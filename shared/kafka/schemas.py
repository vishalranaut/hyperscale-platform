"""HyperScale Platform — Kafka Message Schemas.

Pydantic v2 models for Kafka message serialization/deserialization.
All inter-service messages follow a standardized envelope format
with event metadata for tracing and idempotency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventMetadata(BaseModel):
    """Metadata attached to every Kafka event for tracing and deduplication.

    Attributes:
        timestamp: ISO 8601 timestamp when the event was produced.
        source_service: Name of the microservice that produced the event.
        correlation_id: Distributed tracing correlation ID.
        idempotency_key: Unique key for consumer-side deduplication.
        version: Schema version for backwards compatibility.
        trace_id: Optional OpenTelemetry trace ID.
    """

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_service: str = "unknown"
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "1.0"
    trace_id: str | None = None


class KafkaMessage(BaseModel):
    """Standardized Kafka message envelope.

    All inter-service events are wrapped in this envelope to ensure
    consistent serialization, tracing, and schema evolution.

    Attributes:
        event_type: Dot-separated event identifier (e.g., 'user.registered').
        payload: The event-specific data as a dictionary.
        metadata: Event metadata for tracing and deduplication.

    Example:
        >>> msg = KafkaMessage(
        ...     event_type="user.registered",
        ...     payload={"user_id": "abc123", "email": "user@example.com"},
        ...     metadata=EventMetadata(source_service="user-service"),
        ... )
        >>> serialized = msg.serialize()
    """

    event_type: str
    payload: dict[str, Any]
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    def serialize(self) -> bytes:
        """Serialize the message to JSON bytes for Kafka.

        Returns:
            UTF-8 encoded JSON bytes.
        """
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "KafkaMessage":
        """Deserialize JSON bytes from Kafka into a KafkaMessage.

        Args:
            data: Raw bytes from a Kafka consumer record.

        Returns:
            Deserialized KafkaMessage instance.

        Raises:
            ValueError: If the data cannot be parsed.
        """
        return cls.model_validate_json(data)


# ── Common Event Types ───────────────────────────────────────────────────────


class UserEvents(str, Enum):
    """User service event type constants."""

    REGISTERED = "user.registered"
    VERIFIED = "user.verified"
    LOGIN = "user.login"
    LOGOUT = "user.logout"
    ROLE_CHANGED = "user.role_changed"
    PROFILE_UPDATED = "user.profile_updated"
    DELETED = "user.deleted"


class ProductEvents(str, Enum):
    """Product service event type constants."""

    CREATED = "product.created"
    UPDATED = "product.updated"
    DELETED = "product.deleted"
    INVENTORY_UPDATED = "inventory.updated"
    INVENTORY_LOW_STOCK = "inventory.low_stock"
    INVENTORY_OUT_OF_STOCK = "inventory.out_of_stock"


class OrderEvents(str, Enum):
    """Order service event type constants."""

    CREATED = "order.created"
    CONFIRMED = "order.confirmed"
    CANCELLED = "order.cancelled"
    REFUNDED = "order.refunded"
    STATUS_CHANGED = "order.status_changed"
    FULFILLMENT_STARTED = "order.fulfillment_started"


class ChatEvents(str, Enum):
    """Chat service event type constants."""

    MESSAGE_SENT = "chat.message_sent"
    ROOM_CREATED = "chat.room_created"


class NotificationEvents(str, Enum):
    """Notification service event type constants."""

    SENT = "notification.sent"
    FAILED = "notification.failed"
    DELIVERED = "notification.delivered"


# ── Kafka Topics ─────────────────────────────────────────────────────────────


class KafkaTopics:
    """Centralized Kafka topic name constants.

    Prevents typos and makes topic management easier across services.
    """

    USER_EVENTS = "hyperscale.user.events"
    PRODUCT_EVENTS = "hyperscale.product.events"
    ORDER_EVENTS = "hyperscale.order.events"
    CHAT_EVENTS = "hyperscale.chat.events"
    NOTIFICATION_EVENTS = "hyperscale.notification.events"
    ANALYTICS_EVENTS = "hyperscale.analytics.events"
    DEAD_LETTER = "hyperscale.dead-letter"

    @classmethod
    def all_topics(cls) -> list[str]:
        """Return a list of all defined topic names.

        Returns:
            List of all Kafka topic name strings.
        """
        return [
            cls.USER_EVENTS,
            cls.PRODUCT_EVENTS,
            cls.ORDER_EVENTS,
            cls.CHAT_EVENTS,
            cls.NOTIFICATION_EVENTS,
            cls.ANALYTICS_EVENTS,
            cls.DEAD_LETTER,
        ]
