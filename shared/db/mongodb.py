"""HyperScale Platform — MongoDB / Beanie ODM Utilities.

Provides Motor async client initialization, Beanie ODM setup, and a
base document class with common fields (timestamps, soft delete) used
by all microservice domain models.

Example:
    >>> from shared.db.mongodb import init_mongodb, BaseDocument
    >>> await init_mongodb(
    ...     database_name="hyperscale",
    ...     document_models=[User, Product, Order],
    ... )

    >>> class User(BaseDocument):
    ...     email: str
    ...     full_name: str
    ...
    ...     class Settings:
    ...         name = "users"
    ...         indexes = [
    ...             IndexModel([("email", 1)], unique=True),
    ...         ]
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, ClassVar, Type, TypeVar

from beanie import Document, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import Field

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound="BaseDocument")

# ── Motor Client Singleton ───────────────────────────────────────────────────

_motor_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]
_motor_lock: asyncio.Lock = asyncio.Lock()


async def get_motor_client() -> AsyncIOMotorClient:  # type: ignore[type-arg]
    """Get or create the singleton Motor async MongoDB client.

    Returns:
        Configured AsyncIOMotorClient with connection pooling.
    """
    global _motor_client

    async with _motor_lock:
        if _motor_client is None:
            settings = get_settings()
            _motor_client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                **settings.mongodb_connection_kwargs,
            )
            logger.info(
                "motor_client_initialized",
                url=settings.MONGODB_URL,
                min_pool=settings.MONGODB_MIN_POOL_SIZE,
                max_pool=settings.MONGODB_MAX_POOL_SIZE,
            )
        return _motor_client


async def close_motor_client() -> None:
    """Close the Motor client and release connections.

    Should be called during application shutdown.
    """
    global _motor_client
    if _motor_client is not None:
        _motor_client.close()
        _motor_client = None
        logger.info("motor_client_closed")


# ── Beanie Initialization ───────────────────────────────────────────────────


async def init_mongodb(
    database_name: str | None = None,
    document_models: list[Type[Document]] | None = None,
    motor_client: AsyncIOMotorClient | None = None,  # type: ignore[type-arg]
) -> None:
    """Initialize Beanie ODM with the specified document models.

    Creates the Motor client (if not provided), selects the database,
    and initializes Beanie with all document models for automatic
    collection and index management.

    Args:
        database_name: MongoDB database name. Defaults to settings.MONGODB_DATABASE.
        document_models: List of Beanie Document classes to register.
            Defaults to an empty list.
        motor_client: Optional pre-configured Motor client. If None,
            creates one using settings.

    Example:
        >>> from services.user_service.domain.models import User, Role
        >>> await init_mongodb(document_models=[User, Role])
    """
    settings = get_settings()
    db_name = database_name or settings.MONGODB_DATABASE
    client = motor_client or await get_motor_client()
    models = document_models or []

    database = client[db_name]

    await init_beanie(
        database=database,
        document_models=models,
    )

    logger.info(
        "beanie_initialized",
        database=db_name,
        models=[m.__name__ for m in models],
    )


# ── Base Document ────────────────────────────────────────────────────────────


class BaseDocument(Document):
    """Base document class for all HyperScale MongoDB collections.

    Provides common fields for timestamping, soft deletion, and
    optimistic locking. All domain models should inherit from this.

    Attributes:
        created_at: UTC timestamp of document creation.
        updated_at: UTC timestamp of last modification.
        is_deleted: Soft-delete flag. Documents with is_deleted=True
            are excluded from default queries.
        version: Document version for optimistic locking.

    Example:
        >>> class Product(BaseDocument):
        ...     title: str
        ...     price: float
        ...
        ...     class Settings:
        ...         name = "products"
    """

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_deleted: bool = Field(default=False)
    version: int = Field(default=1)

    # Class-level flag for soft delete filtering
    _use_soft_delete: ClassVar[bool] = True

    class Settings:
        """Beanie document settings."""

        use_state_management = True
        validate_on_save = True

    async def soft_delete(self) -> None:
        """Soft-delete this document by setting is_deleted=True.

        Also updates the updated_at timestamp. The document remains
        in the database but is excluded from default queries.

        Example:
            >>> user = await User.get(user_id)
            >>> await user.soft_delete()
        """
        self.is_deleted = True
        self.updated_at = datetime.now(UTC)
        await self.save()
        logger.info(
            "document_soft_deleted",
            collection=self.__class__.__name__,
            document_id=str(self.id),
        )

    async def restore(self) -> None:
        """Restore a soft-deleted document.

        Sets is_deleted back to False and updates the timestamp.

        Example:
            >>> user = await User.get(user_id)
            >>> await user.restore()
        """
        self.is_deleted = False
        self.updated_at = datetime.now(UTC)
        await self.save()
        logger.info(
            "document_restored",
            collection=self.__class__.__name__,
            document_id=str(self.id),
        )

    async def update_with_version(self, **fields: Any) -> "BaseDocument":
        """Update document fields with optimistic locking.

        Increments the version and checks that the current version
        matches the expected version to prevent stale writes.

        Args:
            **fields: Field name/value pairs to update.

        Returns:
            The updated document instance.

        Raises:
            OptimisticLockError: If the document has been modified since
                it was last read.

        Example:
            >>> product = await Product.get(product_id)
            >>> await product.update_with_version(price=29.99, title="New Title")
        """
        from shared.exceptions import OptimisticLockError

        current_version = self.version
        self.version = current_version + 1
        self.updated_at = datetime.now(UTC)

        for field_name, value in fields.items():
            setattr(self, field_name, value)

        # Use find_one + replace with version check
        result = await self.__class__.find_one(
            self.__class__.id == self.id,
            self.__class__.version == current_version,  # type: ignore[attr-defined]
        )

        if result is None:
            raise OptimisticLockError(
                detail={
                    "resource": self.__class__.__name__,
                    "id": str(self.id),
                    "expected_version": current_version,
                },
            )

        await self.save()
        return self

    @classmethod
    async def find_active(
        cls: Type[T],
        *args: Any,
        **kwargs: Any,
    ) -> list[T]:
        """Find all active (non-deleted) documents matching the criteria.

        Automatically adds is_deleted=False filter to exclude
        soft-deleted documents.

        Args:
            *args: Beanie query expressions.
            **kwargs: Additional find parameters.

        Returns:
            List of matching active documents.

        Example:
            >>> active_users = await User.find_active(User.roles == "admin")
        """
        return await cls.find(
            *args,
            cls.is_deleted == False,  # noqa: E712
            **kwargs,
        ).to_list()

    @classmethod
    async def get_active(cls: Type[T], document_id: Any) -> T | None:
        """Get a single active (non-deleted) document by ID.

        Args:
            document_id: The document's ObjectId or string ID.

        Returns:
            The document if found and active, None otherwise.

        Example:
            >>> user = await User.get_active("507f1f77bcf86cd799439011")
        """
        doc = await cls.get(document_id)
        if doc and not doc.is_deleted:
            return doc
        return None


# ── Index Helpers ────────────────────────────────────────────────────────────


async def ensure_indexes(document_models: list[Type[Document]]) -> None:
    """Create MongoDB indexes for all registered document models.

    This is called after Beanie initialization to ensure all indexes
    defined in document Settings are created.

    Args:
        document_models: List of Beanie Document classes with index definitions.
    """
    for model in document_models:
        try:
            collection = model.get_motor_collection()
            if hasattr(model, "Settings") and hasattr(model.Settings, "indexes"):
                for index in model.Settings.indexes:
                    await collection.create_index(
                        index.document.get("key", []),  # type: ignore[union-attr]
                        **{k: v for k, v in index.document.items() if k != "key"},  # type: ignore[union-attr]
                    )
            logger.info(
                "indexes_ensured",
                collection=model.__name__,
            )
        except Exception as e:
            logger.error(
                "index_creation_failed",
                collection=model.__name__,
                error=str(e),
            )
