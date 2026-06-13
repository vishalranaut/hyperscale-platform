"""HyperScale Platform — User Service REST API Views.

DRF-based async views for user authentication and management.
All views delegate to the UserService business logic layer.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from services.user_service.domain.schemas import (
    AssignRoleRequest,
    ChangePasswordRequest,
    LoginRequest,
    OAuthLoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserSearchFilters,
)
from services.user_service.services.user_service import UserService
from services.user_service.repositories.user_repository import (
    RoleRepository,
    UserProfileRepository,
    UserRepository,
)
from shared.auth.jwt_handler import JWTHandler
from shared.auth.permissions import IsAdminUser, IsAuthenticated
from shared.cache.redis_client import get_redis_client
from shared.exceptions import HyperScaleException
from shared.logging import get_logger

logger = get_logger(__name__)


async def _get_service() -> UserService:
    """Factory to create UserService with dependencies.

    Returns:
        Configured UserService instance.
    """
    redis = await get_redis_client()
    jwt_handler = JWTHandler(redis_client=redis)
    return UserService(
        user_repo=UserRepository(),
        role_repo=RoleRepository(),
        profile_repo=UserProfileRepository(),
        jwt_handler=jwt_handler,
    )


# ── Auth Endpoints ───────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([AllowAny])
async def register(request: Request) -> Response:
    """Register a new user account.

    POST /api/v1/auth/register

    Request Body:
        {
            "email": "user@example.com",
            "password": "SecurePass123!",
            "full_name": "John Doe",
            "phone": "+1234567890"  // optional
        }

    Returns:
        201: AuthResponse with JWT tokens and user summary.
        409: Email already registered.
        422: Validation failed.
    """
    data = RegisterRequest(**request.data)
    service = await _get_service()
    result = await service.register(
        email=data.email,
        password=data.password,
        full_name=data.full_name,
        phone=data.phone,
    )
    return Response(result.model_dump(), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
async def login(request: Request) -> Response:
    """Authenticate a user with email and password.

    POST /api/v1/auth/login

    Request Body:
        {
            "email": "user@example.com",
            "password": "SecurePass123!"
        }

    Returns:
        200: AuthResponse with JWT tokens.
        401: Invalid credentials or locked account.
    """
    data = LoginRequest(**request.data)
    service = await _get_service()
    result = await service.login(email=data.email, password=data.password)
    return Response(result.model_dump())


@api_view(["POST"])
@permission_classes([AllowAny])
async def oauth_login(request: Request, provider: str) -> Response:
    """Authenticate or register via OAuth provider.

    POST /api/v1/auth/oauth/{provider}

    Path Parameters:
        provider: OAuth provider name (google, github, apple, etc.)

    Request Body:
        {
            "provider": "google",
            "token": "<firebase_id_token>"
        }

    Returns:
        200: AuthResponse with JWT tokens.
        401: Invalid OAuth token.
    """
    data = OAuthLoginRequest(provider=provider, **request.data)
    service = await _get_service()
    result = await service.oauth_login(provider=data.provider, token=data.token)
    return Response(result.model_dump())


@api_view(["POST"])
@permission_classes([AllowAny])
async def refresh_token(request: Request) -> Response:
    """Refresh JWT tokens using a refresh token.

    POST /api/v1/auth/refresh

    Request Body:
        {
            "refresh_token": "<jwt_refresh_token>"
        }

    Returns:
        200: AuthResponse with new JWT tokens.
        401: Invalid or expired refresh token.
    """
    data = RefreshTokenRequest(**request.data)
    service = await _get_service()
    result = await service.refresh_token(data.refresh_token)
    return Response(result.model_dump())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def logout(request: Request) -> Response:
    """Log out the current user by blacklisting their token.

    POST /api/v1/auth/logout

    Headers:
        Authorization: Bearer <access_token>

    Returns:
        200: Success message.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

    service = await _get_service()
    await service.logout(token)
    return Response({"message": "Logged out successfully"})


