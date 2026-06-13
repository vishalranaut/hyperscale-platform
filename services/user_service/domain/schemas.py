"""HyperScale Platform — User Service Pydantic Schemas.

Request and response schemas for the User Service REST API.
All schemas use Pydantic v2 with strict validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth Schemas ─────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """User registration request payload.

    Attributes:
        email: Valid email address.
        password: Minimum 8 characters with complexity requirements.
        full_name: User's display name (2-100 characters).
        phone: Optional phone number.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: str = ""

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce password complexity requirements.

        Args:
            v: The password string to validate.

        Returns:
            The validated password string.

        Raises:
            ValueError: If the password doesn't meet complexity rules.
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Sanitize the full name field.

        Args:
            v: The name string to validate.

        Returns:
            Stripped and validated name.
        """
        return v.strip()


class LoginRequest(BaseModel):
    """User login request payload.

    Attributes:
        email: The user's email address.
        password: The user's password.
    """

    email: EmailStr
    password: str = Field(..., min_length=1)


class OAuthLoginRequest(BaseModel):
    """OAuth login request payload.

    Attributes:
        provider: The OAuth provider name.
        token: The OAuth access token or ID token from the provider.
        redirect_uri: The OAuth redirect URI used in the flow.
    """

    provider: str
    token: str
    redirect_uri: str = ""


class RefreshTokenRequest(BaseModel):
    """Token refresh request payload.

    Attributes:
        refresh_token: The JWT refresh token.
    """

    refresh_token: str


class AuthResponse(BaseModel):
    """Authentication response with JWT tokens.

    Attributes:
        access_token: Short-lived JWT access token.
        refresh_token: Long-lived JWT refresh token.
        token_type: Always "Bearer".
        expires_in: Access token lifetime in seconds.
        user: Summary of the authenticated user.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserSummary


# ── User Schemas ─────────────────────────────────────────────────────────────


class UserSummary(BaseModel):
    """Compact user representation for auth responses and lists.

    Attributes:
        id: The user's unique ID.
        email: The user's email address.
        full_name: Display name.
        avatar_url: Profile image URL.
        roles: Assigned role names.
        is_verified: Email verification status.
    """

    id: str
    email: str
    full_name: str
    avatar_url: str = ""
    roles: list[str] = Field(default_factory=list)
    is_verified: bool = False


class UserDetailResponse(BaseModel):
    """Full user details response.

    Attributes:
        id: The user's unique ID.
        email: The user's email address.
        phone: Phone number.
        full_name: Display name.
        avatar_url: Profile image URL.
        roles: Assigned role names.
        is_verified: Email verification status.
        is_active: Account active status.
        last_login: Last login timestamp.
        firebase_uid: Firebase Auth UID.
        oauth_providers: Linked OAuth providers.
        created_at: Account creation timestamp.
        updated_at: Last update timestamp.
        metadata: Custom metadata.
        profile: Extended profile (if loaded).
    """

    id: str
    email: str
    phone: str = ""
    full_name: str
    avatar_url: str = ""
    roles: list[str] = Field(default_factory=list)
    is_verified: bool = False
    is_active: bool = True
    last_login: datetime | None = None
    firebase_uid: str | None = None
    oauth_providers: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    profile: UserProfileResponse | None = None


class UserProfileResponse(BaseModel):
    """User profile response.

    Attributes:
        bio: User biography.
        social_links: Social media links.
        preferences: User preferences.
        location: User location.
        timezone: Timezone identifier.
        language: Language code.
    """

    bio: str = ""
    social_links: dict[str, str] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    location: str = ""
    timezone: str = "UTC"
    language: str = "en"


class UpdateProfileRequest(BaseModel):
    """Update user profile request payload.

    All fields are optional — only provided fields are updated.

    Attributes:
        full_name: Updated display name.
        phone: Updated phone number.
        avatar_url: Updated avatar URL.
        bio: Updated biography.
        social_links: Updated social media links.
        preferences: Updated preferences.
        location: Updated location.
        timezone: Updated timezone.
        language: Updated language.
    """

    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    social_links: dict[str, str] | None = None
    preferences: dict[str, Any] | None = None
    location: str | None = None
    timezone: str | None = None
    language: str | None = None


class AssignRoleRequest(BaseModel):
    """Admin request to assign a role to a user.

    Attributes:
        role_name: The role name to assign.
    """

    role_name: str


class ChangePasswordRequest(BaseModel):
    """Change password request payload.

    Attributes:
        current_password: The user's current password.
        new_password: The new password (must meet complexity requirements).
    """

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Enforce password complexity on the new password."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ── Pagination ───────────────────────────────────────────────────────────────


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints.

    Attributes:
        page: 1-based page number.
        page_size: Number of items per page (max 100).
        sort_by: Field to sort by.
        sort_order: Sort direction ('asc' or 'desc').
    """

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = "created_at"
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper.

    Attributes:
        items: List of items for the current page.
        total: Total number of items across all pages.
        page: Current page number.
        page_size: Items per page.
        total_pages: Total number of pages.
        has_next: Whether a next page exists.
        has_previous: Whether a previous page exists.
    """

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


# ── Role Schemas ─────────────────────────────────────────────────────────────


class RoleResponse(BaseModel):
    """Role details response.

    Attributes:
        id: Role document ID.
        name: Unique role identifier.
        display_name: Human-readable name.
        description: Role description.
        permissions: List of permission strings.
        is_system: Whether it's a system role.
        priority: Role priority level.
    """

    id: str
    name: str
    display_name: str = ""
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    is_system: bool = False
    priority: int = 0


class UserSearchFilters(BaseModel):
    """Filters for user search endpoint.

    Attributes:
        query: Free-text search query.
        role: Filter by role name.
        is_active: Filter by active status.
        is_verified: Filter by verification status.
    """

    query: str | None = None
    role: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
