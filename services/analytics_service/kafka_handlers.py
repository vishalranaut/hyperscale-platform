"""HyperScale Platform — Analytics Service Kafka Handlers.

Consumes events from across the platform to generate business metrics.

Architectural Note (Senior Dev):
    We use atomic `$inc` updates for `DailyMetric` to avoid race conditions when
    multiple consumer instances process events simultaneously.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from shared.kafka.consumer import KafkaEventConsumer
from shared.kafka.schemas import KafkaTopics, OrderEvents
from shared.logging import get_logger

logger = get_logger(__name__)


async def handle_order_metrics(event_type: str, payload: dict[str, Any], key: str | None = None) -> None:
    """Update daily metrics based on order events."""
    from services.analytics_service.domain.models import DailyMetric
    
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    
    try:
        # Find or create today's metric document
        metric = await DailyMetric.find_one(DailyMetric.date_str == today_str)
        if not metric:
            metric = DailyMetric(date_str=today_str)
            await metric.insert()
            
        if event_type == OrderEvents.CONFIRMED:
            # Atomic increment
            await metric.inc({
                DailyMetric.active_orders: 1,
                DailyMetric.revenue_cents: payload.get("total", 0),
            })
            logger.info("metrics_updated_order_confirmed", date=today_str)
            
    except Exception as e:
        logger.error("failed_to_update_order_metrics", error=str(e), payload=payload)


async def start_consumers() -> None:
    """Initialize and start all Kafka consumers for analytics."""
    try:
        consumer = await KafkaEventConsumer.get_instance(group_id="analytics-service-group")
        
        consumer.register_handler(KafkaTopics.ORDER_EVENTS, handle_order_metrics)
        
        asyncio.create_task(consumer.start_consuming())
        logger.info("analytics_consumers_started")
    except Exception as e:
        logger.error("failed_to_start_analytics_consumers", error=str(e))
