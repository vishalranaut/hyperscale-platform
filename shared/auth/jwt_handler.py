"""HyperScale Platform — JWT Token Management.

Provides JWT access/refresh token creation, decoding, and validation.
Integrates with Firebase Auth for federated identity verification and
uses Redis for token blacklisting (logout support).

Example:
    >>> handler = JWTHandler()
    >>> tokens = await handler.create_token_pair({"sub": "user123", "roles": ["admin"]})
    >>> payload = await handler.decode_token(tokens.access_token)
    >>> await handler.blacklist_token(tokens.access_token)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import jwt
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.exceptions import AuthenticationError
from shared.logging import get_logger

logger = get_logger(__name__)


class TokenType(str, Enum):
    """JWT token type enumeration."""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    """Decoded JWT token payload.

    Attributes:
        sub: Subject — typically the user ID.
        token_type: Whether this is an access or refresh token.
        roles: List of role names assigned to the user.
        permissions: Flattened list of permission strings.
        jti: JWT ID — unique identifier for this token.
        iat: Issued-at timestamp.
        exp: Expiration timestamp.
        iss: Issuer identifier.
        firebase_uid: Optional Firebase user UID.
    """

    sub: str
    token_type: TokenType
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    jti: str = Field(default_factory=lambda: str(uuid.uuid4()))
    iat: datetime = Field(default_factory=lambda: datetime.now(UTC))
    exp: datetime | None = None
    iss: str = "hyperscale-platform"
    firebase_uid: str | None = None


class TokenPair(BaseModel):
    """JWT access/refresh token pair returned after authentication.

    Attributes:
        access_token: Short-lived JWT for API authorization.
        refresh_token: Long-lived JWT for obtaining new access tokens.
        token_type: Always "Bearer".
        expires_in: Access token lifetime in seconds.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class JWTHandler:
    """Manages JWT creation, validation, and blacklisting.

    Uses PyJWT for token operations and Redis for maintaining a
    blacklist of revoked tokens (supporting logout).

    Args:
        redis_client: Optional async Redis client for token blacklisting.
            If not provided, blacklist operations will log warnings but
            will not prevent token validation.

    Example:
        >>> from shared.cache.redis_client import get_redis_client
        >>> redis = await get_redis_client()
        >>> handler = JWTHandler(redis_client=redis)
        >>> pair = await handler.create_token_pair({"sub": "user_123"})
    """

    BLACKLIST_PREFIX = "token:blacklist:"

    def __init__(self, redis_client: Any | None = None) -> None:
        self._settings = get_settings()
        self._redis = redis_client
        self._secret = self._settings.JWT_SECRET
        self._algorithm = self._settings.JWT_ALGORITHM
        self._access_expire_minutes = self._settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self._refresh_expire_days = self._settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(
        self,
        payload: dict[str, Any],
        expire_minutes: int | None = None,
    ) -> str:
        """Create a short-lived access token.

        Args:
            payload: Claims to encode. Must include 'sub' (subject).
            expire_minutes: Custom expiration in minutes. Defaults to
                JWT_ACCESS_TOKEN_EXPIRE_MINUTES from settings.

        Returns:
            Encoded JWT string.

        Raises:
            ValueError: If 'sub' is not in the payload.
        """
        if "sub" not in payload:
            raise ValueError("Token payload must include 'sub' (subject)")

        expire = expire_minutes or self._access_expire_minutes
        now = datetime.now(UTC)
        claims = {
            **payload,
            "token_type": TokenType.ACCESS.value,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=expire),
            "iss": "hyperscale-platform",
        }
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def create_refresh_token(
        self,
        payload: dict[str, Any],
        expire_days: int | None = None,
    ) -> str:
        """Create a long-lived refresh token.

        Args:
            payload: Claims to encode. Must include 'sub' (subject).
            expire_days: Custom expiration in days. Defaults to
                JWT_REFRESH_TOKEN_EXPIRE_DAYS from settings.

        Returns:
            Encoded JWT string.

        Raises:
            ValueError: If 'sub' is not in the payload.
        """
        if "sub" not in payload:
            raise ValueError("Token payload must include 'sub' (subject)")

        expire = expire_days or self._refresh_expire_days
        now = datetime.now(UTC)
        claims = {
            "sub": payload["sub"],
            "token_type": TokenType.REFRESH.value,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(days=expire),
            "iss": "hyperscale-platform",
        }
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    async def create_token_pair(
        self,
        payload: dict[str, Any],
        access_expire_minutes: int | None = None,
        refresh_expire_days: int | None = None,
    ) -> TokenPair:
        """Create a paired access + refresh token set.

        Args:
            payload: Claims to encode. Must include 'sub'.
            access_expire_minutes: Custom access token expiration.
            refresh_expire_days: Custom refresh token expiration.

        Returns:
            A TokenPair with both tokens and metadata.
        """
        access_expire = access_expire_minutes or self._access_expire_minutes
        access_token = self.create_access_token(payload, access_expire)
        refresh_token = self.create_refresh_token(payload, refresh_expire_days)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_expire * 60,
        )

    def decode_token(
        self,
        token: str,
        verify_exp: bool = True,
    ) -> TokenPayload:
        """Decode and validate a JWT token.

        Args:
            token: The encoded JWT string.
            verify_exp: Whether to verify token expiration. Set to False
                for token inspection without validation.

        Returns:
            Decoded TokenPayload with all claims.

        Raises:
            AuthenticationError: If the token is invalid, expired, or malformed.
        """
        try:
            decoded = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={
                    "verify_exp": verify_exp,
                    "require": ["sub", "token_type", "jti", "exp", "iat"],
                },
                issuer="hyperscale-platform",
            )
            return TokenPayload(**decoded)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError(
                message="Token has expired",
                code="TOKEN_EXPIRED",
            )
        except jwt.InvalidTokenError as e:
            logger.warning("jwt_decode_failed", error=str(e))
            raise AuthenticationError(
                message="Invalid token",
                code="TOKEN_INVALID",
                detail={"reason": str(e)},
            )

    async def validate_access_token(self, token: str) -> TokenPayload:
        """Validate an access token, checking both JWT validity and blacklist.

        Args:
            token: The encoded JWT access token.

        Returns:
            Decoded TokenPayload if valid.

        Raises:
            AuthenticationError: If token is invalid, expired, or blacklisted.
        """
        payload = self.decode_token(token)

        if payload.token_type != TokenType.ACCESS:
            raise AuthenticationError(
                message="Invalid token type",
                code="INVALID_TOKEN_TYPE",
                detail={"expected": "access", "got": payload.token_type.value},
            )

        # Check blacklist
        if await self.is_blacklisted(payload.jti):
            raise AuthenticationError(
                message="Token has been revoked",
                code="TOKEN_REVOKED",
            )

        return payload

    async def blacklist_token(self, token: str) -> None:
        """Add a token to the blacklist (for logout).

        The token is stored in Redis with a TTL matching its remaining
        lifetime, so expired tokens are automatically cleaned up.

        Args:
            token: The encoded JWT to blacklist.
        """
        if self._redis is None:
            logger.warning("redis_not_configured", action="blacklist_token")
            return

        try:
            payload = self.decode_token(token, verify_exp=False)
            key = f"{self.BLACKLIST_PREFIX}{payload.jti}"

            # Calculate remaining TTL
            if payload.exp:
                remaining = (payload.exp - datetime.now(UTC)).total_seconds()
                ttl = max(int(remaining), 1)
            else:
                ttl = self._access_expire_minutes * 60

            await self._redis.setex(key, ttl, "1")
            logger.info("token_blacklisted", jti=payload.jti, ttl=ttl)
        except Exception as e:
            logger.error("blacklist_failed", error=str(e))
            raise

    async def is_blacklisted(self, jti: str) -> bool:
        """Check if a token ID is in the blacklist.

        Args:
            jti: The JWT ID to check.

        Returns:
            True if the token is blacklisted, False otherwise.
        """
        if self._redis is None:
            return False

        try:
            result = await self._redis.exists(f"{self.BLACKLIST_PREFIX}{jti}")
            return bool(result)
        except Exception as e:
            logger.error("blacklist_check_failed", error=str(e), jti=jti)
            return False


async def verify_firebase_token(id_token: str) -> dict[str, Any]:
    """Verify a Firebase ID token asynchronously.

    Uses the Firebase Admin SDK to verify the token's signature,
    expiration, and audience. Runs the synchronous verification
    in a thread pool executor.

    Args:
        id_token: The Firebase ID token string from the client.

    Returns:
        Decoded Firebase token claims dictionary containing uid,
        email, and other user information.

    Raises:
        AuthenticationError: If the token is invalid, expired, or
            the Firebase SDK is not initialized.
    """
    import asyncio

    try:
        import firebase_admin.auth as firebase_auth

        loop = asyncio.get_running_loop()
        decoded_token = await loop.run_in_executor(
            None,
            firebase_auth.verify_id_token,
            id_token,
        )
        return decoded_token
    except ImportError:
        raise AuthenticationError(
            message="Firebase Admin SDK not configured",
            code="FIREBASE_NOT_CONFIGURED",
        )
    except Exception as e:
        logger.warning("firebase_token_verification_failed", error=str(e))
        raise AuthenticationError(
            message="Invalid Firebase token",
            code="FIREBASE_TOKEN_INVALID",
            detail={"reason": str(e)},
        )
