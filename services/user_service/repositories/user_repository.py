"""HyperScale Platform — User Repository.

Async MongoDB repository implementing the repository pattern for User,
Role, and UserProfile documents. All database access is encapsulated
here — business logic in the service layer never calls the database directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import In, RegEx, Set

from services.user_service.domain.models import Role, User, UserProfile
from shared.logging import get_logger

logger = get_logger(__name__)


class UserRepository:
    """Async repository for User document operations.

    Encapsulates all MongoDB interactions for the User collection.
    All methods are async and return domain model instances.

    Example:
        >>> repo = UserRepository()
        >>> user = await repo.create(
        ...     email="john@example.com",
        ...     password_hash="$2b$12$...",
        ...     full_name="John Doe",
        ... )
        >>> found = await repo.get_by_email("john@example.com")
    """

    async def create(
        self,
        email: str,
        password_hash: str,
        full_name: str,
        phone: str = "",
        roles: list[str] | None = None,
        firebase_uid: str | None = None,
        oauth_providers: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        verification_token: str | None = None,
    ) -> User:
        """Create a new user document.

        Args:
            email: Unique email address.
            password_hash: Pre-hashed password string.
            full_name: User's display name.
            phone: Optional phone number.
            roles: List of role names (defaults to ['customer']).
            firebase_uid: Optional Firebase Auth UID.
            oauth_providers: Optional list of OAuth provider names.
            metadata: Optional metadata dictionary.
            verification_token: Optional email verification token.

        Returns:
            The created User document.

        Example:
            >>> user = await repo.create(
            ...     email="new@example.com",
            ...     password_hash=hash_password("secret"),
            ...     full_name="New User",
            ... )
        """
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            phone=phone,
            roles=roles or ["customer"],
            firebase_uid=firebase_uid,
            oauth_providers=oauth_providers or [],
            metadata=metadata or {},
            verification_token=verification_token,
        )
        await user.insert()
        logger.info("user_created", user_id=str(user.id), email=email)
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        """Get a user by their document ID.

        Args:
            user_id: The user's ObjectId string.

        Returns:
            The User document if found and active, None otherwise.
        """
        try:
            user = await User.get(PydanticObjectId(user_id))
            if user and not user.is_deleted:
                return user
            return None
        except Exception:
            return None

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address.

        Args:
            email: The email address to search for.

        Returns:
            The User document if found, None otherwise.
        """
        return await User.find_one(
            User.email == email.lower(),
            User.is_deleted == False,  # noqa: E712
        )

    async def get_by_firebase_uid(self, firebase_uid: str) -> User | None:
        """Get a user by their Firebase UID.

        Args:
            firebase_uid: The Firebase Auth UID.

        Returns:
            The User document if found, None otherwise.
        """
        return await User.find_one(
            User.firebase_uid == firebase_uid,
            User.is_deleted == False,  # noqa: E712
        )

    async def update(self, user_id: str, **fields: Any) -> User | None:
        """Update specific fields on a user document.

        Args:
            user_id: The user's ObjectId string.
            **fields: Field name/value pairs to update.

        Returns:
            The updated User document, or None if not found.

        Example:
            >>> updated = await repo.update(
            ...     user_id="abc123",
            ...     full_name="Updated Name",
            ...     is_verified=True,
            ... )
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        fields["updated_at"] = datetime.now(UTC)
        await user.update(Set(fields))
        await user.sync()
        logger.info("user_updated", user_id=user_id, fields=list(fields.keys()))
        return user

    async def soft_delete(self, user_id: str) -> bool:
        """Soft-delete a user by setting is_deleted=True.

        Args:
            user_id: The user's ObjectId string.

        Returns:
            True if the user was found and deleted, False otherwise.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return False

        await user.soft_delete()
        logger.info("user_soft_deleted", user_id=user_id)
        return True

    async def search(
        self,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        is_verified: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[User], int]:
        """Search users with filters and pagination.

        Args:
            query: Free-text search on name and email.
            role: Filter by role name.
            is_active: Filter by active status.
            is_verified: Filter by verification status.
            page: 1-based page number.
            page_size: Items per page.
            sort_by: Field to sort by.
            sort_order: 'asc' or 'desc'.

        Returns:
            Tuple of (list of users, total count).
        """
        filters: list[Any] = [User.is_deleted == False]  # noqa: E712

        if query:
            filters.append(
                {"$or": [
                    {"full_name": {"$regex": query, "$options": "i"}},
                    {"email": {"$regex": query, "$options": "i"}},
                ]}
            )

        if role:
            filters.append(In(User.roles, [role]))

        if is_active is not None:
            filters.append(User.is_active == is_active)

        if is_verified is not None:
            filters.append(User.is_verified == is_verified)

        # Build sort specification
        sort_prefix = "-" if sort_order == "desc" else "+"
        sort_spec = f"{sort_prefix}{sort_by}"

        # Execute query with pagination
        total = await User.find(*filters).count()
        skip = (page - 1) * page_size
        users = await User.find(*filters).sort(sort_spec).skip(skip).limit(page_size).to_list()

        return users, total

    async def bulk_get(self, user_ids: list[str]) -> list[User]:
        """Get multiple users by their IDs.

        Args:
            user_ids: List of user ObjectId strings.

        Returns:
            List of found User documents (missing IDs are silently skipped).
        """
        object_ids = [PydanticObjectId(uid) for uid in user_ids]
        users = await User.find(
            In(User.id, object_ids),
            User.is_deleted == False,  # noqa: E712
        ).to_list()
        return users

    async def update_last_login(self, user_id: str) -> None:
        """Update the last_login timestamp for a user.

        Args:
            user_id: The user's ObjectId string.
        """
        await self.update(user_id, last_login=datetime.now(UTC))

    async def increment_failed_logins(self, user_id: str) -> int:
        """Increment the failed login counter and return the new count.

        Args:
            user_id: The user's ObjectId string.

        Returns:
            The new failed login attempt count.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return 0

        new_count = user.failed_login_attempts + 1
        await self.update(user_id, failed_login_attempts=new_count)
        return new_count

    async def reset_failed_logins(self, user_id: str) -> None:
        """Reset the failed login counter to zero.

        Args:
            user_id: The user's ObjectId string.
        """
        await self.update(user_id, failed_login_attempts=0, locked_until=None)

    async def count_by_role(self, role: str) -> int:
        """Count users with a specific role.

        Args:
            role: The role name to count.

        Returns:
            Number of active users with the specified role.
        """
        return await User.find(
            In(User.roles, [role]),
            User.is_deleted == False,  # noqa: E712
        ).count()


class RoleRepository:
    """Async repository for Role document operations.

    Example:
        >>> repo = RoleRepository()
        >>> admin_role = await repo.get_by_name("admin")
        >>> all_roles = await repo.get_all()
    """

    async def get_by_name(self, name: str) -> Role | None:
        """Get a role by its unique name.

        Args:
            name: The role name (e.g., 'admin', 'customer').

        Returns:
            The Role document if found, None otherwise.
        """
        return await Role.find_one(
            Role.name == name,
            Role.is_deleted == False,  # noqa: E712
        )

    async def get_all(self) -> list[Role]:
        """Get all active roles sorted by priority.

        Returns:
            List of all Role documents.
        """
        return await Role.find(
            Role.is_deleted == False,  # noqa: E712
        ).sort("-priority").to_list()

    async def create(self, **fields: Any) -> Role:
        """Create a new role.

        Args:
            **fields: Role field values.

        Returns:
            The created Role document.
        """
        role = Role(**fields)
        await role.insert()
        logger.info("role_created", role_name=role.name)
        return role

    async def get_permissions_for_roles(self, role_names: list[str]) -> list[str]:
        """Get all permissions for a list of role names.

        Args:
            role_names: List of role names to look up.

        Returns:
            Deduplicated list of permission strings.
        """
        roles = await Role.find(
            In(Role.name, role_names),
            Role.is_deleted == False,  # noqa: E712
        ).to_list()

        permissions: set[str] = set()
        for role in roles:
            permissions.update(role.permissions)
        return list(permissions)


class UserProfileRepository:
    """Async repository for UserProfile document operations.

    Example:
        >>> repo = UserProfileRepository()
        >>> profile = await repo.get_by_user_id("user123")
        >>> await repo.upsert("user123", bio="Hello world")
    """

    async def get_by_user_id(self, user_id: str) -> UserProfile | None:
        """Get a profile by user ID.

        Args:
            user_id: The associated user's ID.

        Returns:
            The UserProfile document if found, None otherwise.
        """
        return await UserProfile.find_one(
            UserProfile.user_id == user_id,
            UserProfile.is_deleted == False,  # noqa: E712
        )

    async def upsert(self, user_id: str, **fields: Any) -> UserProfile:
        """Create or update a user profile.

        Args:
            user_id: The associated user's ID.
            **fields: Profile field values to set.

        Returns:
            The created or updated UserProfile document.
        """
        profile = await self.get_by_user_id(user_id)

        if profile is None:
            profile = UserProfile(user_id=user_id, **fields)
            await profile.insert()
            logger.info("profile_created", user_id=user_id)
        else:
            fields["updated_at"] = datetime.now(UTC)
            await profile.update(Set(fields))
            await profile.sync()
            logger.info("profile_updated", user_id=user_id)

        return profile

    async def delete_by_user_id(self, user_id: str) -> bool:
        """Soft-delete a profile by user ID.

        Args:
            user_id: The associated user's ID.

        Returns:
            True if found and deleted, False otherwise.
        """
        profile = await self.get_by_user_id(user_id)
        if profile:
            await profile.soft_delete()
            return True
        return False
