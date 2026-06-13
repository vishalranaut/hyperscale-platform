"""HyperScale Platform — Kafka Event Producer.

Async Kafka producer singleton using aiokafka with retry logic,
dead-letter-queue support, and structured message serialization.

Example:
    >>> producer = await KafkaEventProducer.get_instance()
    >>> await producer.publish(
    ...     topic=KafkaTopics.USER_EVENTS,
    ...     event_type=UserEvents.REGISTERED,
    ...     payload={"user_id": "abc123", "email": "user@example.com"},
    ... )
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiokafka import AIOKafkaProducer

from shared.config import get_settings
from shared.kafka.schemas import EventMetadata, KafkaMessage, KafkaTopics
from shared.logging import get_logger, correlation_id_ctx

logger = get_logger(__name__)


class KafkaEventProducer:
    """Singleton async Kafka producer with retry and dead-letter-queue.

    Uses aiokafka for non-blocking message production. Messages are
    serialized using the KafkaMessage envelope format. Failed messages
    after max retries are sent to the dead-letter topic.

    Attributes:
        MAX_RETRIES: Maximum number of send attempts before DLQ.
        RETRY_BACKOFF_BASE: Base seconds for exponential backoff.

    Example:
        >>> producer = await KafkaEventProducer.get_instance()
        >>> await producer.publish("topic", "event.type", {"key": "value"})
        >>> await producer.close()
    """

    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE: float = 0.5

    _instance: "KafkaEventProducer | None" = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        self._settings = get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._started = False

    @classmethod
    async def get_instance(cls) -> "KafkaEventProducer":
        """Get or create the singleton producer instance.

        Returns:
            The shared KafkaEventProducer instance.
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance.start()
            return cls._instance

    async def start(self) -> None:
        """Initialize and start the Kafka producer.

        Creates the aiokafka producer with idempotence enabled and
        starts it. This is called automatically by ``get_instance()``.
        """
        if self._started:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.KAFKA_BOOTSTRAP_SERVERS,
            enable_idempotence=self._settings.KAFKA_ENABLE_IDEMPOTENCE,
            acks="all",
            max_request_size=1048576,  # 1 MB
            compression_type="gzip",
            linger_ms=10,
            retry_backoff_ms=500,
        )
        await self._producer.start()
        self._started = True
        logger.info(
            "kafka_producer_started",
            bootstrap_servers=self._settings.KAFKA_BOOTSTRAP_SERVERS,
        )

    async def close(self) -> None:
        """Flush pending messages and close the producer."""
        if self._producer and self._started:
            await self._producer.stop()
            self._started = False
            logger.info("kafka_producer_stopped")

    async def publish(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
        source_service: str | None = None,
    ) -> None:
        """Publish an event to a Kafka topic with retry logic.

        Messages are wrapped in the KafkaMessage envelope with metadata
        for tracing and deduplication. On failure after max retries,
        the message is sent to the dead-letter topic.

        Args:
            topic: The Kafka topic to publish to.
            event_type: Dot-separated event type (e.g., 'user.registered').
            payload: Event-specific data dictionary.
            key: Optional partition key for ordering guarantees.
            headers: Optional additional Kafka headers.
            source_service: Override the source service name in metadata.

        Raises:
            RuntimeError: If the producer has not been started.

        Example:
            >>> await producer.publish(
            ...     topic="hyperscale.user.events",
            ...     event_type="user.registered",
            ...     payload={"user_id": "abc123"},
            ...     key="abc123",
            ... )
        """
        if not self._producer or not self._started:
            raise RuntimeError("Kafka producer not started. Call start() first.")

        # Build message envelope
        metadata = EventMetadata(
            source_service=source_service or self._settings.SERVICE_NAME,
            correlation_id=correlation_id_ctx.get(None) or "",
        )
        message = KafkaMessage(
            event_type=event_type,
            payload=payload,
            metadata=metadata,
        )

        # Prepare headers
        kafka_headers: list[tuple[str, bytes]] | None = None
        if headers:
            kafka_headers = [(k, v.encode("utf-8")) for k, v in headers.items()]

        # Prepare key
        key_bytes = key.encode("utf-8") if key else None

        # Retry loop with exponential backoff
        last_error: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                await self._producer.send_and_wait(
                    topic=topic,
                    value=message.serialize(),
                    key=key_bytes,
                    headers=kafka_headers,
                )
                logger.info(
                    "kafka_message_published",
                    topic=topic,
                    event_type=event_type,
                    idempotency_key=metadata.idempotency_key,
                )
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "kafka_publish_retry",
                    topic=topic,
                    event_type=event_type,
                    attempt=attempt,
                    max_retries=self.MAX_RETRIES,
                    error=str(e),
                )
                if attempt < self.MAX_RETRIES:
                    backoff = self.RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)

        # All retries exhausted — send to dead-letter queue
        logger.error(
            "kafka_publish_failed_dlq",
            topic=topic,
            event_type=event_type,
            error=str(last_error),
        )
        await self._send_to_dlq(topic, message, last_error)

    async def _send_to_dlq(
        self,
        original_topic: str,
        message: KafkaMessage,
        error: Exception | None,
    ) -> None:
        """Send a failed message to the dead-letter queue.

        Args:
            original_topic: The topic the message was originally intended for.
            message: The failed KafkaMessage.
            error: The last exception that caused the failure.
        """
        if not self._producer:
            return

        dlq_payload = {
            "original_topic": original_topic,
            "original_event_type": message.event_type,
            "original_payload": message.payload,
            "original_metadata": message.metadata.model_dump(mode="json"),
            "error": str(error) if error else "unknown",
        }
        dlq_message = KafkaMessage(
            event_type="dlq.message_failed",
            payload=dlq_payload,
            metadata=EventMetadata(
                source_service=self._settings.SERVICE_NAME,
            ),
        )
        try:
            await self._producer.send_and_wait(
                topic=KafkaTopics.DEAD_LETTER,
                value=dlq_message.serialize(),
            )
            logger.info(
                "kafka_dlq_message_sent",
                original_topic=original_topic,
                original_event_type=message.event_type,
            )
        except Exception as dlq_error:
            logger.critical(
                "kafka_dlq_send_failed",
                original_topic=original_topic,
                error=str(dlq_error),
            )

    async def publish_batch(
        self,
        topic: str,
        messages: list[tuple[str, dict[str, Any], str | None]],
        source_service: str | None = None,
    ) -> int:
        """Publish multiple events in a batch.

        Args:
            topic: The Kafka topic to publish to.
            messages: List of (event_type, payload, optional_key) tuples.
            source_service: Override the source service name.

        Returns:
            Number of successfully published messages.
        """
        success_count = 0
        for event_type, payload, key in messages:
            try:
                await self.publish(
                    topic=topic,
                    event_type=event_type,
                    payload=payload,
                    key=key,
                    source_service=source_service,
                )
                success_count += 1
            except Exception as e:
                logger.error(
                    "kafka_batch_publish_error",
                    event_type=event_type,
                    error=str(e),
                )
        return success_count
