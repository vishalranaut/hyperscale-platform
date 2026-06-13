"""HyperScale Platform — Order Service Domain Models.

Beanie ODM models for orders, carts, order items, payment info,
and tracking information.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from beanie import Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING

from shared.db.mongodb import BaseDocument


class OrderStatus(str, Enum):
    """Order lifecycle status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentStatus(str, Enum):
    """Payment processing status."""

    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class Address(BaseDocument):
    """Shipping or billing address.

    Attributes:
        line1: Street address line 1.
        line2: Street address line 2 (apt, suite, etc.).
        city: City name.
        state: State/province/region.
        postal_code: ZIP/postal code.
        country: ISO 3166-1 alpha-2 country code.
        phone: Contact phone number.
        recipient_name: Name of the recipient.
    """

    line1: str
    line2: str = ""
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: str = ""
    recipient_name: str = ""

    class Settings:
        """Beanie collection settings."""
        name = "addresses"


class OrderItem(BaseDocument):
    """Individual item within an order.

    Attributes:
        product_id: Reference to the product.
        variant_id: Optional variant reference.
        product_title: Snapshot of product title at order time.
        product_image: Snapshot of product image.
        sku: Product/variant SKU.
        quantity: Number of units ordered.
        unit_price: Price per unit in cents.
        total_price: quantity × unit_price in cents.
        attributes: Variant attributes at order time.
    """

    product_id: str
    variant_id: str = ""
    product_title: str = ""
    product_image: str = ""
    sku: str = ""
    quantity: int = Field(default=1, ge=1)
    unit_price: int = Field(default=0, ge=0)  # cents
    total_price: int = Field(default=0, ge=0)  # cents
    attributes: dict[str, str] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""
        name = "order_items"


class PaymentInfo(BaseDocument):
    """Payment details for an order.

    Attributes:
        provider: Payment provider name (e.g., 'stripe').
        transaction_id: Provider's transaction ID.
        payment_intent_id: Payment intent/session ID.
        status: Payment status.
        amount: Total payment amount in cents.
        currency: Payment currency code.
        captured_at: When payment was captured.
        refunds: List of refund records.
        metadata: Provider-specific metadata.
    """

    provider: str = "stripe"
    transaction_id: str = ""
    payment_intent_id: str = ""
    status: PaymentStatus = PaymentStatus.PENDING
    amount: int = Field(default=0, ge=0)
    currency: str = "USD"
    captured_at: datetime | None = None
    refunds: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""
        name = "payment_info"


class TrackingEvent(BaseDocument):
    """A single tracking event in the fulfillment timeline."""

    status: str
    description: str
    location: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        """Beanie collection settings."""
        name = "tracking_events"


class TrackingInfo(BaseDocument):
    """Shipment tracking information.

    Attributes:
        carrier: Shipping carrier name.
        tracking_number: Carrier tracking number.
        tracking_url: URL to track the shipment.
        estimated_delivery: Estimated delivery date.
        events: List of tracking events.
    """

    carrier: str = ""
    tracking_number: str = ""
    tracking_url: str = ""
    estimated_delivery: datetime | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)

    class Settings:
        """Beanie collection settings."""
        name = "tracking_info"


class Order(BaseDocument):
    """Core order document.

    Represents a customer order with items, pricing, payment,
    shipping, and tracking information.

    Attributes:
        order_number: Human-readable order number.
        user_id: Reference to the ordering user.
        items: List of order items (embedded).
        subtotal: Pre-tax total in cents.
        tax: Tax amount in cents.
        shipping_cost: Shipping cost in cents.
        discount: Discount amount in cents.
        total: Final total in cents.
        currency: Order currency code.
        status: Current order status.
        payment: Payment details (embedded).
        shipping_address: Delivery address (embedded).
        billing_address: Billing address (embedded).
        tracking: Shipment tracking info (embedded).
        notes: Customer notes.
        cancel_reason: Reason for cancellation (if cancelled).
        metadata: Flexible metadata store.
        reservation_id: Inventory reservation reference.
        saga_state: Current state of the order placement saga.
    """

    order_number: Indexed(str, unique=True)  # type: ignore[valid-type]
    user_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    subtotal: int = Field(default=0, ge=0)
    tax: int = Field(default=0, ge=0)
    shipping_cost: int = Field(default=0, ge=0)
    discount: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    currency: str = "USD"
    status: OrderStatus = OrderStatus.PENDING
    payment: dict[str, Any] = Field(default_factory=dict)
    shipping_address: dict[str, Any] = Field(default_factory=dict)
    billing_address: dict[str, Any] = Field(default_factory=dict)
    tracking: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    cancel_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    reservation_id: str = ""
    saga_state: str = ""

    class Settings:
        """Beanie collection settings."""
        name = "orders"
        indexes = [
            IndexModel([("order_number", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
        ]


class CartItem(BaseDocument):
    """Item in a shopping cart.

    Attributes:
        product_id: Product reference.
        variant_id: Optional variant reference.
        quantity: Number of units.
        unit_price: Price per unit in cents.
        product_title: Product display title.
        product_image: Product thumbnail URL.
        attributes: Product/variant attributes.
    """

    product_id: str
    variant_id: str = ""
    quantity: int = Field(default=1, ge=1)
    unit_price: int = Field(default=0, ge=0)
    product_title: str = ""
    product_image: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""
        name = "cart_items"
