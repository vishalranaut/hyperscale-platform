"""HyperScale Platform — User Service Domain Models.

Beanie ODM document models for MongoDB collections. Defines the
core user, role, permission, and profile entities with their
indexes and validation rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from beanie import Indexed
from pydantic import EmailStr, Field
from pymongo import IndexModel, ASCENDING, DESCENDING

from shared.db.mongodb import BaseDocument


class OAuthProvider(str, Enum):
    """Supported OAuth2 identity providers."""

    GOOGLE = "google"
    GITHUB = "github"
    APPLE = "apple"
    FACEBOOK = "facebook"
    MICROSOFT = "microsoft"


class OAuthConnection(BaseDocument):
    """OAuth provider connection linked to a user account.

    Attributes:
        provider: The OAuth provider name.
        provider_user_id: The user's ID on the provider platform.
        access_token: Encrypted OAuth access token.
        refresh_token: Encrypted OAuth refresh token.
        token_expires_at: When the access token expires.
        profile_data: Raw profile data from the provider.
    """

    provider: OAuthProvider
    provider_user_id: str
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: datetime | None = None
    profile_data: dict[str, Any] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""

        name = "oauth_connections"


class Permission(BaseDocument):
    """Fine-grained permission definition.

    Permissions follow the format 'resource:action' and can include
    conditions for context-aware authorization.

    Attributes:
        resource: The resource name (e.g., 'users', 'products', 'orders').
        action: The action allowed (e.g., 'read', 'write', 'delete', '*').
        conditions: Optional conditions for the permission
            (e.g., {"owner_only": "true"}).
        description: Human-readable description of this permission.

    Example:
        >>> perm = Permission(
        ...     resource="orders",
        ...     action="read",
        ...     conditions={"owner_only": "true"},
        ...     description="Read own orders only",
        ... )
    """

    resource: str
    action: str
    conditions: dict[str, str] = Field(default_factory=dict)
    description: str = ""

    class Settings:
        """Beanie collection settings."""

        name = "permissions"
        indexes = [
            IndexModel(
                [("resource", ASCENDING), ("action", ASCENDING)],
                unique=True,
            ),
        ]

    @property
    def permission_string(self) -> str:
        """Return the permission as a 'resource:action' string."""
        return f"{self.resource}:{self.action}"


class Role(BaseDocument):
    """Role definition for RBAC.

    Roles group permissions together and are assigned to users.
    A user can have multiple roles, and each role can have multiple
    permissions.

    Attributes:
        name: Unique role identifier (e.g., 'admin', 'moderator', 'customer').
        display_name: Human-readable role name.
        description: Description of the role's purpose.
        permissions: List of permission strings (e.g., ['users:read', 'orders:*']).
        is_system: Whether this is a system role that cannot be deleted.
        priority: Role priority for conflict resolution (higher = more privileged).

    Example:
        >>> admin_role = Role(
        ...     name="admin",
        ...     display_name="Administrator",
        ...     permissions=["*:*"],
        ...     is_system=True,
        ...     priority=100,
        ... )
    """

    name: Indexed(str, unique=True)  # type: ignore[valid-type]
    display_name: str = ""
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    is_system: bool = False
    priority: int = Field(default=0, ge=0)

    class Settings:
        """Beanie collection settings."""

        name = "roles"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
        ]


class User(BaseDocument):
    """Core user document.

    Represents a platform user with authentication credentials,
    profile information, and role assignments.

    Attributes:
        email: Unique email address (primary identifier).
        phone: Optional phone number.
        password_hash: Bcrypt-hashed password.
        full_name: Display name.
        avatar_url: URL to the user's profile image.
        roles: List of assigned role names.
        is_verified: Whether the email has been verified.
        is_active: Whether the account is active (can be disabled by admin).
        last_login: Timestamp of the last successful login.
        firebase_uid: Firebase Auth UID (for Firebase-authenticated users).
        oauth_providers: List of linked OAuth provider names.
        metadata: Flexible key-value metadata store.
        verification_token: Token for email verification.
        password_reset_token: Token for password reset flow.
        password_reset_expires: Expiry for the password reset token.
        failed_login_attempts: Counter for brute-force protection.
        locked_until: Account lockout timestamp.

    Example:
        >>> user = User(
        ...     email="john@example.com",
        ...     password_hash="$2b$12$...",
        ...     full_name="John Doe",
        ...     roles=["customer"],
        ... )
    """

    email: Indexed(EmailStr, unique=True)  # type: ignore[valid-type]
    phone: str = ""
    password_hash: str = ""
    full_name: str
    avatar_url: str = ""
    roles: list[str] = Field(default_factory=lambda: ["customer"])
    is_verified: bool = False
    is_active: bool = True
    last_login: datetime | None = None
    firebase_uid: str | None = None
    oauth_providers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Security fields
    verification_token: str | None = None
    password_reset_token: str | None = None
    password_reset_expires: datetime | None = None
    failed_login_attempts: int = 0
    locked_until: datetime | None = None

    class Settings:
        """Beanie collection settings."""

        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("firebase_uid", ASCENDING)], sparse=True),
            IndexModel([("phone", ASCENDING)], sparse=True),
            IndexModel([("roles", ASCENDING)]),
            IndexModel([("is_active", ASCENDING), ("is_deleted", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel(
                [("full_name", "text"), ("email", "text")],
                name="user_text_search",
            ),
        ]

    @property
    def is_locked(self) -> bool:
        """Check if the account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.now(UTC) < self.locked_until

    @property
    def display_roles(self) -> str:
        """Return comma-separated role names for display."""
        return ", ".join(self.roles)


