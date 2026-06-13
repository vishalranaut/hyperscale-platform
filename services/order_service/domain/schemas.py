"""HyperScale Platform — Order Service Domain Schemas.

Pydantic v2 request/response schemas for the Order Service REST API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────────────


class AddCartItemRequest(BaseModel):
    """Request to add an item to the cart."""

    product_id: str
    variant_id: str = ""
    quantity: int = Field(default=1, ge=1)


class UpdateCartItemRequest(BaseModel):
    """Request to update a cart item quantity."""

    quantity: int = Field(ge=0)  # 0 removes the item


class AddressInput(BaseModel):
    """Address input for order placement."""

    line1: str
    line2: str = ""
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: str = ""
    recipient_name: str = ""


class PlaceOrderRequest(BaseModel):
    """Request to place an order from the current cart.

    Attributes:
        shipping_address: Delivery address.
        billing_address: Billing address (defaults to shipping if not provided).
        payment_method_id: Payment method/token from the payment provider.
        notes: Optional order notes.
    """

    shipping_address: AddressInput
    billing_address: AddressInput | None = None
    payment_method_id: str = ""
    notes: str = ""


class CancelOrderRequest(BaseModel):
    """Request to cancel an order."""

    reason: str = ""


class RefundOrderRequest(BaseModel):
    """Request to refund an order (admin)."""

    amount: int | None = Field(default=None, ge=0)  # None = full refund
    reason: str = ""


# ── Response Schemas ─────────────────────────────────────────────────────────


class CartItemResponse(BaseModel):
    """Cart item response."""

    product_id: str
    variant_id: str = ""
    quantity: int
    unit_price: int
    total_price: int = 0
    product_title: str = ""
    product_image: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)


class CartResponse(BaseModel):
    """Full cart response."""

    user_id: str
    items: list[CartItemResponse] = Field(default_factory=list)
    subtotal: int = 0
    item_count: int = 0


class OrderItemResponse(BaseModel):
    """Order item in an order response."""

    product_id: str
    variant_id: str = ""
    product_title: str = ""
    product_image: str = ""
    sku: str = ""
    quantity: int
    unit_price: int
    total_price: int


class PaymentInfoResponse(BaseModel):
    """Payment information in an order response."""

    provider: str = ""
    transaction_id: str = ""
    status: str = "pending"
    amount: int = 0
    currency: str = "USD"
    captured_at: datetime | None = None


class TrackingInfoResponse(BaseModel):
    """Tracking information in an order response."""

    carrier: str = ""
    tracking_number: str = ""
    tracking_url: str = ""
    estimated_delivery: datetime | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class OrderResponse(BaseModel):
    """Full order response."""

    id: str
    order_number: str
    user_id: str
    items: list[OrderItemResponse] = Field(default_factory=list)
    subtotal: int = 0
    tax: int = 0
    shipping_cost: int = 0
    discount: int = 0
    total: int = 0
    currency: str = "USD"
    status: str = "pending"
    payment: PaymentInfoResponse | None = None
    shipping_address: dict[str, Any] = Field(default_factory=dict)
    billing_address: dict[str, Any] = Field(default_factory=dict)
    tracking: TrackingInfoResponse | None = None
    notes: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedOrderResponse(BaseModel):
    """Paginated order listing."""

    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
