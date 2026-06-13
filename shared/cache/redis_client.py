"""HyperScale Platform — Async Redis Client.

Provides an async Redis client singleton with connection pooling, a
cache-aside decorator with TTL and key namespacing, and a distributed
lock implementation using the Redlock algorithm.

Example:
    >>> redis = await get_redis_client()
    >>> await redis.set("key", "value", ex=300)
    >>> value = await redis.get("key")

    >>> @cache_aside(ttl=300, namespace="products")
    ... async def get_product(product_id: str) -> dict:
    ...     return await db.find_product(product_id)

    >>> async with DistributedLock(redis, "inventory:sku123"):
    ...     await process_inventory_update()
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import time
import uuid
from typing import Any, Callable, TypeVar

import redis.asyncio as aioredis

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ── Singleton Client ─────────────────────────────────────────────────────────

_redis_client: aioredis.Redis | None = None
_redis_lock: asyncio.Lock = asyncio.Lock()


async def get_redis_client() -> aioredis.Redis:
    """Get or create the singleton async Redis client.

    Uses a connection pool with configurable max connections. The client
    is created once and reused across the application lifetime.

    Returns:
        Configured aioredis.Redis instance.

    Example:
        >>> redis = await get_redis_client()
        >>> await redis.ping()
        True
    """
    global _redis_client

    async with _redis_lock:
        if _redis_client is None:
            settings = get_settings()
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            logger.info("redis_client_initialized", url=settings.REDIS_URL)
        return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client and release connections.

    Should be called during application shutdown.
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("redis_client_closed")


# ── Cache-Aside Decorator ───────────────────────────────────────────────────


def _build_cache_key(namespace: str, func_name: str, args: tuple, kwargs: dict) -> str:
    """Build a deterministic cache key from function arguments.

    Args:
        namespace: Key namespace prefix (e.g., service name).
        func_name: The cached function's name.
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A namespaced cache key string.
    """
    # Create a hash of the arguments for the key
    key_parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    key_data = ":".join(key_parts)
    key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]  # noqa: S324
    return f"cache:{namespace}:{func_name}:{key_hash}"


def cache_aside(
    ttl: int = 300,
    namespace: str = "default",
    key_builder: Callable[..., str] | None = None,
) -> Callable[[F], F]:
    """Decorator implementing the cache-aside (lazy-loading) pattern.

    On cache miss, calls the decorated function and stores the result
    in Redis with the specified TTL. On cache hit, returns the cached
    result without calling the function.

    Args:
        ttl: Time-to-live in seconds for cached values (default: 300).
        namespace: Key namespace for grouping related cache entries.
        key_builder: Optional custom function to build cache keys.
            Receives the same arguments as the decorated function.

    Returns:
        Decorated async function with caching.

    Example:
        >>> @cache_aside(ttl=600, namespace="products")
        ... async def get_product(product_id: str) -> dict:
        ...     return await db.products.find_one({"_id": product_id})
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                redis = await get_redis_client()

                # Build cache key
                if key_builder:
                    cache_key = key_builder(*args, **kwargs)
                else:
                    cache_key = _build_cache_key(namespace, func.__name__, args, kwargs)

                # Try cache first
                cached = await redis.get(cache_key)
                if cached is not None:
                    import orjson

                    logger.debug("cache_hit", key=cache_key)
                    return orjson.loads(cached)

                logger.debug("cache_miss", key=cache_key)

            except Exception as e:
                logger.warning("cache_read_error", error=str(e))
                # Fall through to call the function
                return await func(*args, **kwargs)

            # Cache miss — call function
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                import orjson

                serialized = orjson.dumps(result)
                await redis.setex(cache_key, ttl, serialized)
                logger.debug("cache_set", key=cache_key, ttl=ttl)
            except Exception as e:
                logger.warning("cache_write_error", error=str(e))

            return result

        return wrapper  # type: ignore[return-value]

    return decorator


async def invalidate_cache(namespace: str, pattern: str = "*") -> int:
    """Invalidate cache entries matching a pattern within a namespace.

    Args:
        namespace: The cache namespace to invalidate.
        pattern: Glob pattern for key matching (default: all keys).

    Returns:
        Number of keys deleted.

    Example:
        >>> await invalidate_cache("products", "get_product:*")
    """
    redis = await get_redis_client()
    full_pattern = f"cache:{namespace}:{pattern}"
    keys = []

    async for key in redis.scan_iter(match=full_pattern, count=100):
        keys.append(key)

    if keys:
        deleted = await redis.delete(*keys)
        logger.info("cache_invalidated", namespace=namespace, keys_deleted=deleted)
        return deleted
    return 0


