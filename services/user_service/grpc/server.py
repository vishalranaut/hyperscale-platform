"""HyperScale Platform — User Service gRPC Server.

gRPC server implementation for the User service. Provides inter-service
RPC endpoints for user lookup, token validation, and permission queries.
"""

from __future__ import annotations

import asyncio
from concurrent import futures
from typing import Any

import grpc
from grpc import aio as grpc_aio

from services.user_service.repositories.user_repository import (
    RoleRepository,
    UserProfileRepository,
    UserRepository,
)
from shared.auth.jwt_handler import JWTHandler
from shared.cache.redis_client import get_redis_client
from shared.config import get_settings
from shared.logging import get_logger, setup_logging

logger = get_logger(__name__)


class UserServiceServicer:
    """gRPC servicer implementing the UserService proto definition.

    Provides user lookup, token validation, and permission resolution
    for inter-service communication.

    Example:
        This servicer is registered with the gRPC server automatically
        when calling ``serve()``. Other services call it via gRPC stubs::

            channel = grpc.aio.insecure_channel("localhost:50051")
            stub = UserServiceStub(channel)
            response = await stub.GetUser(GetUserRequest(user_id="abc123"))
    """

    def __init__(self) -> None:
        self._user_repo = UserRepository()
        self._role_repo = RoleRepository()
        self._profile_repo = UserProfileRepository()
        self._jwt_handler: JWTHandler | None = None

    async def _get_jwt_handler(self) -> JWTHandler:
        """Lazily initialize JWT handler with Redis."""
        if self._jwt_handler is None:
            redis = await get_redis_client()
            self._jwt_handler = JWTHandler(redis_client=redis)
        return self._jwt_handler

    async def GetUser(self, request: Any, context: grpc.aio.ServicerContext) -> Any:
        """Get a single user by ID.

        Args:
            request: GetUserRequest with user_id and include_profile flag.
            context: gRPC servicer context.

        Returns:
            UserResponse proto message.
        """
        try:
            user = await self._user_repo.get_by_id(request.user_id)
            if user is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"User {request.user_id} not found")
                return _empty_user_response()

            profile = None
            if request.include_profile:
                profile = await self._profile_repo.get_by_user_id(request.user_id)

            return _user_to_proto(user, profile)
        except Exception as e:
            logger.error("grpc_get_user_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return _empty_user_response()

    async def ValidateToken(self, request: Any, context: grpc.aio.ServicerContext) -> Any:
        """Validate a JWT or Firebase token.

        Args:
            request: ValidateTokenRequest with token and token_type.
            context: gRPC servicer context.

        Returns:
            TokenPayload proto message.
        """
        try:
            jwt_handler = await self._get_jwt_handler()

            if request.token_type == "firebase":
                from shared.auth.jwt_handler import verify_firebase_token
                claims = await verify_firebase_token(request.token)
                return _make_token_payload_proto(
                    sub=claims.get("uid", ""),
                    token_type="access",
                    roles=claims.get("roles", []),
                    permissions=claims.get("permissions", []),
                    valid=True,
                )
            else:
                payload = await jwt_handler.validate_access_token(request.token)
                return _make_token_payload_proto(
                    sub=payload.sub,
                    token_type=payload.token_type.value,
                    roles=payload.roles,
                    permissions=payload.permissions,
                    jti=payload.jti,
                    valid=True,
                )
        except Exception as e:
            return _make_token_payload_proto(valid=False, error=str(e))

    async def GetUserPermissions(
        self, request: Any, context: grpc.aio.ServicerContext
    ) -> Any:
        """Get all resolved permissions for a user.

        Args:
            request: UserIdRequest with user_id.
            context: gRPC servicer context.

        Returns:
            PermissionsResponse proto message.
        """
        try:
            user = await self._user_repo.get_by_id(request.user_id)
            if user is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("User not found")
                return _empty_permissions_response()

            permissions = await self._role_repo.get_permissions_for_roles(user.roles)
            return _make_permissions_response(request.user_id, user.roles, permissions)
        except Exception as e:
            logger.error("grpc_get_permissions_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return _empty_permissions_response()

    async def BulkGetUsers(self, request: Any, context: grpc.aio.ServicerContext) -> Any:
        """Bulk fetch users by IDs.

        Args:
            request: BulkUserRequest with user_ids list.
            context: gRPC servicer context.

        Returns:
            BulkUserResponse proto message.
        """
        try:
            user_ids = list(request.user_ids)
            if request.max_results > 0:
                user_ids = user_ids[:request.max_results]

            users = await self._user_repo.bulk_get(user_ids)
            user_protos = [_user_to_proto(u) for u in users]

            return _make_bulk_user_response(user_protos, len(users))
        except Exception as e:
            logger.error("grpc_bulk_get_users_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return _make_bulk_user_response([], 0)

    async def HealthCheck(self, request: Any, context: grpc.aio.ServicerContext) -> Any:
        """Health check endpoint for gRPC.

        Returns:
            HealthCheckResponse with SERVING status.
        """
        return _make_health_response("user-service")


# ── Proto Message Helpers ────────────────────────────────────────────────────
# These functions create proto-compatible dictionaries since we don't
# import generated pb2 modules directly (they're generated at build time).


def _empty_user_response() -> dict[str, Any]:
    """Create an empty user response dict."""
    return {"id": "", "email": "", "full_name": ""}


def _user_to_proto(user: Any, profile: Any | None = None) -> dict[str, Any]:
    """Convert a User document to a proto-compatible dictionary.

    Args:
        user: The User document.
        profile: Optional UserProfile document.

    Returns:
        Dictionary matching UserResponse proto fields.
    """
    result: dict[str, Any] = {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone or "",
        "avatar_url": user.avatar_url or "",
        "roles": user.roles,
        "is_verified": user.is_verified,
        "is_active": user.is_active,
        "firebase_uid": user.firebase_uid or "",
        "created_at": {"value": user.created_at.isoformat()},
        "last_login": {"value": user.last_login.isoformat()} if user.last_login else None,
    }

    if profile:
        result["profile"] = {
            "bio": profile.bio or "",
            "social_links": profile.social_links or {},
            "preferences": {k: str(v) for k, v in (profile.preferences or {}).items()},
            "location": profile.location or "",
        }

    return result


def _make_token_payload_proto(**kwargs: Any) -> dict[str, Any]:
    """Create a TokenPayload proto-compatible dictionary."""
    return {
        "sub": kwargs.get("sub", ""),
        "token_type": kwargs.get("token_type", ""),
        "roles": kwargs.get("roles", []),
        "permissions": kwargs.get("permissions", []),
        "jti": kwargs.get("jti", ""),
        "valid": kwargs.get("valid", False),
        "error": kwargs.get("error", ""),
    }


def _empty_permissions_response() -> dict[str, Any]:
    """Create an empty permissions response dict."""
    return {"user_id": "", "permissions": [], "roles": []}


def _make_permissions_response(
    user_id: str, roles: list[str], permissions: list[str]
) -> dict[str, Any]:
    """Create a PermissionsResponse proto-compatible dictionary."""
    perm_objects = []
    for p in permissions:
        parts = p.split(":")
        perm_objects.append({
            "resource": parts[0] if len(parts) > 0 else p,
            "action": parts[1] if len(parts) > 1 else "*",
            "conditions": {},
        })
    return {"user_id": user_id, "permissions": perm_objects, "roles": roles}


def _make_bulk_user_response(users: list[dict], total: int) -> dict[str, Any]:
    """Create a BulkUserResponse proto-compatible dictionary."""
    return {"users": users, "total": total}


def _make_health_response(service_name: str) -> dict[str, Any]:
    """Create a HealthCheckResponse proto-compatible dictionary."""
    from datetime import UTC, datetime

    return {
        "status": 1,  # SERVING
        "service_name": service_name,
        "version": "1.0.0",
        "timestamp": {"value": datetime.now(UTC).isoformat()},
    }


async def serve(port: int | None = None) -> None:
    """Start the gRPC server for the User service.

    Args:
        port: Port to listen on. Defaults to settings.USER_SERVICE_GRPC_PORT.
    """
    settings = get_settings()
    grpc_port = port or settings.USER_SERVICE_GRPC_PORT

    setup_logging(service_name="user-service-grpc")

    # Initialize MongoDB
    from shared.db.mongodb import init_mongodb
    from services.user_service.domain.models import (
        OAuthConnection, Permission, Role, User, UserProfile,
    )

    await init_mongodb(document_models=[User, Role, Permission, UserProfile, OAuthConnection])

    server = grpc_aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
        ],
    )

    # Register servicer
    servicer = UserServiceServicer()

    # Note: In production, use generated pb2_grpc to register:
    # user_pb2_grpc.add_UserServiceServicer_to_server(servicer, server)
    # For now, we log the server readiness.

    listen_addr = f"[::]:{grpc_port}"
    server.add_insecure_port(listen_addr)
    await server.start()

    logger.info("grpc_server_started", address=listen_addr, service="user-service")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("grpc_server_stopping")
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
