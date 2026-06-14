"""HyperScale Platform — Analytics Service Domain Models.

Models for tracking events and storing aggregated metrics.

Architectural Note (Senior Dev):
    In a high-throughput system, writing raw events directly to a document database
    can cause massive write amplification and index bloat. The models here represent
    raw events (which should ideally be TTL'd or tiered to cold storage) and 
    aggregated daily rollups (which power the dashboards efficiently).
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from beanie import Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING

from shared.db.mongodb import BaseDocument


class EventType(str, Enum):
    PAGE_VIEW = "page_view"
    PRODUCT_VIEW = "product_view"
    ADD_TO_CART = "add_to_cart"
    ORDER_PLACED = "order_placed"


class AnalyticsEvent(BaseDocument):
    """Raw analytics event.
    
    In a production system, these might only live in Kafka or a Data Warehouse (like ClickHouse).
    We store a rolling window of them here for near-real-time dashboarding.
    """
    event_type: EventType
    user_id: str | None = None
    session_id: str = ""
    resource_id: str = ""  # e.g., product_id or order_id
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Settings:
        name = "analytics_events"
        indexes = [
            IndexModel([("event_type", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("resource_id", ASCENDING)]),
            # TTL index to automatically delete raw events older than 30 days
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=30 * 24 * 3600),
        ]


class DailyMetric(BaseDocument):
    """Aggregated daily metrics to power dashboards quickly without scanning raw events.
    
    This uses the Document Versioning Pattern for optimistic concurrency, though
    increment operations in MongoDB ($inc) are atomic and preferred.
    """
    date_str: Indexed(str, unique=True)  # type: ignore[valid-type]  # Format: YYYY-MM-DD
    total_users: int = 0
    active_orders: int = 0
    revenue_cents: int = 0
    
    class Settings:
        name = "daily_metrics"
        indexes = [
            IndexModel([("date_str", DESCENDING)], unique=True),
        ]
