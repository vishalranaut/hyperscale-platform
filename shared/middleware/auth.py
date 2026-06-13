"""HyperScale Platform — Authentication Middleware.

Multi-strategy authentication supporting JWT Bearer tokens, Firebase
ID tokens, and API Keys. Populates request.user_payload with decoded
credentials for downstream authorization checks.
"""

from __future__ import annotations

from typing import Any, Callable

from django.http import HttpRequest, JsonResponse

from shared.auth.jwt_handler import JWTHandler, TokenPayload
from shared.logging import get_logger, set_log_context

logger = get_logger(__name__)


class AuthMiddleware:
    """ASGI middleware that authenticates requests using multiple strategies.

    Authentication strategies (tried in order):
        1. **JWT Bearer** — ``Authorization: Bearer <jwt>``
        2. **Firebase ID Token** — ``Authorization: Firebase <id_token>``
        3. **API Key** — ``X-API-Key: <key>``

    On successful authentication, sets ``request.user_payload`` with the
    decoded token payload. Public endpoints (listed in ``PUBLIC_PATHS``)
    bypass authentication entirely.

    Args:
        get_response: The next middleware or view in the chain.

    Example:
        Add to Django MIDDLEWARE setting::

            MIDDLEWARE = [
                'shared.middleware.tracing.RequestTracingMiddleware',
                'shared.middleware.auth.AuthMiddleware',
                ...
            ]
    """

    # Paths that do not require authentication
    PUBLIC_PATHS: set[str] = {
        "/health",
        "/ready",
        "/metrics",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/graphql",  # GraphQL handles auth via directives
    }

    # Path prefixes that do not require authentication
    PUBLIC_PREFIXES: list[str] = [
        "/api/v1/auth/oauth/",
        "/admin/",
        "/static/",
    ]

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self._jwt_handler: JWTHandler | None = None

    async def _get_jwt_handler(self) -> JWTHandler:
        """Lazily initialize the JWT handler with Redis support.

        Returns:
            Configured JWTHandler instance.
        """
        if self._jwt_handler is None:
            try:
                from shared.cache.redis_client import get_redis_client

                redis = await get_redis_client()
                self._jwt_handler = JWTHandler(redis_client=redis)
            except Exception:
                self._jwt_handler = JWTHandler()
        return self._jwt_handler

    def _is_public_path(self, path: str) -> bool:
        """Check if the request path is exempt from authentication.

        Args:
            path: The URL path to check.

        Returns:
            True if the path does not require authentication.
        """
        if path in self.PUBLIC_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES)

    def _extract_bearer_token(self, request: HttpRequest) -> str | None:
        """Extract a JWT Bearer token from the Authorization header.

        Args:
            request: The incoming HTTP request.

        Returns:
            The token string if present, None otherwise.
        """
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return None

    def _extract_firebase_token(self, request: HttpRequest) -> str | None:
        """Extract a Firebase ID token from the Authorization header.

        Args:
            request: The incoming HTTP request.

        Returns:
            The Firebase token string if present, None otherwise.
        """
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Firebase "):
            return auth_header[9:].strip()
        return None

    def _extract_api_key(self, request: HttpRequest) -> str | None:
        """Extract an API key from the X-API-Key header.

        Args:
            request: The incoming HTTP request.

        Returns:
            The API key string if present, None otherwise.
        """
        return request.META.get("HTTP_X_API_KEY")

    async def _authenticate_jwt(self, token: str) -> TokenPayload:
        """Authenticate using a JWT Bearer token.

        Args:
            token: The encoded JWT string.

        Returns:
            Decoded token payload.

        Raises:
            AuthenticationError: If the token is invalid or blacklisted.
        """
        handler = await self._get_jwt_handler()
        return await handler.validate_access_token(token)

    async def _authenticate_firebase(self, token: str) -> TokenPayload:
        """Authenticate using a Firebase ID token.

        Verifies the token with Firebase Admin SDK and creates a
        TokenPayload-compatible object.

        Args:
            token: The Firebase ID token string.

        Returns:
            A TokenPayload constructed from Firebase claims.

        Raises:
            AuthenticationError: If the Firebase token is invalid.
        """
        from shared.auth.jwt_handler import TokenType, verify_firebase_token

        claims = await verify_firebase_token(token)
        return TokenPayload(
            sub=claims.get("uid", ""),
            token_type=TokenType.ACCESS,
            roles=claims.get("roles", []),
            permissions=claims.get("permissions", []),
            firebase_uid=claims.get("uid"),
        )

    async def _authenticate_api_key(self, api_key: str) -> TokenPayload | None:
        """Authenticate using an API key.

        Looks up the API key in Redis or the database to find the
        associated service account.

        Args:
            api_key: The API key string.

        Returns:
            A TokenPayload for the service account, or None if not found.
        """
        from shared.auth.jwt_handler import TokenType

        try:
            from shared.cache.redis_client import get_redis_client

            redis = await get_redis_client()
            service_data = await redis.hgetall(f"apikey:{api_key}")
            if service_data:
                return TokenPayload(
                    sub=service_data.get("service_id", "api-client"),
                    token_type=TokenType.ACCESS,
                    roles=service_data.get("roles", "").split(","),
                    permissions=service_data.get("permissions", "").split(","),
                )
        except Exception as e:
            logger.error("api_key_lookup_failed", error=str(e))

        return None

    async def __call__(self, request: HttpRequest) -> Any:
        """Process the request through authentication.

        Args:
            request: The incoming HTTP request.

        Returns:
            The response from the next middleware/view, or a 401 response
            if authentication fails on a protected endpoint.
        """
        # Initialize user_payload as None
        request.user_payload = None  # type: ignore[attr-defined]

        # Skip auth for public paths
        if self._is_public_path(request.path):
            return await self.get_response(request)

        # Try JWT Bearer first
        bearer_token = self._extract_bearer_token(request)
        if bearer_token:
            try:
                payload = await self._authenticate_jwt(bearer_token)
                request.user_payload = payload  # type: ignore[attr-defined]
                set_log_context(user_id=payload.sub)
                return await self.get_response(request)
            except Exception as e:
                logger.warning("jwt_auth_failed", error=str(e))
                return JsonResponse(
                    {
                        "error": {
                            "code": "AUTHENTICATION_ERROR",
                            "message": str(e),
                        }
                    },
                    status=401,
                )

        # Try Firebase token
        firebase_token = self._extract_firebase_token(request)
        if firebase_token:
            try:
                payload = await self._authenticate_firebase(firebase_token)
                request.user_payload = payload  # type: ignore[attr-defined]
                set_log_context(user_id=payload.sub)
                return await self.get_response(request)
            except Exception as e:
                logger.warning("firebase_auth_failed", error=str(e))
                return JsonResponse(
                    {
                        "error": {
                            "code": "AUTHENTICATION_ERROR",
                            "message": str(e),
                        }
                    },
                    status=401,
                )

        # Try API Key
        api_key = self._extract_api_key(request)
        if api_key:
            payload = await self._authenticate_api_key(api_key)
            if payload:
                request.user_payload = payload  # type: ignore[attr-defined]
                set_log_context(user_id=payload.sub)
                return await self.get_response(request)
            return JsonResponse(
                {
                    "error": {
                        "code": "AUTHENTICATION_ERROR",
                        "message": "Invalid API key",
                    }
                },
                status=401,
            )

        # No authentication credentials provided
        return JsonResponse(
            {
                "error": {
                    "code": "AUTHENTICATION_ERROR",
                    "message": "Authentication credentials not provided",
                    "detail": {
                        "supported_schemes": [
                            "Bearer <jwt>",
                            "Firebase <id_token>",
                            "X-API-Key header",
                        ]
                    },
                }
            },
            status=401,
        )
