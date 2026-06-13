"""HyperScale Platform — Product Repository.

Async MongoDB repository for Product, Category, and Variant documents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import In, Set

from services.product_service.domain.models import Category, Product, ProductStatus, Variant
from shared.logging import get_logger

logger = get_logger(__name__)


class ProductRepository:
    """Async repository for Product document operations.

    Example:
        >>> repo = ProductRepository()
        >>> product = await repo.create(sku="SKU001", title="Widget", price=2999)
    """

    async def create(self, **fields: Any) -> Product:
        """Create a new product document.

        Args:
            **fields: Product field values.

        Returns:
            The created Product document.
        """
        product = Product(**fields)
        await product.insert()
        logger.info("product_created", product_id=str(product.id), sku=product.sku)
        return product

    async def get_by_id(self, product_id: str) -> Product | None:
        """Get a product by ID."""
        try:
            product = await Product.get(PydanticObjectId(product_id))
            if product and not product.is_deleted:
                return product
            return None
        except Exception:
            return None

    async def get_by_sku(self, sku: str) -> Product | None:
        """Get a product by SKU."""
        return await Product.find_one(
            Product.sku == sku,
            Product.is_deleted == False,  # noqa: E712
        )

    async def update(self, product_id: str, **fields: Any) -> Product | None:
        """Update specific fields on a product."""
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        fields["updated_at"] = datetime.now(UTC)
        await product.update(Set(fields))
        await product.sync()
        logger.info("product_updated", product_id=product_id)
        return product

    async def soft_delete(self, product_id: str) -> bool:
        """Soft-delete a product."""
        product = await self.get_by_id(product_id)
        if product is None:
            return False
        await product.soft_delete()
        return True

    async def search(
        self,
        query: str | None = None,
        category_id: str | None = None,
        brand: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        in_stock: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Product], int]:
        """Search products with filters and pagination.

        Args:
            query: Free-text search on title, description, brand, tags.
            category_id: Filter by category.
            brand: Filter by brand name.
            min_price: Minimum price filter (cents).
            max_price: Maximum price filter (cents).
            status: Filter by product status.
            tags: Filter by tags (any match).
            in_stock: Filter to in-stock products only.
            page: Page number (1-based).
            page_size: Items per page.
            sort_by: Sort field.
            sort_order: 'asc' or 'desc'.

        Returns:
            Tuple of (products list, total count).
        """
        filters: list[Any] = [Product.is_deleted == False]  # noqa: E712

        if query:
            filters.append({"$text": {"$search": query}})

        if category_id:
            filters.append(Product.category_id == category_id)

        if brand:
            filters.append(Product.brand == brand)

        if min_price is not None:
            filters.append(Product.price >= min_price)

        if max_price is not None:
            filters.append(Product.price <= max_price)

        if status:
            filters.append(Product.status == status)

        if tags:
            filters.append({"tags": {"$in": tags}})

        if in_stock is True:
            filters.append({"inventory.stock_quantity": {"$gt": 0}})

        sort_prefix = "-" if sort_order == "desc" else "+"
        sort_spec = f"{sort_prefix}{sort_by}"

        total = await Product.find(*filters).count()
        skip = (page - 1) * page_size
        products = await Product.find(*filters).sort(sort_spec).skip(skip).limit(page_size).to_list()

        return products, total

    async def bulk_get(self, product_ids: list[str]) -> list[Product]:
        """Get multiple products by IDs."""
        object_ids = [PydanticObjectId(pid) for pid in product_ids]
        return await Product.find(
            In(Product.id, object_ids),
            Product.is_deleted == False,  # noqa: E712
        ).to_list()

    async def update_inventory_atomic(
        self,
        product_id: str,
        delta: int,
        field: str = "inventory.stock_quantity",
    ) -> Product | None:
        """Atomically update inventory using MongoDB $inc.

        Args:
            product_id: The product ID.
            delta: The change amount (positive or negative).
            field: The inventory field to update.

        Returns:
            The updated product, or None if not found.
        """
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        collection = Product.get_motor_collection()
        result = await collection.find_one_and_update(
            {"_id": PydanticObjectId(product_id)},
            {
                "$inc": {field: delta},
                "$set": {"updated_at": datetime.now(UTC)},
            },
            return_document=True,
        )

        if result:
            await product.sync()
            return product
        return None

    async def reserve_inventory(self, product_id: str, quantity: int) -> bool:
        """Reserve inventory for an order.

        Atomically increments reserved count and checks availability.

        Args:
            product_id: The product ID.
            quantity: Number of units to reserve.

        Returns:
            True if reservation succeeded.
        """
        collection = Product.get_motor_collection()
        result = await collection.update_one(
            {
                "_id": PydanticObjectId(product_id),
                "$expr": {
                    "$gte": [
                        {"$subtract": ["$inventory.stock_quantity", "$inventory.reserved"]},
                        quantity,
                    ]
                },
            },
            {
                "$inc": {"inventory.reserved": quantity},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        success = result.modified_count > 0
        if success:
            logger.info("inventory_reserved", product_id=product_id, quantity=quantity)
        return success

    async def release_inventory(self, product_id: str, quantity: int) -> bool:
        """Release previously reserved inventory.

        Args:
            product_id: The product ID.
            quantity: Number of units to release.

        Returns:
            True if release succeeded.
        """
        collection = Product.get_motor_collection()
        result = await collection.update_one(
            {
                "_id": PydanticObjectId(product_id),
                "inventory.reserved": {"$gte": quantity},
            },
            {
                "$inc": {"inventory.reserved": -quantity},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        return result.modified_count > 0


class CategoryRepository:
    """Async repository for Category operations."""

    async def create(self, **fields: Any) -> Category:
        """Create a new category."""
        category = Category(**fields)
        await category.insert()
        logger.info("category_created", name=category.name)
        return category

    async def get_by_id(self, category_id: str) -> Category | None:
        """Get a category by ID."""
        try:
            cat = await Category.get(PydanticObjectId(category_id))
            if cat and not cat.is_deleted:
                return cat
            return None
        except Exception:
            return None

    async def get_by_slug(self, slug: str) -> Category | None:
        """Get a category by slug."""
        return await Category.find_one(
            Category.slug == slug,
            Category.is_deleted == False,  # noqa: E712
        )

    async def get_tree(self) -> list[Category]:
        """Get all categories for building a tree."""
        return await Category.find(
            Category.is_deleted == False,  # noqa: E712
            Category.is_visible == True,  # noqa: E712
        ).sort("+sort_order").to_list()

    async def get_children(self, parent_id: str | None) -> list[Category]:
        """Get direct children of a category."""
        return await Category.find(
            Category.parent_id == parent_id,
            Category.is_deleted == False,  # noqa: E712
        ).sort("+sort_order").to_list()


class VariantRepository:
    """Async repository for Variant operations."""

    async def create(self, **fields: Any) -> Variant:
        """Create a new variant."""
        variant = Variant(**fields)
        await variant.insert()
        return variant

    async def get_by_product(self, product_id: str) -> list[Variant]:
        """Get all variants for a product."""
        return await Variant.find(
            Variant.product_id == product_id,
            Variant.is_deleted == False,  # noqa: E712
        ).to_list()

    async def get_by_sku(self, sku: str) -> Variant | None:
        """Get a variant by SKU."""
        return await Variant.find_one(
            Variant.sku == sku,
            Variant.is_deleted == False,  # noqa: E712
        )

    async def update_stock(self, variant_id: str, delta: int) -> bool:
        """Atomically update variant stock."""
        collection = Variant.get_motor_collection()
        result = await collection.update_one(
            {"_id": PydanticObjectId(variant_id)},
            {
                "$inc": {"stock": delta},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        return result.modified_count > 0