# ── Distributed Lock (Redlock) ───────────────────────────────────────────────


class DistributedLock:
    """Redis-based distributed lock using the Redlock algorithm.

    Provides mutual exclusion across multiple service instances for
    critical sections like inventory updates or payment processing.

    Args:
        redis: The async Redis client.
        resource: The resource name to lock (e.g., 'inventory:sku123').
        ttl: Lock time-to-live in seconds (default: 30).
        retry_count: Number of acquisition attempts (default: 3).
        retry_delay: Seconds between retry attempts (default: 0.2).

    Example:
        >>> redis = await get_redis_client()
        >>> async with DistributedLock(redis, "inventory:product123", ttl=10):
        ...     await update_inventory(product_id, -1)

        >>> lock = DistributedLock(redis, "payment:order456")
        >>> if await lock.acquire():
        ...     try:
        ...         await process_payment(order)
        ...     finally:
        ...         await lock.release()
    """

    LOCK_PREFIX = "lock:"

    def __init__(
        self,
        redis: aioredis.Redis,
        resource: str,
        ttl: int = 30,
        retry_count: int = 3,
        retry_delay: float = 0.2,
    ) -> None:
        self._redis = redis
        self._resource = resource
        self._ttl = ttl
        self._retry_count = retry_count
        self._retry_delay = retry_delay
        self._lock_key = f"{self.LOCK_PREFIX}{resource}"
        self._lock_value = str(uuid.uuid4())
        self._acquired = False

    async def acquire(self) -> bool:
        """Attempt to acquire the distributed lock.

        Uses SET NX (set-if-not-exists) with a TTL to prevent deadlocks.
        Retries with delays on failure.

        Returns:
            True if the lock was acquired, False if it could not be acquired
            after all retry attempts.
        """
        for attempt in range(self._retry_count):
            result = await self._redis.set(
                self._lock_key,
                self._lock_value,
                nx=True,
                ex=self._ttl,
            )
            if result:
                self._acquired = True
                logger.debug(
                    "lock_acquired",
                    resource=self._resource,
                    lock_value=self._lock_value,
                )
                return True

            if attempt < self._retry_count - 1:
                await asyncio.sleep(self._retry_delay)

        logger.warning(
            "lock_acquisition_failed",
            resource=self._resource,
            retry_count=self._retry_count,
        )
        return False

    async def release(self) -> bool:
        """Release the distributed lock.

        Uses a Lua script to atomically check-and-delete, ensuring only
        the lock holder can release the lock (prevents accidental release
        of another holder's lock).

        Returns:
            True if the lock was released, False if it was already released
            or held by another holder.
        """
        if not self._acquired:
            return False

        # Atomic check-and-delete via Lua script
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self._redis.eval(lua_script, 1, self._lock_key, self._lock_value)  # type: ignore[arg-type]
        self._acquired = False

        if result:
            logger.debug("lock_released", resource=self._resource)
            return True

        logger.warning(
            "lock_release_failed",
            resource=self._resource,
            reason="lock_value_mismatch",
        )
        return False

    async def extend(self, additional_ttl: int) -> bool:
        """Extend the lock's TTL if still held by this instance.

        Useful for long-running operations that need more time.

        Args:
            additional_ttl: Additional seconds to add to the lock TTL.

        Returns:
            True if the lock was extended, False if not held.
        """
        if not self._acquired:
            return False

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self._redis.eval(  # type: ignore[arg-type]
            lua_script, 1, self._lock_key, self._lock_value, str(additional_ttl)
        )

        if result:
            logger.debug(
                "lock_extended",
                resource=self._resource,
                additional_ttl=additional_ttl,
            )
            return True
        return False

    async def __aenter__(self) -> "DistributedLock":
        """Async context manager entry — acquires the lock.

        Raises:
            RuntimeError: If the lock could not be acquired.
        """
        acquired = await self.acquire()
        if not acquired:
            raise RuntimeError(
                f"Could not acquire lock for resource: {self._resource}"
            )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit — releases the lock."""
        await self.release()
