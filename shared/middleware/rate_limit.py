"""HyperScale Platform — Rate Limiting Middleware.

Redis-backed sliding window rate limiter with per-user and per-endpoint
granularity. Supports configurable limits for different endpoint groups.

The sliding window algorithm ensures smooth rate limiting without the
burst issues of fixed window approaches.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from django.http import HttpRequest, JsonResponse

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware:
    """ASGI/WSGI middleware implementing Redis sliding window rate limiting.

    Rate limits are applied per-user (authenticated) or per-IP (anonymous).
    Different endpoint prefixes can have different limits.

    Args:
        get_response: The next middleware or view in the chain.

    Attributes:
        RATE_LIMIT_RULES: Mapping of URL prefix patterns to
            (max_requests, window_seconds) tuples.

    Example:
        Add to Django MIDDLEWARE setting::

            MIDDLEWARE = [
                'shared.middleware.rate_limit.RateLimitMiddleware',
                ...
            ]
    """

    # Endpoint-specific rate limit rules: prefix → (requests, window_seconds)
    RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
        "/api/v1/auth/login": (10, 300),      # 10 requests per 5 min
        "/api/v1/auth/register": (5, 600),     # 5 requests per 10 min
        "/api/v1/auth/refresh": (20, 60),      # 20 requests per minute
    }

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self._settings = get_settings()
        self._redis: Any | None = None
        self._default_requests = self._settings.RATE_LIMIT_DEFAULT_REQUESTS
        self._default_window = self._settings.RATE_LIMIT_DEFAULT_WINDOW_SECONDS

    async def _get_redis(self) -> Any:
        """Lazily initialize the Redis client.

        Returns:
            The async Redis client instance.
        """
        if self._redis is None:
            from shared.cache.redis_client import get_redis_client

            self._redis = await get_redis_client()
        return self._redis

    def _get_client_identifier(self, request: HttpRequest) -> str:
        """Extract a unique client identifier for rate limiting.

        Uses the authenticated user ID if available, otherwise falls
        back to the client IP address.

        Args:
            request: The incoming HTTP request.

        Returns:
            A string identifier for the client.
        """
        # Prefer authenticated user ID
        user_payload = getattr(request, "user_payload", None)
        if user_payload and hasattr(user_payload, "sub"):
            return f"user:{user_payload.sub}"

        # Fall back to IP address
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return f"ip:{x_forwarded_for.split(',')[0].strip()}"
        return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"

    def _get_rate_limit(self, path: str) -> tuple[int, int]:
        """Determine the rate limit for a given URL path.

        Args:
            path: The request URL path.

        Returns:
            Tuple of (max_requests, window_seconds) for the matched rule.
        """
        for prefix, limits in self.RATE_LIMIT_RULES.items():
            if path.startswith(prefix):
                return limits
        return (self._default_requests, self._default_window)

    async def _check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Check and update the sliding window rate limit counter.

        Uses Redis sorted sets with timestamp-based scoring for a
        precise sliding window implementation.

        Args:
            key: The Redis key for this rate limit bucket.
            max_requests: Maximum allowed requests in the window.
            window_seconds: Size of the sliding window in seconds.

        Returns:
            Tuple of (is_allowed, remaining_requests, retry_after_seconds).
        """
        try:
            redis = await self._get_redis()
            now = time.time()
            window_start = now - window_seconds

            pipe = redis.pipeline()
            # Remove entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            # Count entries in the current window
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {f"{now}": now})
            # Set TTL on the key
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()

            current_count = results[1]

            if current_count >= max_requests:
                # Get the oldest entry to calculate retry-after
                oldest = await redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(window_seconds - (now - oldest[0][1])) + 1
                else:
                    retry_after = window_seconds
                return False, 0, retry_after

            remaining = max_requests - current_count - 1
            return True, max(remaining, 0), 0

        except Exception as e:
            # If Redis is down, allow the request (fail-open)
            logger.error("rate_limit_check_failed", error=str(e))
            return True, max_requests, 0

    async def __call__(self, request: HttpRequest) -> Any:
        """Process the request through rate limiting.

        Args:
            request: The incoming HTTP request.

        Returns:
            The response from the next middleware/view, or a 429 response
            if rate limited.
        """
        # Skip rate limiting for health checks and metrics
        skip_paths = {"/health", "/ready", "/metrics"}
        if request.path in skip_paths:
            return await self.get_response(request)

        client_id = self._get_client_identifier(request)
        max_requests, window_seconds = self._get_rate_limit(request.path)
        key = f"ratelimit:{request.path}:{client_id}"

        is_allowed, remaining, retry_after = await self._check_rate_limit(
            key, max_requests, window_seconds
        )

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_id=client_id,
                path=request.path,
                retry_after=retry_after,
            )
            response = JsonResponse(
                {
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Rate limit exceeded",
                        "detail": {
                            "retry_after_seconds": retry_after,
                            "limit": max_requests,
                            "window_seconds": window_seconds,
                        },
                    }
                },
                status=429,
            )
            response["Retry-After"] = str(retry_after)
            response["X-RateLimit-Limit"] = str(max_requests)
            response["X-RateLimit-Remaining"] = "0"
            response["X-RateLimit-Reset"] = str(int(time.time()) + retry_after)
            return response

        response = await self.get_response(request)

        # Add rate limit headers to successful responses
        response["X-RateLimit-Limit"] = str(max_requests)
        response["X-RateLimit-Remaining"] = str(remaining)
        response["X-RateLimit-Reset"] = str(int(time.time()) + window_seconds)

        return response