class UserProfile(BaseDocument):
    """Extended user profile with additional personal information.

    Stored separately from the User document for performance — profile
    data is only loaded when specifically requested.

    Attributes:
        user_id: Reference to the parent User document ID.
        bio: User biography / about text.
        social_links: Map of platform name to profile URL.
        preferences: User preference settings.
        location: User's location string.
        timezone: User's timezone (e.g., 'America/New_York').
        language: Preferred language code (e.g., 'en', 'es').
        date_of_birth: Optional date of birth.
        gender: Optional gender identifier.

    Example:
        >>> profile = UserProfile(
        ...     user_id="507f1f77bcf86cd799439011",
        ...     bio="Software engineer and coffee enthusiast",
        ...     social_links={"github": "https://github.com/johndoe"},
        ...     location="San Francisco, CA",
        ... )
    """

    user_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    bio: str = ""
    social_links: dict[str, str] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    location: str = ""
    timezone: str = "UTC"
    language: str = "en"
    date_of_birth: datetime | None = None
    gender: str = ""

    class Settings:
        """Beanie collection settings."""

        name = "user_profiles"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
        ]


# ── Default Roles ────────────────────────────────────────────────────────────

DEFAULT_ROLES: list[dict[str, Any]] = [
    {
        "name": "customer",
        "display_name": "Customer",
        "description": "Standard platform user with basic access",
        "permissions": [
            "users:read_own",
            "users:update_own",
            "products:read",
            "orders:create",
            "orders:read_own",
            "orders:cancel_own",
            "cart:manage",
            "chat:participate",
            "notifications:read_own",
        ],
        "is_system": True,
        "priority": 10,
    },
    {
        "name": "seller",
        "display_name": "Seller",
        "description": "Product seller with catalog management access",
        "permissions": [
            "users:read_own",
            "users:update_own",
            "products:read",
            "products:create",
            "products:update_own",
            "products:delete_own",
            "orders:read_own",
            "inventory:manage_own",
            "analytics:read_own",
            "chat:participate",
            "notifications:read_own",
        ],
        "is_system": True,
        "priority": 30,
    },
    {
        "name": "moderator",
        "display_name": "Moderator",
        "description": "Content and community moderator",
        "permissions": [
            "users:read",
            "users:update_own",
            "products:read",
            "products:moderate",
            "orders:read",
            "chat:moderate",
            "notifications:read_own",
        ],
        "is_system": True,
        "priority": 50,
    },
    {
        "name": "admin",
        "display_name": "Administrator",
        "description": "Full platform administrator with unrestricted access",
        "permissions": ["*:*"],
        "is_system": True,
        "priority": 100,
    },
]
