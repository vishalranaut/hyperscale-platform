"""HyperScale Platform — User Service Business Logic.

Service layer implementing all user management operations. Orchestrates
repository calls, authentication, caching, and Kafka event emission.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from passlib.hash import bcrypt

from services.user_service.domain.models import User, UserProfile
from services.user_service.domain.schemas import (
    AuthResponse,
    PaginatedResponse,
    UpdateProfileRequest,
    UserDetailResponse,
    UserProfileResponse,
    UserSummary,
)
from services.user_service.repositories.user_repository import (
    RoleRepository,
    UserProfileRepository,
    UserRepository,
)
from shared.auth.jwt_handler import JWTHandler
from shared.cache.redis_client import cache_aside, get_redis_client, invalidate_cache
from shared.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from shared.kafka.producer import KafkaEventProducer
from shared.kafka.schemas import KafkaTopics, UserEvents
from shared.logging import get_logger

logger = get_logger(__name__)

# Maximum failed login attempts before account lockout
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION_MINUTES = 30


class UserService:
    """Business logic layer for user management.

    Coordinates authentication, profile management, role assignment,
    and event emission. All database access goes through repositories.

    Args:
        user_repo: User repository instance.
        role_repo: Role repository instance.
        profile_repo: UserProfile repository instance.
        jwt_handler: JWT token handler instance.
        kafka_producer: Kafka event producer (optional, for testing).

    Example:
        >>> service = UserService(
        ...     user_repo=UserRepository(),
        ...     role_repo=RoleRepository(),
        ...     profile_repo=UserProfileRepository(),
        ...     jwt_handler=JWTHandler(redis_client=redis),
        ... )
        >>> auth = await service.register("john@example.com", "Pass1234!", "John")
    """

    def __init__(
        self,
        user_repo: UserRepository,
        role_repo: RoleRepository,
        profile_repo: UserProfileRepository,
        jwt_handler: JWTHandler,
        kafka_producer: KafkaEventProducer | None = None,
    ) -> None:
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._profile_repo = profile_repo
        self._jwt = jwt_handler
        self._kafka = kafka_producer

    async def _get_kafka(self) -> KafkaEventProducer:
        """Get or create the Kafka producer.

        Returns:
            The Kafka event producer instance.
        """
        if self._kafka is None:
            self._kafka = await KafkaEventProducer.get_instance()
        return self._kafka

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: The plain-text password.

        Returns:
            The bcrypt-hashed password string.
        """
        return bcrypt.hash(password)

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash.

        Args:
            password: The plain-text password to verify.
            password_hash: The stored bcrypt hash.

        Returns:
            True if the password matches.
        """
        return bcrypt.verify(password, password_hash)

    def _user_to_summary(self, user: User) -> UserSummary:
        """Convert a User document to a UserSummary schema.

        Args:
            user: The User document.

        Returns:
            A UserSummary Pydantic model.
        """
        return UserSummary(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            roles=user.roles,
            is_verified=user.is_verified,
        )

    def _user_to_detail(
        self, user: User, profile: UserProfile | None = None
    ) -> UserDetailResponse:
        """Convert a User document to a full detail response.

        Args:
            user: The User document.
            profile: Optional UserProfile document to include.

        Returns:
            A UserDetailResponse Pydantic model.
        """
        profile_response = None
        if profile:
            profile_response = UserProfileResponse(
                bio=profile.bio,
                social_links=profile.social_links,
                preferences=profile.preferences,
                location=profile.location,
                timezone=profile.timezone,
                language=profile.language,
            )

        return UserDetailResponse(
            id=str(user.id),
            email=user.email,
            phone=user.phone,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            roles=user.roles,
            is_verified=user.is_verified,
            is_active=user.is_active,
            last_login=user.last_login,
            firebase_uid=user.firebase_uid,
            oauth_providers=user.oauth_providers,
            created_at=user.created_at,
            updated_at=user.updated_at,
            metadata=user.metadata,
            profile=profile_response,
        )

    async def register(
        self,
        email: str,
        password: str,
        full_name: str,
        phone: str = "",
    ) -> AuthResponse:
        """Register a new user account.

        Creates the user, generates JWT tokens, and emits a
        user.registered Kafka event (triggering welcome email).

        Args:
            email: The user's email address.
            password: Plain-text password (will be hashed).
            full_name: The user's display name.
            phone: Optional phone number.

        Returns:
            AuthResponse with JWT tokens and user summary.

        Raises:
            ConflictError: If the email is already registered.
        """
        # Check for existing user
        existing = await self._user_repo.get_by_email(email.lower())
        if existing:
            raise ConflictError(
                message="Email already registered",
                detail={"email": email},
            )

        # Create user with hashed password
        verification_token = str(uuid.uuid4())
        user = await self._user_repo.create(
            email=email.lower(),
            password_hash=self._hash_password(password),
            full_name=full_name,
            phone=phone,
            verification_token=verification_token,
        )

        # Create empty profile
        await self._profile_repo.upsert(str(user.id))

        # Generate tokens
        token_pair = await self._jwt.create_token_pair(
            {
                "sub": str(user.id),
                "email": user.email,
                "roles": user.roles,
            }
        )

        # Emit registration event
        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.USER_EVENTS,
                event_type=UserEvents.REGISTERED,
                payload={
                    "user_id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "verification_token": verification_token,
                },
                key=str(user.id),
            )
        except Exception as e:
            logger.error("kafka_publish_failed", event="user.registered", error=str(e))

        logger.info("user_registered", user_id=str(user.id), email=email)

        return AuthResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
            user=self._user_to_summary(user),
        )

    async def login(self, email: str, password: str) -> AuthResponse:
        """Authenticate a user with email and password.

        Validates credentials, checks account status, generates JWT
        tokens, and emits a user.login event.

        Args:
            email: The user's email address.
            password: The user's plain-text password.

        Returns:
            AuthResponse with JWT tokens and user summary.

        Raises:
            AuthenticationError: If credentials are invalid or account is locked.
        """
        user = await self._user_repo.get_by_email(email.lower())
        if user is None:
            raise AuthenticationError(message="Invalid email or password")

        if not user.is_active:
            raise AuthenticationError(
                message="Account is deactivated",
                code="ACCOUNT_DEACTIVATED",
            )

        if user.is_locked:
            raise AuthenticationError(
                message="Account is temporarily locked due to too many failed attempts",
                code="ACCOUNT_LOCKED",
                detail={"locked_until": user.locked_until.isoformat() if user.locked_until else ""},
            )

        if not self._verify_password(password, user.password_hash):
            # Increment failed login counter
            count = await self._user_repo.increment_failed_logins(str(user.id))
            if count >= MAX_FAILED_LOGINS:
                locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                await self._user_repo.update(str(user.id), locked_until=locked_until)
                logger.warning("account_locked", user_id=str(user.id), failed_attempts=count)

            raise AuthenticationError(message="Invalid email or password")

        # Reset failed login counter on success
        await self._user_repo.reset_failed_logins(str(user.id))
        await self._user_repo.update_last_login(str(user.id))

        # Get permissions for token
        permissions = await self._role_repo.get_permissions_for_roles(user.roles)

        # Generate tokens
        token_pair = await self._jwt.create_token_pair(
            {
                "sub": str(user.id),
                "email": user.email,
                "roles": user.roles,
                "permissions": permissions,
            }
        )

        # Emit login event
        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.USER_EVENTS,
                event_type=UserEvents.LOGIN,
                payload={
                    "user_id": str(user.id),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                key=str(user.id),
            )
        except Exception as e:
            logger.error("kafka_publish_failed", event="user.login", error=str(e))

        logger.info("user_login", user_id=str(user.id))

        return AuthResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
            user=self._user_to_summary(user),
        )

    async def oauth_login(
        self,
        provider: str,
        token: str,
    ) -> AuthResponse:
        """Authenticate or register via OAuth provider.

        If the user exists (by email from provider profile), returns
        tokens. Otherwise creates a new account.

        Args:
            provider: OAuth provider name (e.g., 'google', 'github').
            token: The OAuth access or ID token.

        Returns:
            AuthResponse with JWT tokens.

        Raises:
            AuthenticationError: If the OAuth token is invalid.
        """
        from shared.auth.jwt_handler import verify_firebase_token

        # Verify Firebase token (works for Google, Apple, etc.)
        try:
            firebase_claims = await verify_firebase_token(token)
        except Exception:
            raise AuthenticationError(
                message=f"Invalid {provider} token",
                code="OAUTH_TOKEN_INVALID",
            )

        email = firebase_claims.get("email", "")
        firebase_uid = firebase_claims.get("uid", "")
        name = firebase_claims.get("name", email.split("@")[0])
        avatar = firebase_claims.get("picture", "")

        if not email:
            raise AuthenticationError(
                message="OAuth provider did not return an email",
                code="OAUTH_NO_EMAIL",
            )

        # Look up existing user
        user = await self._user_repo.get_by_email(email.lower())

        if user is None:
            # Create new user from OAuth
            user = await self._user_repo.create(
                email=email.lower(),
                password_hash="",  # No password for OAuth users
                full_name=name,
                firebase_uid=firebase_uid,
                oauth_providers=[provider],
                metadata={"oauth_avatar": avatar},
            )
            await self._user_repo.update(str(user.id), is_verified=True)
            await self._profile_repo.upsert(str(user.id))

            try:
                kafka = await self._get_kafka()
                await kafka.publish(
                    topic=KafkaTopics.USER_EVENTS,
                    event_type=UserEvents.REGISTERED,
                    payload={
                        "user_id": str(user.id),
                        "email": user.email,
                        "full_name": user.full_name,
                        "provider": provider,
                    },
                    key=str(user.id),
                )
            except Exception as e:
                logger.error("kafka_publish_failed", error=str(e))
        else:
            # Update existing user with OAuth info
            updates: dict[str, Any] = {}
            if firebase_uid and not user.firebase_uid:
                updates["firebase_uid"] = firebase_uid
            if provider not in user.oauth_providers:
                updates["oauth_providers"] = [*user.oauth_providers, provider]
            if updates:
                await self._user_repo.update(str(user.id), **updates)

        permissions = await self._role_repo.get_permissions_for_roles(user.roles)
        token_pair = await self._jwt.create_token_pair(
            {
                "sub": str(user.id),
                "email": user.email,
                "roles": user.roles,
                "permissions": permissions,
            }
        )

        return AuthResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
            user=self._user_to_summary(user),
        )

    async def verify_email(self, token: str) -> bool:
        """Verify a user's email using the verification token.

        Args:
            token: The verification token from the email link.

        Returns:
            True if verification succeeded.

        Raises:
            NotFoundError: If no user matches the token.
        """
        user = await User.find_one(
            User.verification_token == token,
            User.is_deleted == False,  # noqa: E712
        )

        if user is None:
            raise NotFoundError(
                message="Invalid verification token",
                detail={"token": "not_found"},
            )

        await self._user_repo.update(
            str(user.id),
            is_verified=True,
            verification_token=None,
        )

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.USER_EVENTS,
                event_type=UserEvents.VERIFIED,
                payload={"user_id": str(user.id)},
                key=str(user.id),
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        logger.info("email_verified", user_id=str(user.id))
        return True

    async def refresh_token(self, refresh_token: str) -> AuthResponse:
        """Issue new JWT tokens using a valid refresh token.

        Args:
            refresh_token: The JWT refresh token.

        Returns:
            AuthResponse with new JWT tokens.

        Raises:
            AuthenticationError: If the refresh token is invalid or expired.
        """
        payload = self._jwt.decode_token(refresh_token)

        if payload.token_type.value != "refresh":
            raise AuthenticationError(
                message="Invalid token type",
                code="INVALID_TOKEN_TYPE",
            )

        user = await self._user_repo.get_by_id(payload.sub)
        if user is None:
            raise AuthenticationError(message="User not found")

        if not user.is_active:
            raise AuthenticationError(message="Account is deactivated")

        permissions = await self._role_repo.get_permissions_for_roles(user.roles)
        token_pair = await self._jwt.create_token_pair(
            {
                "sub": str(user.id),
                "email": user.email,
                "roles": user.roles,
                "permissions": permissions,
            }
        )

        return AuthResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
            user=self._user_to_summary(user),
        )

    async def logout(self, access_token: str) -> None:
        """Log out a user by blacklisting their access token.

        Args:
            access_token: The JWT access token to blacklist.
        """
        await self._jwt.blacklist_token(access_token)
        logger.info("user_logout")

    async def get_user(self, user_id: str) -> UserDetailResponse:
        """Get full user details including profile.

        Args:
            user_id: The user's ID.

        Returns:
            Full user detail response.

        Raises:
            NotFoundError: If the user is not found.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(detail={"resource": "User", "id": user_id})

        profile = await self._profile_repo.get_by_user_id(user_id)
        return self._user_to_detail(user, profile)

    async def update_profile(
        self,
        user_id: str,
        data: UpdateProfileRequest,
    ) -> UserDetailResponse:
        """Update a user's profile information.

        Args:
            user_id: The user's ID.
            data: The update payload with optional fields.

        Returns:
            Updated user detail response.

        Raises:
            NotFoundError: If the user is not found.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(detail={"resource": "User", "id": user_id})

        # Update User fields
        user_updates: dict[str, Any] = {}
        if data.full_name is not None:
            user_updates["full_name"] = data.full_name
        if data.phone is not None:
            user_updates["phone"] = data.phone
        if data.avatar_url is not None:
            user_updates["avatar_url"] = data.avatar_url

        if user_updates:
            await self._user_repo.update(user_id, **user_updates)

        # Update Profile fields
        profile_updates: dict[str, Any] = {}
        if data.bio is not None:
            profile_updates["bio"] = data.bio
        if data.social_links is not None:
            profile_updates["social_links"] = data.social_links
        if data.preferences is not None:
            profile_updates["preferences"] = data.preferences
        if data.location is not None:
            profile_updates["location"] = data.location
        if data.timezone is not None:
            profile_updates["timezone"] = data.timezone
        if data.language is not None:
            profile_updates["language"] = data.language

        if profile_updates:
            await self._profile_repo.upsert(user_id, **profile_updates)

        # Invalidate permissions cache
        await invalidate_cache("permissions", f"*{user_id}*")

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.USER_EVENTS,
                event_type=UserEvents.PROFILE_UPDATED,
                payload={"user_id": user_id},
                key=user_id,
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        return await self.get_user(user_id)

    async def assign_role(
        self,
        user_id: str,
        role_name: str,
        assigned_by: str,
    ) -> UserDetailResponse:
        """Assign a role to a user (admin only).

        Args:
            user_id: The target user's ID.
            role_name: The role to assign.
            assigned_by: The admin user's ID performing the assignment.

        Returns:
            Updated user detail response.

        Raises:
            NotFoundError: If the user or role is not found.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(detail={"resource": "User", "id": user_id})

        role = await self._role_repo.get_by_name(role_name)
        if role is None:
            raise NotFoundError(
                message=f"Role '{role_name}' not found",
                detail={"resource": "Role", "name": role_name},
            )

        old_roles = list(user.roles)
        if role_name not in user.roles:
            new_roles = [*user.roles, role_name]
            await self._user_repo.update(user_id, roles=new_roles)

        # Invalidate permissions cache
        await invalidate_cache("permissions", f"*{user_id}*")

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.USER_EVENTS,
                event_type=UserEvents.ROLE_CHANGED,
                payload={
                    "user_id": user_id,
                    "old_roles": old_roles,
                    "new_roles": [*old_roles, role_name] if role_name not in old_roles else old_roles,
                    "changed_by": assigned_by,
                },
                key=user_id,
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        logger.info(
            "role_assigned",
            user_id=user_id,
            role=role_name,
            assigned_by=assigned_by,
        )

        return await self.get_user(user_id)

    @cache_aside(ttl=300, namespace="permissions")
    async def get_permissions(self, user_id: str) -> dict[str, Any]:
        """Get all resolved permissions for a user (cached 5 min).

        Args:
            user_id: The user's ID.

        Returns:
            Dictionary with user_id, roles, and permissions lists.

        Raises:
            NotFoundError: If the user is not found.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(detail={"resource": "User", "id": user_id})

        permissions = await self._role_repo.get_permissions_for_roles(user.roles)

        return {
            "user_id": user_id,
            "roles": user.roles,
            "permissions": permissions,
        }

    async def search_users(
        self,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        is_verified: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> PaginatedResponse:
        """Search users with filters and pagination.

        Args:
            query: Free-text search query.
            role: Filter by role name.
            is_active: Filter by active status.
            is_verified: Filter by verification status.
            page: 1-based page number.
            page_size: Items per page.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Paginated response with user summaries.
        """
        users, total = await self._user_repo.search(
            query=query,
            role=role,
            is_active=is_active,
            is_verified=is_verified,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return PaginatedResponse(
            items=[self._user_to_summary(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )
