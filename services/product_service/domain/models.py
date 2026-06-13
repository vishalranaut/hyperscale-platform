"""HyperScale Platform — Product Service Domain Models.

Beanie ODM document models for product catalog, categories,
variants, and inventory tracking.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from beanie import Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT

from shared.db.mongodb import BaseDocument


class ProductStatus(str, Enum):
    """Product lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class SEOData(BaseDocument):
    """SEO metadata for a product.

    Attributes:
        meta_title: SEO title tag.
        meta_description: SEO meta description.
        slug: URL-friendly product identifier.
        canonical_url: Canonical URL for the product.
        keywords: SEO keywords.
    """

    meta_title: str = ""
    meta_description: str = ""
    slug: str = ""
    canonical_url: str = ""
    keywords: list[str] = Field(default_factory=list)

    class Settings:
        """Beanie collection settings."""
        name = "seo_data"


class InventoryInfo(BaseDocument):
    """Inventory tracking information.

    Attributes:
        stock_quantity: Total physical stock count.
        reserved: Quantity reserved by pending orders.
        threshold: Low-stock alert threshold.
        warehouse_id: Identifier of the storage warehouse.
        track_inventory: Whether inventory tracking is enabled.
    """

    stock_quantity: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    threshold: int = Field(default=10, ge=0)
    warehouse_id: str = "default"
    track_inventory: bool = True

    class Settings:
        """Beanie collection settings."""
        name = "inventory"

    @property
    def available(self) -> int:
        """Calculate available stock (total minus reserved)."""
        return max(self.stock_quantity - self.reserved, 0)

    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below the alert threshold."""
        return self.available <= self.threshold

    @property
    def is_out_of_stock(self) -> bool:
        """Check if no stock is available."""
        return self.available == 0


class Variant(BaseDocument):
    """Product variant (e.g., size, color combination).

    Attributes:
        sku: Unique variant SKU.
        product_id: Parent product reference.
        attributes: Variant-specific attributes (e.g., {"size": "L", "color": "Blue"}).
        price: Variant-specific price in cents.
        compare_price: Original/compare-at price in cents.
        stock: Variant stock count.
        images: Variant-specific image URLs.
        is_available: Whether this variant is currently for sale.
        weight: Product weight in grams.
        barcode: UPC/EAN barcode.
    """

    sku: Indexed(str, unique=True)  # type: ignore[valid-type]
    product_id: str
    attributes: dict[str, str] = Field(default_factory=dict)
    price: int = Field(default=0, ge=0)  # cents
    compare_price: int = Field(default=0, ge=0)
    stock: int = Field(default=0, ge=0)
    images: list[str] = Field(default_factory=list)
    is_available: bool = True
    weight: int = 0  # grams
    barcode: str = ""

    class Settings:
        """Beanie collection settings."""
        name = "variants"
        indexes = [
            IndexModel([("sku", ASCENDING)], unique=True),
            IndexModel([("product_id", ASCENDING)]),
        ]


class Category(BaseDocument):
    """Product category with hierarchical tree support.

    Attributes:
        name: Category display name.
        slug: URL-friendly identifier.
        parent_id: Parent category ID (null for root).
        description: Category description.
        image_url: Category image.
        sort_order: Display sort order within parent.
        is_visible: Whether the category is shown to customers.
        product_count: Cached count of products in this category.
        path: Materialized path for tree queries (e.g., "electronics/phones").
    """

    name: str
    slug: Indexed(str, unique=True)  # type: ignore[valid-type]
    parent_id: str | None = None
    description: str = ""
    image_url: str = ""
    sort_order: int = Field(default=0, ge=0)
    is_visible: bool = True
    product_count: int = Field(default=0, ge=0)
    path: str = ""

    class Settings:
        """Beanie collection settings."""
        name = "categories"
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=True),
            IndexModel([("parent_id", ASCENDING)]),
            IndexModel([("sort_order", ASCENDING)]),
            IndexModel([("path", ASCENDING)]),
        ]


class Product(BaseDocument):
    """Core product document.

    Represents a product listing with pricing, inventory, categorization,
    and search-optimized fields.

    Attributes:
        sku: Unique stock-keeping unit identifier.
        title: Product display title.
        description: Full product description (may contain HTML).
        price: Price in smallest currency unit (cents).
        compare_price: Original/compare-at price in cents.
        currency: ISO 4217 currency code.
        images: List of product image URLs.
        category_id: Reference to the product's category.
        brand: Product brand name.
        attributes: Product-specific attributes (e.g., {"material": "cotton"}).
        variant_ids: List of variant document IDs.
        inventory: Embedded inventory information.
        seo: Embedded SEO metadata.
        status: Product lifecycle status.
        tags: Search/filter tags.
        rating: Average customer rating (0-5).
        review_count: Number of customer reviews.
        seller_id: ID of the seller/merchant.
        weight: Product weight in grams.
        dimensions: Product dimensions.
    """

    sku: Indexed(str, unique=True)  # type: ignore[valid-type]
    title: str
    description: str = ""
    price: int = Field(default=0, ge=0)  # cents
    compare_price: int = Field(default=0, ge=0)
    currency: str = "USD"
    images: list[str] = Field(default_factory=list)
    category_id: str | None = None
    brand: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    variant_ids: list[str] = Field(default_factory=list)
    inventory: dict[str, Any] = Field(default_factory=lambda: {
        "stock_quantity": 0,
        "reserved": 0,
        "threshold": 10,
        "warehouse_id": "default",
        "track_inventory": True,
    })
    seo: dict[str, Any] = Field(default_factory=dict)
    status: ProductStatus = ProductStatus.DRAFT
    tags: list[str] = Field(default_factory=list)
    rating: float = Field(default=0.0, ge=0.0, le=5.0)
    review_count: int = Field(default=0, ge=0)
    seller_id: str | None = None
    weight: int = 0
    dimensions: dict[str, float] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""
        name = "products"
        indexes = [
            IndexModel([("sku", ASCENDING)], unique=True),
            IndexModel([("category_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("brand", ASCENDING)]),
            IndexModel([("price", ASCENDING)]),
            IndexModel([("rating", DESCENDING)]),
            IndexModel([("tags", ASCENDING)]),
            IndexModel([("seller_id", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel(
                [("title", TEXT), ("description", TEXT), ("brand", TEXT), ("tags", TEXT)],
                name="product_text_search",
                weights={"title": 10, "brand": 5, "tags": 3, "description": 1},
            ),
        ]

    @property
    def available_stock(self) -> int:
        """Calculate available stock from inventory."""
        qty = self.inventory.get("stock_quantity", 0)
        reserved = self.inventory.get("reserved", 0)
        return max(qty - reserved, 0)

    @property
    def is_in_stock(self) -> bool:
        """Check if the product is in stock."""
        return self.available_stock > 0

    @property
    def display_price(self) -> str:
        """Format price for display (e.g., '$29.99')."""
        if self.currency == "USD":
            return f"${self.price / 100:.2f}"
        return f"{self.price / 100:.2f} {self.currency}"
