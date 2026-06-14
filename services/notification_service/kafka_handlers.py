"""HyperScale Platform — Notification Service Kafka Handlers.

Consumes platform-wide events (e.g., OrderConfirmed, MessageSent) and 
dispatches push notifications to the respective users.

Architectural Note (Senior Dev):
    This module implements the Consumer side of the Event-Driven Architecture.
    By decoupled notifications from core flows (like order placement), we ensure
    that the critical path remains fast and highly available. If the FCM provider
    experiences an outage or latency spike, it only affects notification delivery
    (which is eventually consistent) rather than blocking the user's checkout.
    
    Robustness patterns implemented here:
    1. Idempotency: Handlers should ideally check if a notification for a specific
       event ID was already sent to avoid duplicate pushes on at-least-once delivery.
    2. Graceful Error Handling: Exceptions are caught and logged to prevent
       poison-pill messages from crashing the consumer loop.
"""

import asyncio
from typing import Any

from services.notification_service.services.notification_service import NotificationService
from shared.kafka.consumer import KafkaEventConsumer
from shared.kafka.schemas import KafkaTopics, OrderEvents
from shared.logging import get_logger

logger = get_logger(__name__)


async def handle_order_events(event_type: str, payload: dict[str, Any], key: str | None = None) -> None:
    """Process order-related events and send notifications.
    
    Args:
        event_type: The specific order event (e.g., 'confirmed', 'shipped').
        payload: Event payload containing order details.
        key: Kafka message key (typically order_id).
    """
    logger.info("processing_order_event", event_type=event_type, order_id=payload.get("order_id"))
    service = NotificationService()
    
    try:
        user_id = payload.get("user_id")
        if not user_id:
            logger.warning("order_event_missing_user_id", payload=payload)
            return

        if event_type == OrderEvents.CONFIRMED:
            order_num = payload.get("order_number", "Unknown")
            total = payload.get("total", 0) / 100.0
            await service.send_notification(
                user_id=user_id,
                title="Order Confirmed! 🎉",
                body=f"Your order #{order_num} for ${total:.2f} has been confirmed.",
                notification_type="order_update",
                data={"order_id": payload.get("order_id")},
            )
        
        elif event_type == OrderEvents.SHIPPED:
            order_num = payload.get("order_number", "Unknown")
            tracking = payload.get("tracking_url", "")
            await service.send_notification(
                user_id=user_id,
                title="Your Order is on the way! 🚚",
                body=f"Order #{order_num} has shipped.",
                notification_type="order_update",
                data={"order_id": payload.get("order_id"), "tracking_url": tracking},
            )
            
    except Exception as e:
        # We catch broad exceptions to prevent consumer loop termination.
        # In a production system, we might route failed messages to a DLQ (Dead Letter Queue).
        logger.error("failed_to_handle_order_event", error=str(e), payload=payload)


async def start_consumers() -> None:
    """Initialize and start all Kafka consumers for the notification service."""
    try:
        consumer = await KafkaEventConsumer.get_instance(group_id="notification-service-group")
        
        # Register handlers
        consumer.register_handler(KafkaTopics.ORDER_EVENTS, handle_order_events)
        # consumer.register_handler(KafkaTopics.USER_EVENTS, handle_user_events)
        
        # Start consuming in the background
        asyncio.create_task(consumer.start_consuming())
        logger.info("notification_consumers_started")
    except Exception as e:
        logger.error("failed_to_start_notification_consumers", error=str(e))
