"""HyperScale Platform — Kafka Event Consumer.

Base consumer class using aiokafka with at-least-once delivery guarantees,
idempotency tracking via Redis, and graceful shutdown handling.

Example:
    >>> class UserEventConsumer(BaseKafkaConsumer):
    ...     topics = ["hyperscale.user.events"]
    ...     group_id = "notification-service"
    ...
    ...     async def handle_event(self, message: KafkaMessage) -> None:
    ...         if message.event_type == "user.registered":
    ...             await send_welcome_email(message.payload)
    ...
    >>> consumer = UserEventConsumer()
    >>> await consumer.start()
"""

from __future__ import annotations

import asyncio
import signal
from abc import ABC, abstractmethod
from typing import Any

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from shared.config import get_settings
from shared.kafka.schemas import KafkaMessage
from shared.logging import get_logger, set_log_context

logger = get_logger(__name__)


class BaseKafkaConsumer(ABC):
    """Abstract base class for Kafka event consumers.

    Provides at-least-once delivery guarantees with manual offset commits
    and Redis-based idempotency tracking. Subclasses implement the
    ``handle_event`` method for business logic.

    Subclass Attributes:
        topics: List of Kafka topic names to subscribe to.
        group_id: Consumer group ID for this consumer.
        max_poll_records: Maximum records per poll (default: 50).
        enable_idempotency: Whether to track processed messages (default: True).
        idempotency_ttl: TTL in seconds for idempotency keys (default: 86400 = 24h).

    Example:
        >>> class OrderConsumer(BaseKafkaConsumer):
        ...     topics = ["hyperscale.order.events"]
        ...     group_id = "analytics-service"
        ...
        ...     async def handle_event(self, message: KafkaMessage) -> None:
        ...         await track_order_event(message)
    """

    topics: list[str] = []
    group_id: str = ""
    max_poll_records: int = 50
    enable_idempotency: bool = True
    idempotency_ttl: int = 86400  # 24 hours

    def __init__(self) -> None:
        self._settings = get_settings()
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._redis: Any | None = None

        if not self.topics:
            raise ValueError(f"{self.__class__.__name__} must define 'topics'")
        if not self.group_id:
            self.group_id = (
                f"{self._settings.KAFKA_CONSUMER_GROUP_PREFIX}.{self.__class__.__name__}"
            )

    async def _get_redis(self) -> Any:
        """Lazily initialize Redis client for idempotency tracking.

        Returns:
            The async Redis client instance.
        """
        if self._redis is None and self.enable_idempotency:
            try:
                from shared.cache.redis_client import get_redis_client

                self._redis = await get_redis_client()
            except Exception as e:
                logger.warning("redis_unavailable_for_idempotency", error=str(e))
        return self._redis

    async def _is_duplicate(self, idempotency_key: str) -> bool:
        """Check if a message has already been processed.

        Args:
            idempotency_key: The unique key from the message metadata.

        Returns:
            True if the message has been processed before.
        """
        if not self.enable_idempotency:
            return False

        redis = await self._get_redis()
        if redis is None:
            return False

        try:
            key = f"idempotency:{self.group_id}:{idempotency_key}"
            return bool(await redis.exists(key))
        except Exception as e:
            logger.warning("idempotency_check_failed", error=str(e))
            return False

    async def _mark_processed(self, idempotency_key: str) -> None:
        """Mark a message as processed in the idempotency store.

        Args:
            idempotency_key: The unique key from the message metadata.
        """
        if not self.enable_idempotency:
            return

        redis = await self._get_redis()
        if redis is None:
            return

        try:
            key = f"idempotency:{self.group_id}:{idempotency_key}"
            await redis.setex(key, self.idempotency_ttl, "1")
        except Exception as e:
            logger.warning("idempotency_mark_failed", error=str(e))

    @abstractmethod
    async def handle_event(self, message: KafkaMessage) -> None:
        """Process a single Kafka event.

        Subclasses must implement this method with their business logic.
        This method is called after deserialization and idempotency checks.

        Args:
            message: The deserialized KafkaMessage.

        Raises:
            Exception: Any exception will prevent offset commit (at-least-once).
        """
        ...

    async def on_error(self, record: ConsumerRecord, error: Exception) -> None:
        """Handle processing errors for a consumer record.

        Override this method to implement custom error handling (e.g.,
        sending to a dead-letter queue, alerting, or retry logic).

        Args:
            record: The raw Kafka consumer record that failed.
            error: The exception that occurred during processing.
        """
        logger.error(
            "consumer_processing_error",
            topic=record.topic,
            partition=record.partition,
            offset=record.offset,
            error=str(error),
            error_type=type(error).__name__,
        )

    async def start(self) -> None:
        """Start the Kafka consumer and begin processing messages.

        Sets up signal handlers for graceful shutdown and enters the
        consume loop. Messages are processed one at a time with manual
        offset commits after successful processing.
        """
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self._settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.group_id,
            auto_offset_reset=self._settings.KAFKA_AUTO_OFFSET_RESET,
            enable_auto_commit=False,
            max_poll_records=self.max_poll_records,
        )

        await self._consumer.start()
        self._running = True

        logger.info(
            "kafka_consumer_started",
            consumer=self.__class__.__name__,
            topics=self.topics,
            group_id=self.group_id,
        )

        # Register graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        try:
            await self._consume_loop()
        finally:
            await self.stop()

    async def _consume_loop(self) -> None:
        """Main consume loop processing messages with at-least-once delivery."""
        if not self._consumer:
            return

        while self._running:
            try:
                records = await self._consumer.getmany(timeout_ms=1000)
                for topic_partition, partition_records in records.items():
                    for record in partition_records:
                        await self._process_record(record)

                # Commit offsets after successful processing
                if records:
                    await self._consumer.commit()

            except asyncio.CancelledError:
                logger.info("consumer_cancelled", consumer=self.__class__.__name__)
                break
            except Exception as e:
                logger.error(
                    "consumer_loop_error",
                    consumer=self.__class__.__name__,
                    error=str(e),
                )
                await asyncio.sleep(1)  # Backoff on errors

    async def _process_record(self, record: ConsumerRecord) -> None:
        """Process a single Kafka consumer record.

        Deserializes the message, checks idempotency, and delegates
        to the ``handle_event`` method.

        Args:
            record: The raw Kafka consumer record.
        """
        try:
            message = KafkaMessage.deserialize(record.value)

            # Set logging context from message metadata
            set_log_context(
                correlation_id=message.metadata.correlation_id,
            )

            # Check for duplicates
            if await self._is_duplicate(message.metadata.idempotency_key):
                logger.debug(
                    "duplicate_message_skipped",
                    event_type=message.event_type,
                    idempotency_key=message.metadata.idempotency_key,
                )
                return

            logger.info(
                "processing_event",
                event_type=message.event_type,
                source_service=message.metadata.source_service,
                idempotency_key=message.metadata.idempotency_key,
            )

            await self.handle_event(message)

            # Mark as processed
            await self._mark_processed(message.metadata.idempotency_key)

        except Exception as e:
            await self.on_error(record, e)

    async def stop(self) -> None:
        """Gracefully stop the consumer.

        Commits any pending offsets and closes the consumer connection.
        """
        self._running = False
        if self._consumer:
            try:
                await self._consumer.commit()
            except Exception:
                pass
            await self._consumer.stop()
            logger.info(
                "kafka_consumer_stopped",
                consumer=self.__class__.__name__,
            )
