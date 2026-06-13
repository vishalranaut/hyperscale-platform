"""HyperScale Platform — User Service Unit Tests.

Tests for the UserService business logic layer with mocked repositories.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.user_service.domain.schemas import UpdateProfileRequest
from services.user_service.services.user_service import UserService


@pytest.fixture
def mock_user_repo():
    """Create a mocked UserRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_role_repo():
    """Create a mocked RoleRepository."""
    repo = AsyncMock()
    repo.get_permissions_for_roles = AsyncMock(return_value=["users:read", "orders:create"])
    return repo


@pytest.fixture
def mock_profile_repo():
    """Create a mocked UserProfileRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_jwt_handler():
    """Create a mocked JWTHandler."""
    handler = AsyncMock()
    handler.create_token_pair = AsyncMock(return_value=MagicMock(
        access_token="mock_access_token",
        refresh_token="mock_refresh_token",
        expires_in=1800,
    ))
    handler.blacklist_token = AsyncMock()
    handler.decode_token = MagicMock()
    return handler


@pytest.fixture
def mock_kafka_producer():
    """Create a mocked KafkaEventProducer."""
    producer = AsyncMock()
    producer.publish = AsyncMock()
    return producer


@pytest.fixture
def user_service(
    mock_user_repo,
    mock_role_repo,
    mock_profile_repo,
    mock_jwt_handler,
    mock_kafka_producer,
):
    """Create a UserService with all mocked dependencies."""
    return UserService(
        user_repo=mock_user_repo,
        role_repo=mock_role_repo,
        profile_repo=mock_profile_repo,
        jwt_handler=mock_jwt_handler,
        kafka_producer=mock_kafka_producer,
    )


class TestUserRegistration:
    """Tests for user registration flow."""

    @pytest.mark.asyncio
    async def test_register_success(self, user_service, mock_user_repo):
        """Test successful user registration."""
        mock_user_repo.get_by_email.return_value = None
        mock_user = MagicMock()
        mock_user.id = "new_user_id"
        mock_user.email = "john@example.com"
        mock_user.full_name = "John Doe"
        mock_user.avatar_url = ""
        mock_user.roles = ["customer"]
        mock_user.is_verified = False
        mock_user_repo.create.return_value = mock_user

        result = await user_service.register(
            email="john@example.com",
            password="SecurePass123!",
            full_name="John Doe",
        )

        assert result.access_token == "mock_access_token"
        assert result.refresh_token == "mock_refresh_token"
        assert result.user.email == "john@example.com"
        mock_user_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, user_service, mock_user_repo):
        """Test registration with already registered email."""
        mock_user_repo.get_by_email.return_value = MagicMock()

        from shared.exceptions import ConflictError

        with pytest.raises(ConflictError):
            await user_service.register(
                email="existing@example.com",
                password="SecurePass123!",
                full_name="Test User",
            )


class TestUserLogin:
    """Tests for user login flow."""

    @pytest.mark.asyncio
    async def test_login_success(self, user_service, mock_user_repo):
        """Test successful login with valid credentials."""
        mock_user = MagicMock()
        mock_user.id = "user_123"
        mock_user.email = "john@example.com"
        mock_user.full_name = "John Doe"
        mock_user.password_hash = "$2b$12$LJ3m4y1aITDrK.g3j1Cq8OFcHW0p55/bsQmqZCXs9.KJ8rKHKXxG"
        mock_user.is_active = True
        mock_user.is_locked = False
        mock_user.locked_until = None
        mock_user.roles = ["customer"]
        mock_user.avatar_url = ""
        mock_user.is_verified = True
        mock_user.failed_login_attempts = 0
        mock_user_repo.get_by_email.return_value = mock_user

        with patch.object(user_service, "_verify_password", return_value=True):
            result = await user_service.login("john@example.com", "password")

        assert result.access_token == "mock_access_token"
        assert result.user.id == "user_123"

    @pytest.mark.asyncio
    async def test_login_invalid_email(self, user_service, mock_user_repo):
        """Test login with non-existent email."""
        mock_user_repo.get_by_email.return_value = None

        from shared.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            await user_service.login("nobody@example.com", "password")

    @pytest.mark.asyncio
    async def test_login_inactive_account(self, user_service, mock_user_repo):
        """Test login with deactivated account."""
        mock_user = MagicMock()
        mock_user.is_active = False
        mock_user_repo.get_by_email.return_value = mock_user

        from shared.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError, match="deactivated"):
            await user_service.login("inactive@example.com", "password")


class TestUserProfile:
    """Tests for user profile operations."""

    @pytest.mark.asyncio
    async def test_get_user_success(self, user_service, mock_user_repo, mock_profile_repo):
        """Test getting user details."""
        mock_user = MagicMock()
        mock_user.id = "user_123"
        mock_user.email = "john@example.com"
        mock_user.full_name = "John Doe"
        mock_user.phone = ""
        mock_user.avatar_url = ""
        mock_user.roles = ["customer"]
        mock_user.is_verified = True
        mock_user.is_active = True
        mock_user.last_login = None
        mock_user.firebase_uid = None
        mock_user.oauth_providers = []
        mock_user.created_at = datetime.now(UTC)
        mock_user.updated_at = datetime.now(UTC)
        mock_user.metadata = {}
        mock_user_repo.get_by_id.return_value = mock_user
        mock_profile_repo.get_by_user_id.return_value = None

        result = await user_service.get_user("user_123")

        assert result.id == "user_123"
        assert result.email == "john@example.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, user_service, mock_user_repo):
        """Test getting non-existent user."""
        mock_user_repo.get_by_id.return_value = None

        from shared.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await user_service.get_user("nonexistent")

    @pytest.mark.asyncio
    async def test_update_profile(self, user_service, mock_user_repo, mock_profile_repo):
        """Test updating user profile."""
        mock_user = MagicMock()
        mock_user.id = "user_123"
        mock_user.email = "john@example.com"
        mock_user.full_name = "John Updated"
        mock_user.phone = ""
        mock_user.avatar_url = ""
        mock_user.roles = ["customer"]
        mock_user.is_verified = True
        mock_user.is_active = True
        mock_user.last_login = None
        mock_user.firebase_uid = None
        mock_user.oauth_providers = []
        mock_user.created_at = datetime.now(UTC)
        mock_user.updated_at = datetime.now(UTC)
        mock_user.metadata = {}
        mock_user_repo.get_by_id.return_value = mock_user
        mock_profile_repo.get_by_user_id.return_value = None

        data = UpdateProfileRequest(full_name="John Updated", bio="New bio")

        with patch("services.user_service.services.user_service.invalidate_cache", new_callable=AsyncMock):
            result = await user_service.update_profile("user_123", data)

        assert result.full_name == "John Updated"


class TestRoleAssignment:
    """Tests for role assignment."""

    @pytest.mark.asyncio
    async def test_assign_role(self, user_service, mock_user_repo, mock_role_repo):
        """Test assigning a role to a user."""
        mock_user = MagicMock()
        mock_user.id = "user_123"
        mock_user.email = "john@example.com"
        mock_user.full_name = "John Doe"
        mock_user.phone = ""
        mock_user.avatar_url = ""
        mock_user.roles = ["customer"]
        mock_user.is_verified = True
        mock_user.is_active = True
        mock_user.last_login = None
        mock_user.firebase_uid = None
        mock_user.oauth_providers = []
        mock_user.created_at = datetime.now(UTC)
        mock_user.updated_at = datetime.now(UTC)
        mock_user.metadata = {}
        mock_user_repo.get_by_id.return_value = mock_user

        mock_role = MagicMock()
        mock_role.name = "admin"
        mock_role_repo.get_by_name.return_value = mock_role

        with patch("services.user_service.services.user_service.invalidate_cache", new_callable=AsyncMock):
            result = await user_service.assign_role("user_123", "admin", "admin_user_id")

        mock_user_repo.update.assert_called()


class TestTokenOperations:
    """Tests for token-related operations."""

    @pytest.mark.asyncio
    async def test_logout_blacklists_token(self, user_service, mock_jwt_handler):
        """Test that logout blacklists the access token."""
        await user_service.logout("some_access_token")
        mock_jwt_handler.blacklist_token.assert_called_once_with("some_access_token")
