"""HyperScale Platform — Place Order Saga.

Orchestrated saga pattern for order placement. Coordinates multiple
service calls with compensation (rollback) logic on failure.

Architectural Note (Senior Dev):
    Distributed transactions across microservices cannot rely on ACID database
    locks (like two-phase commit), as that creates tight coupling and severe
    latency bottlenecks. Instead, we use the Saga Pattern.
    
    Here, the Order Service acts as the Orchestrator. It attempts to execute
    a sequence of local transactions (Steps). If any step fails (e.g., payment
    is declined), it runs "Compensations" (rollbacks) in reverse order to ensure
    eventual consistency across the system.

Saga Steps:
    1. ValidateCart — check items are still available
    2. ReserveInventory — gRPC call to product_service
    3. CreatePaymentIntent — call payment provider
    4. ConfirmOrder — save order, emit order.confirmed
    5. TriggerFulfillment — emit order.fulfillment_started

Compensations (on failure):
    - ReleaseInventory — reverse inventory reservation
    - CancelPaymentIntent — void the payment authorization
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from shared.exceptions import PaymentError, ServiceUnavailableError, ValidationError
from shared.logging import get_logger

logger = get_logger(__name__)


class SagaState(str, Enum):
    """Saga execution states."""

    STARTED = "started"
    CART_VALIDATED = "cart_validated"
    INVENTORY_RESERVED = "inventory_reserved"
    PAYMENT_AUTHORIZED = "payment_authorized"
    ORDER_CONFIRMED = "order_confirmed"
    FULFILLMENT_TRIGGERED = "fulfillment_triggered"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    FAILED = "failed"


class SagaStep:
    """Represents a single step in the saga with its compensation.

    Attributes:
        name: Human-readable step name.
        execute: Async function to execute this step.
        compensate: Async function to roll back this step.
    """

    def __init__(
        self,
        name: str,
        execute: Any,
        compensate: Any | None = None,
    ) -> None:
        self.name = name
        self.execute = execute
        self.compensate = compensate


class PlaceOrderSaga:
    """Orchestrated saga for placing an order.

    Executes steps sequentially and rolls back completed steps
    in reverse order if any step fails.

    Args:
        order_repo: Order repository for persistence.
        product_client: gRPC client for product service.
        payment_client: Payment provider client.
        kafka_producer: Kafka event producer.

    Example:
        >>> saga = PlaceOrderSaga(
        ...     order_repo=order_repo,
        ...     product_client=product_grpc_client,
        ...     payment_client=stripe_client,
        ...     kafka_producer=kafka_producer,
        ... )
        >>> order = await saga.execute(
        ...     user_id="user123",
        ...     cart_items=cart.items,
        ...     shipping_address=address,
        ...     payment_method_id="pm_xxx",
        ... )
    """

    def __init__(
        self,
        order_repo: Any,
        product_client: Any | None = None,
        payment_client: Any | None = None,
        kafka_producer: Any | None = None,
    ) -> None:
        self._order_repo = order_repo
        self._product_client = product_client
        self._payment_client = payment_client
        self._kafka = kafka_producer
        self._completed_steps: list[SagaStep] = []
        self._context: dict[str, Any] = {}

    async def execute(
        self,
        user_id: str,
        cart_items: list[dict[str, Any]],
        shipping_address: dict[str, Any],
        billing_address: dict[str, Any] | None = None,
        payment_method_id: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Execute the place order saga.

        Args:
            user_id: The ordering user's ID.
            cart_items: List of cart item dictionaries.
            shipping_address: Shipping address dictionary.
            billing_address: Billing address (defaults to shipping).
            payment_method_id: Payment method identifier.
            notes: Optional order notes.

        Returns:
            Dictionary with order_id, order_number, and status.

        Raises:
            ValidationError: If cart validation fails.
            ServiceUnavailableError: If a downstream service is unreachable.
            PaymentError: If payment authorization fails.
        """
        self._context = {
            "user_id": user_id,
            "cart_items": cart_items,
            "shipping_address": shipping_address,
            "billing_address": billing_address or shipping_address,
            "payment_method_id": payment_method_id,
            "notes": notes,
            "order_number": f"ORD-{uuid.uuid4().hex[:12].upper()}",
            "saga_id": str(uuid.uuid4()),
        }

        # Define saga steps
        steps = [
            SagaStep("validate_cart", self._validate_cart),
            SagaStep("reserve_inventory", self._reserve_inventory, self._release_inventory),
            SagaStep("create_payment_intent", self._create_payment_intent, self._cancel_payment),
            SagaStep("confirm_order", self._confirm_order),
            SagaStep("trigger_fulfillment", self._trigger_fulfillment),
        ]

        logger.info(
            "saga_started",
            saga_id=self._context["saga_id"],
            order_number=self._context["order_number"],
            user_id=user_id,
        )

        for step in steps:
            try:
                logger.info(
                    "saga_step_executing",
                    step=step.name,
                    saga_id=self._context["saga_id"],
                )
                await step.execute()
                self._completed_steps.append(step)
                logger.info(
                    "saga_step_completed",
                    step=step.name,
                    saga_id=self._context["saga_id"],
                )
            except Exception as e:
                logger.error(
                    "saga_step_failed",
                    step=step.name,
                    saga_id=self._context["saga_id"],
                    error=str(e),
                )
                await self._compensate(e)
                raise

        logger.info(
            "saga_completed",
            saga_id=self._context["saga_id"],
            order_id=self._context.get("order_id"),
        )

        return {
            "order_id": self._context.get("order_id", ""),
            "order_number": self._context["order_number"],
            "status": "confirmed",
        }

    async def _compensate(self, original_error: Exception) -> None:
        """Execute compensation steps in reverse order.

        Args:
            original_error: The exception that triggered compensation.
        """
        logger.warning(
            "saga_compensating",
            saga_id=self._context["saga_id"],
            steps_to_compensate=len(self._completed_steps),
        )

        for step in reversed(self._completed_steps):
            if step.compensate:
                try:
                    logger.info(
                        "saga_compensating_step",
                        step=step.name,
                        saga_id=self._context["saga_id"],
                    )
                    await step.compensate()
                except Exception as comp_error:
                    logger.critical(
                        "saga_compensation_failed",
                        step=step.name,
                        saga_id=self._context["saga_id"],
                        original_error=str(original_error),
                        compensation_error=str(comp_error),
                    )

    async def _validate_cart(self) -> None:
        """Step 1: Validate cart items are available."""
        cart_items = self._context["cart_items"]
        if not cart_items:
            raise ValidationError(message="Cart is empty")

        # Calculate totals
        subtotal = 0
        validated_items = []
        for item in cart_items:
            quantity = item.get("quantity", 1)
            unit_price = item.get("unit_price", 0)
            total_price = quantity * unit_price
            subtotal += total_price

            validated_items.append({
                **item,
                "total_price": total_price,
            })

        # Calculate tax (simplified — 8.5% rate)
        tax = int(subtotal * 0.085)
        shipping_cost = 0 if subtotal >= 5000 else 999  # Free shipping over $50

        self._context["validated_items"] = validated_items
        self._context["subtotal"] = subtotal
        self._context["tax"] = tax
        self._context["shipping_cost"] = shipping_cost
        self._context["total"] = subtotal + tax + shipping_cost

    async def _reserve_inventory(self) -> None:
        """Step 2: Reserve inventory via product service.

        In production, this would make a gRPC call to the product service.
        """
        reservation_id = str(uuid.uuid4())
        self._context["reservation_id"] = reservation_id

        if self._product_client:
            try:
                # gRPC call: product_service.ReserveInventory
                items = [
                    {
                        "product_id": item["product_id"],
                        "variant_id": item.get("variant_id", ""),
                        "quantity": item["quantity"],
                    }
                    for item in self._context["validated_items"]
                ]
                # response = await self._product_client.ReserveInventory(...)
                logger.info("inventory_reserved", reservation_id=reservation_id)
            except Exception as e:
                raise ServiceUnavailableError(
                    message="Failed to reserve inventory",
                    detail={"error": str(e)},
                )
        else:
            logger.info("inventory_reservation_skipped", reason="no_product_client")

    async def _release_inventory(self) -> None:
        """Compensation: Release reserved inventory."""
        reservation_id = self._context.get("reservation_id")
        if reservation_id and self._product_client:
            try:
                # gRPC call: product_service.ReleaseInventory
                logger.info("inventory_released", reservation_id=reservation_id)
            except Exception as e:
                logger.error("inventory_release_failed", error=str(e))

    async def _create_payment_intent(self) -> None:
        """Step 3: Create payment intent with payment provider."""
        total = self._context["total"]
        currency = "USD"
        payment_method_id = self._context["payment_method_id"]

        if self._payment_client:
            try:
                # In production: stripe.PaymentIntent.create(...)
                payment_intent_id = f"pi_{uuid.uuid4().hex[:24]}"
                self._context["payment_intent_id"] = payment_intent_id
                self._context["payment_status"] = "authorized"
            except Exception as e:
                raise PaymentError(
                    message="Payment authorization failed",
                    detail={"error": str(e)},
                )
        else:
            # Mock payment for development
            self._context["payment_intent_id"] = f"pi_mock_{uuid.uuid4().hex[:12]}"
            self._context["payment_status"] = "authorized"

    async def _cancel_payment(self) -> None:
        """Compensation: Cancel/void the payment intent."""
        payment_intent_id = self._context.get("payment_intent_id")
        if payment_intent_id and self._payment_client:
            try:
                # stripe.PaymentIntent.cancel(payment_intent_id)
                logger.info("payment_cancelled", payment_intent_id=payment_intent_id)
            except Exception as e:
                logger.error("payment_cancel_failed", error=str(e))

    async def _confirm_order(self) -> None:
        """Step 4: Save the confirmed order to the database."""
        from services.order_service.domain.models import OrderStatus

        order = await self._order_repo.create(
            order_number=self._context["order_number"],
            user_id=self._context["user_id"],
            items=self._context["validated_items"],
            subtotal=self._context["subtotal"],
            tax=self._context["tax"],
            shipping_cost=self._context["shipping_cost"],
            total=self._context["total"],
            status=OrderStatus.CONFIRMED.value,
            payment={
                "provider": "stripe",
                "payment_intent_id": self._context.get("payment_intent_id", ""),
                "status": self._context.get("payment_status", "pending"),
                "amount": self._context["total"],
                "currency": "USD",
            },
            shipping_address=self._context["shipping_address"],
            billing_address=self._context["billing_address"],
            notes=self._context.get("notes", ""),
            reservation_id=self._context.get("reservation_id", ""),
            saga_state=SagaState.ORDER_CONFIRMED.value,
        )
        self._context["order_id"] = str(order.id)

        # Emit order confirmed event
        if self._kafka:
            try:
                from shared.kafka.schemas import KafkaTopics, OrderEvents

                await self._kafka.publish(
                    topic=KafkaTopics.ORDER_EVENTS,
                    event_type=OrderEvents.CONFIRMED,
                    payload={
                        "order_id": str(order.id),
                        "order_number": order.order_number,
                        "user_id": order.user_id,
                        "total": order.total,
                        "items_count": len(order.items),
                    },
                    key=str(order.id),
                )
            except Exception as e:
                logger.error("kafka_publish_failed", error=str(e))

    async def _trigger_fulfillment(self) -> None:
        """Step 5: Emit fulfillment started event."""
        if self._kafka:
            try:
                from shared.kafka.schemas import KafkaTopics, OrderEvents

                await self._kafka.publish(
                    topic=KafkaTopics.ORDER_EVENTS,
                    event_type=OrderEvents.FULFILLMENT_STARTED,
                    payload={
                        "order_id": self._context.get("order_id", ""),
                        "order_number": self._context["order_number"],
                    },
                    key=self._context.get("order_id", ""),
                )
            except Exception as e:
                logger.error("kafka_publish_failed", error=str(e))