@api_view(["POST"])
@permission_classes([AllowAny])
async def verify_email(request: Request) -> Response:
    """Verify a user's email address.

    POST /api/v1/auth/verify-email

    Request Body:
        {
            "token": "<verification_token>"
        }

    Returns:
        200: Email verified successfully.
        404: Invalid verification token.
    """
    token = request.data.get("token", "")
    service = await _get_service()
    await service.verify_email(token)
    return Response({"message": "Email verified successfully"})


# ── User Endpoints ───────────────────────────────────────────────────────────


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
async def me(request: Request) -> Response:
    """Get or update the current user's profile.

    GET /api/v1/users/me — Get current user details.
    PUT /api/v1/users/me — Update current user profile.

    Returns:
        200: UserDetailResponse.
        404: User not found.
    """
    user_payload = request.user_payload  # type: ignore[attr-defined]
    user_id = user_payload.sub
    service = await _get_service()

    if request.method == "GET":
        result = await service.get_user(user_id)
        return Response(result.model_dump(mode="json"))

    # PUT — update profile
    data = UpdateProfileRequest(**request.data)
    result = await service.update_profile(user_id, data)
    return Response(result.model_dump(mode="json"))


@api_view(["GET"])
@permission_classes([IsAdminUser])
async def user_detail(request: Request, user_id: str) -> Response:
    """Get a specific user's details (admin only).

    GET /api/v1/users/{user_id}

    Returns:
        200: UserDetailResponse.
        404: User not found.
    """
    service = await _get_service()
    result = await service.get_user(user_id)
    return Response(result.model_dump(mode="json"))


@api_view(["GET"])
@permission_classes([IsAdminUser])
async def user_list(request: Request) -> Response:
    """List users with search and pagination (admin only).

    GET /api/v1/users/?query=john&role=admin&page=1&page_size=20

    Query Parameters:
        query: Free-text search.
        role: Filter by role.
        is_active: Filter by active status.
        is_verified: Filter by verification status.
        page: Page number (default: 1).
        page_size: Items per page (default: 20, max: 100).
        sort_by: Sort field (default: created_at).
        sort_order: asc or desc (default: desc).

    Returns:
        200: PaginatedResponse with UserSummary items.
    """
    service = await _get_service()
    result = await service.search_users(
        query=request.query_params.get("query"),
        role=request.query_params.get("role"),
        is_active=_parse_bool(request.query_params.get("is_active")),
        is_verified=_parse_bool(request.query_params.get("is_verified")),
        page=int(request.query_params.get("page", 1)),
        page_size=int(request.query_params.get("page_size", 20)),
        sort_by=request.query_params.get("sort_by", "created_at"),
        sort_order=request.query_params.get("sort_order", "desc"),
    )
    return Response(result.model_dump(mode="json"))


@api_view(["POST"])
@permission_classes([IsAdminUser])
async def assign_role(request: Request, user_id: str) -> Response:
    """Assign a role to a user (admin only).

    POST /api/v1/users/{user_id}/roles

    Request Body:
        {
            "role_name": "moderator"
        }

    Returns:
        200: Updated UserDetailResponse.
        404: User or role not found.
    """
    data = AssignRoleRequest(**request.data)
    admin_id = request.user_payload.sub  # type: ignore[attr-defined]
    service = await _get_service()
    result = await service.assign_role(user_id, data.role_name, admin_id)
    return Response(result.model_dump(mode="json"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def user_permissions(request: Request) -> Response:
    """Get the current user's resolved permissions.

    GET /api/v1/users/me/permissions

    Returns:
        200: Permissions response with roles and permission strings.
    """
    user_payload = request.user_payload  # type: ignore[attr-defined]
    service = await _get_service()
    result = await service.get_permissions(user_payload.sub)
    return Response(result)


def _parse_bool(value: str | None) -> bool | None:
    """Parse a string query parameter to boolean.

    Args:
        value: String value ('true', 'false', '1', '0') or None.

    Returns:
        Parsed boolean or None if input is None.
    """
    if value is None:
        return None
    return value.lower() in ("true", "1", "yes")
