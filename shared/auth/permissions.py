"""HyperScale Platform — RBAC Permission System.

Role-Based Access Control with fine-grained permissions. Provides
DRF permission classes and a decorator for view-level authorization.

Example:
    >>> @require_permissions("users", "read")
    ... async def list_users(request):
    ...     return await user_service.list_all()
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from shared.exceptions import AuthorizationError
from shared.logging import get_logger

logger = get_logger(__name__)


class PermissionChecker:
    """Evaluates whether a user has the required permissions.

    Supports wildcard permissions (e.g., 'users:*') and conditional
    permissions based on resource ownership.

    Example:
        >>> checker = PermissionChecker()
        >>> checker.has_permission(
        ...     user_permissions=["users:read", "users:write"],
        ...     resource="users",
        ...     action="read",
        ... )
        True
    """

    @staticmethod
    def has_permission(
        user_permissions: list[str],
        resource: str,
        action: str,
        conditions: dict[str, Any] | None = None,
    ) -> bool:
        """Check if the user's permissions include the required access.

        Permission strings follow the format 'resource:action', with
        wildcards supported as 'resource:*' or '*:*'.

        Args:
            user_permissions: List of permission strings the user holds.
            resource: The resource being accessed (e.g., 'users', 'orders').
            action: The action being performed (e.g., 'read', 'write', 'delete').
            conditions: Optional conditions for context-aware authorization
                (e.g., ownership checks).

        Returns:
            True if the user has the required permission.
        """
        required = f"{resource}:{action}"

        for perm in user_permissions:
            # Superadmin wildcard
            if perm == "*:*":
                return True
            # Resource-level wildcard
            if perm == f"{resource}:*":
                return True
            # Exact match
            if perm == required:
                return True

        return False

    @staticmethod
    def has_role(user_roles: list[str], required_role: str) -> bool:
        """Check if the user has a specific role.

        Args:
            user_roles: List of role names assigned to the user.
            required_role: The role name to check for.

        Returns:
            True if the user has the required role.
        """
        return required_role in user_roles

    @staticmethod
    def has_any_role(user_roles: list[str], required_roles: list[str]) -> bool:
        """Check if the user has any of the specified roles.

        Args:
            user_roles: List of role names assigned to the user.
            required_roles: List of role names, at least one must match.

        Returns:
            True if the user has at least one of the required roles.
        """
        return bool(set(user_roles) & set(required_roles))


# ── DRF Permission Classes ───────────────────────────────────────────────────


class IsAuthenticated(BasePermission):
    """DRF permission class requiring a valid authenticated user.

    Checks that request.user is set and has an 'id' attribute,
    indicating successful JWT/Firebase authentication.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if the request is authenticated.

        Args:
            request: The incoming DRF request.
            view: The view being accessed.

        Returns:
            True if the user is authenticated.
        """
        return bool(
            hasattr(request, "user_payload")
            and request.user_payload is not None  # type: ignore[attr-defined]
        )


class HasRole(BasePermission):
    """DRF permission class requiring a specific role.

    Usage:
        >>> class AdminView(APIView):
        ...     permission_classes = [HasRole]
        ...     required_role = "admin"
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if the user has the required role.

        Args:
            request: The incoming DRF request.
            view: The view being accessed (must define required_role).

        Returns:
            True if the user has the required role.
        """
        required_role = getattr(view, "required_role", None)
        if required_role is None:
            logger.warning("has_role_no_required_role", view=view.__class__.__name__)
            return False

        user_payload = getattr(request, "user_payload", None)
        if user_payload is None:
            return False

        user_roles = getattr(user_payload, "roles", [])
        return PermissionChecker.has_role(user_roles, required_role)


class HasPermission(BasePermission):
    """DRF permission class requiring a specific resource:action permission.

    Usage:
        >>> class UserListView(APIView):
        ...     permission_classes = [HasPermission]
        ...     required_permission = ("users", "read")
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if the user has the required permission.

        Args:
            request: The incoming DRF request.
            view: The view being accessed (must define required_permission).

        Returns:
            True if the user has the required permission.
        """
        required_permission = getattr(view, "required_permission", None)
        if required_permission is None:
            logger.warning("has_permission_not_set", view=view.__class__.__name__)
            return False

        resource, action = required_permission
        user_payload = getattr(request, "user_payload", None)
        if user_payload is None:
            return False

        user_permissions = getattr(user_payload, "permissions", [])
        return PermissionChecker.has_permission(user_permissions, resource, action)


class IsAdminUser(BasePermission):
    """DRF permission class requiring the 'admin' role."""

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check if the user is an admin.

        Args:
            request: The incoming DRF request.
            view: The view being accessed.

        Returns:
            True if the user has the 'admin' role.
        """
        user_payload = getattr(request, "user_payload", None)
        if user_payload is None:
            return False
        user_roles = getattr(user_payload, "roles", [])
        return "admin" in user_roles


# ── Decorator ────────────────────────────────────────────────────────────────


def require_permissions(
    resource: str,
    action: str,
    error_message: str | None = None,
) -> Callable:
    """Decorator that enforces permission checks on async view functions.

    Args:
        resource: The resource name (e.g., 'users', 'products').
        action: The action name (e.g., 'read', 'write', 'delete').
        error_message: Custom error message on authorization failure.

    Returns:
        Decorated function with permission enforcement.

    Example:
        >>> @require_permissions("orders", "write")
        ... async def create_order(request):
        ...     ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request from args (DRF view method signature)
            request = None
            for arg in args:
                if hasattr(arg, "user_payload"):
                    request = arg
                    break

            if request is None:
                raise AuthorizationError(
                    message="Request context not found",
                    code="MISSING_AUTH_CONTEXT",
                )

            user_payload = getattr(request, "user_payload", None)
            if user_payload is None:
                raise AuthorizationError(
                    message="Authentication required",
                    code="NOT_AUTHENTICATED",
                )

            user_permissions = getattr(user_payload, "permissions", [])
            if not PermissionChecker.has_permission(user_permissions, resource, action):
                msg = error_message or f"Permission '{resource}:{action}' required"
                logger.warning(
                    "permission_denied",
                    user_id=user_payload.sub,
                    resource=resource,
                    action=action,
                )
                raise AuthorizationError(
                    message=msg,
                    detail={"required": f"{resource}:{action}"},
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_roles(*roles: str, error_message: str | None = None) -> Callable:
    """Decorator that enforces role checks on async view functions.

    Args:
        *roles: One or more role names required (any match is sufficient).
        error_message: Custom error message on authorization failure.

    Returns:
        Decorated function with role enforcement.

    Example:
        >>> @require_roles("admin", "moderator")
        ... async def ban_user(request, user_id):
        ...     ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = None
            for arg in args:
                if hasattr(arg, "user_payload"):
                    request = arg
                    break

            if request is None:
                raise AuthorizationError(
                    message="Request context not found",
                    code="MISSING_AUTH_CONTEXT",
                )

            user_payload = getattr(request, "user_payload", None)
            if user_payload is None:
                raise AuthorizationError(
                    message="Authentication required",
                    code="NOT_AUTHENTICATED",
                )

            user_roles = getattr(user_payload, "roles", [])
            if not PermissionChecker.has_any_role(user_roles, list(roles)):
                msg = error_message or f"One of roles {list(roles)} required"
                logger.warning(
                    "role_denied",
                    user_id=user_payload.sub,
                    required_roles=list(roles),
                    user_roles=user_roles,
                )
                raise AuthorizationError(
                    message=msg,
                    detail={"required_roles": list(roles)},
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
