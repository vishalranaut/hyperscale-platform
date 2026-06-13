"""HyperScale Platform — Product Service Pydantic Schemas.

Request and response schemas for the Product Service REST API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProductStatusEnum(str, Enum):
    """Product status for API schemas."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


# ── Request Schemas ──────────────────────────────────────────────────────────


class CreateProductRequest(BaseModel):
    """Request to create a new product.

    Attributes:
        sku: Unique SKU identifier.
        title: Product title (3-200 chars).
        description: Product description.
        price: Price in cents.
        compare_price: Compare-at price in cents.
        currency: ISO 4217 currency code.
        images: List of image URLs.
        category_id: Category reference.
        brand: Brand name.
        attributes: Product attributes.
        tags: Search tags.
        status: Initial product status.
        inventory: Initial inventory settings.
    """

    sku: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=3, max_length=200)
    description: str = ""
    price: int = Field(..., ge=0)
    compare_price: int = Field(default=0, ge=0)
    currency: str = "USD"
    images: list[str] = Field(default_factory=list)
    category_id: str | None = None
    brand: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    status: ProductStatusEnum = ProductStatusEnum.DRAFT
    inventory: InventoryInput | None = None


class InventoryInput(BaseModel):
    """Inventory settings for product creation/update."""

    stock_quantity: int = Field(default=0, ge=0)
    threshold: int = Field(default=10, ge=0)
    warehouse_id: str = "default"
    track_inventory: bool = True


class UpdateProductRequest(BaseModel):
    """Partial update request for a product.

    All fields are optional — only provided fields are updated.
    """

    title: str | None = None
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    compare_price: int | None = Field(default=None, ge=0)
    images: list[str] | None = None
    category_id: str | None = None
    brand: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    status: ProductStatusEnum | None = None


class UpdateInventoryRequest(BaseModel):
    """Request to update inventory levels.

    Attributes:
        delta: Change in stock (positive = add, negative = remove).
        reason: Reason for the change (e.g., 'restock', 'sale', 'damage').
    """

    delta: int
    reason: str = ""


class ProductSearchParams(BaseModel):
    """Search and filter parameters for product listing.

    Attributes:
        query: Free-text search query.
        category_id: Filter by category.
        brand: Filter by brand.
        min_price: Minimum price in cents.
        max_price: Maximum price in cents.
        status: Filter by status.
        tags: Filter by tags (any match).
        in_stock: Filter to only in-stock products.
        sort_by: Sort field.
        sort_order: Sort direction.
        page: Page number.
        page_size: Items per page.
    """

    query: str | None = None
    category_id: str | None = None
    brand: str | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    status: ProductStatusEnum | None = None
    tags: list[str] | None = None
    in_stock: bool | None = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CreateCategoryRequest(BaseModel):
    """Request to create a product category."""

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    parent_id: str | None = None
    description: str = ""
    image_url: str = ""
    sort_order: int = 0


class VariantInput(BaseModel):
    """Variant data for product creation."""

    sku: str = Field(..., min_length=1, max_length=50)
    attributes: dict[str, str] = Field(default_factory=dict)
    price: int = Field(default=0, ge=0)
    stock: int = Field(default=0, ge=0)
    images: list[str] = Field(default_factory=list)


# ── Response Schemas ─────────────────────────────────────────────────────────


class VariantResponse(BaseModel):
    """Variant response data."""

    id: str
    sku: str
    attributes: dict[str, str] = Field(default_factory=dict)
    price: int = 0
    compare_price: int = 0
    stock: int = 0
    images: list[str] = Field(default_factory=list)
    is_available: bool = True


class InventoryResponse(BaseModel):
    """Inventory status response."""

    stock_quantity: int = 0
    reserved: int = 0
    available: int = 0
    threshold: int = 10
    warehouse_id: str = "default"
    track_inventory: bool = True
    is_low_stock: bool = False
    is_out_of_stock: bool = False


class ProductResponse(BaseModel):
    """Full product response."""

    id: str
    sku: str
    title: str
    description: str = ""
    price: int = 0
    compare_price: int = 0
    currency: str = "USD"
    images: list[str] = Field(default_factory=list)
    category_id: str | None = None
    brand: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    variants: list[VariantResponse] = Field(default_factory=list)
    inventory: InventoryResponse | None = None
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)
    rating: float = 0.0
    review_count: int = 0
    seller_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductSummary(BaseModel):
    """Compact product representation for listings."""

    id: str
    sku: str
    title: str
    price: int
    compare_price: int = 0
    currency: str = "USD"
    image: str = ""
    brand: str = ""
    status: str = "draft"
    rating: float = 0.0
    in_stock: bool = True


class CategoryResponse(BaseModel):
    """Category response with children."""

    id: str
    name: str
    slug: str
    parent_id: str | None = None
    description: str = ""
    image_url: str = ""
    sort_order: int = 0
    product_count: int = 0
    children: list["CategoryResponse"] = Field(default_factory=list)


class CategoryTreeResponse(BaseModel):
    """Full category tree."""

    categories: list[CategoryResponse] = Field(default_factory=list)


class PaginatedProductResponse(BaseModel):
    """Paginated product listing response."""

    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
