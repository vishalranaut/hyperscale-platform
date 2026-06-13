"""HyperScale Platform — Order Service Cart & Business Logic.

Implements Redis-backed shopping cart and order management operations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import orjson

from services.order_service.domain.models import Order, OrderStatus
from services.order_service.domain.schemas import (
    AddCartItemRequest,
    CartItemResponse,
    CartResponse,
    OrderItemResponse,
    OrderResponse,
    PaginatedOrderResponse,
    PaymentInfoResponse,
    PlaceOrderRequest,
    TrackingInfoResponse,
)
from services.order_service.services.saga.place_order_saga import PlaceOrderSaga
from shared.cache.redis_client import get_redis_client
from shared.exceptions import NotFoundError, ValidationError
from shared.kafka.producer import KafkaEventProducer
from shared.kafka.schemas import KafkaTopics, OrderEvents
from shared.logging import get_logger

logger = get_logger(__name__)

CART_TTL = 7 * 24 * 3600  # 7 days


class CartService:
    """Redis-backed shopping cart service.

    Carts are stored in Redis with a 7-day TTL. Each cart is keyed
    by user_id and contains a list of items with pricing.

    Example:
        >>> cart_service = CartService()
        >>> await cart_service.add_item("user123", AddCartItemRequest(
        ...     product_id="prod_abc", quantity=2
        ... ))
    """

    CART_PREFIX = "cart:"

    async def _get_redis(self) -> Any:
        """Get the Redis client."""
        return await get_redis_client()

    def _cart_key(self, user_id: str) -> str:
        """Build the Redis key for a user's cart."""
        return f"{self.CART_PREFIX}{user_id}"

    async def get_cart(self, user_id: str) -> CartResponse:
        """Get the current cart for a user.

        Args:
            user_id: The user's ID.

        Returns:
            CartResponse with items and totals.
        """
        redis = await self._get_redis()
        cart_data = await redis.get(self._cart_key(user_id))

        if not cart_data:
            return CartResponse(user_id=user_id, items=[], subtotal=0, item_count=0)

        items_raw = orjson.loads(cart_data)
        items = [CartItemResponse(**item) for item in items_raw]
        subtotal = sum(item.unit_price * item.quantity for item in items)
        item_count = sum(item.quantity for item in items)

        return CartResponse(
            user_id=user_id,
            items=items,
            subtotal=subtotal,
            item_count=item_count,
        )

    async def add_item(
        self,
        user_id: str,
        data: AddCartItemRequest,
        product_info: dict[str, Any] | None = None,
    ) -> CartResponse:
        """Add an item to the cart or increment quantity.

        Args:
            user_id: The user's ID.
            data: Cart item to add.
            product_info: Optional product details (title, image, price).

        Returns:
            Updated cart response.
        """
        redis = await self._get_redis()
        cart = await self.get_cart(user_id)
        items = [item.model_dump() for item in cart.items]

        # Check if item already in cart
        existing_idx = next(
            (i for i, item in enumerate(items)
             if item["product_id"] == data.product_id
             and item.get("variant_id", "") == data.variant_id),
            None,
        )

        if existing_idx is not None:
            items[existing_idx]["quantity"] += data.quantity
        else:
            new_item = {
                "product_id": data.product_id,
                "variant_id": data.variant_id,
                "quantity": data.quantity,
                "unit_price": product_info.get("price", 0) if product_info else 0,
                "product_title": product_info.get("title", "") if product_info else "",
                "product_image": product_info.get("image", "") if product_info else "",
                "attributes": product_info.get("attributes", {}) if product_info else {},
            }
            items.append(new_item)

        await redis.setex(
            self._cart_key(user_id),
            CART_TTL,
            orjson.dumps(items),
        )

        return await self.get_cart(user_id)

    async def remove_item(self, user_id: str, product_id: str, variant_id: str = "") -> CartResponse:
        """Remove an item from the cart.

        Args:
            user_id: The user's ID.
            product_id: Product to remove.
            variant_id: Variant to remove.

        Returns:
            Updated cart response.
        """
        redis = await self._get_redis()
        cart = await self.get_cart(user_id)
        items = [
            item.model_dump()
            for item in cart.items
            if not (item.product_id == product_id and (item.variant_id or "") == variant_id)
        ]

        if items:
            await redis.setex(self._cart_key(user_id), CART_TTL, orjson.dumps(items))
        else:
            await redis.delete(self._cart_key(user_id))

        return await self.get_cart(user_id)

    async def clear_cart(self, user_id: str) -> None:
        """Clear all items from a user's cart.

        Args:
            user_id: The user's ID.
        """
        redis = await self._get_redis()
        await redis.delete(self._cart_key(user_id))


class OrderService:
    """Business logic layer for order management.

    Coordinates cart operations, order placement (via saga),
    cancellation, and refund workflows.

    Args:
        order_repo: Order repository.
        cart_service: Cart service.
        kafka_producer: Kafka event producer.
    """

    def __init__(
        self,
        order_repo: Any,
        cart_service: CartService | None = None,
        kafka_producer: KafkaEventProducer | None = None,
    ) -> None:
        self._order_repo = order_repo
        self._cart_service = cart_service or CartService()
        self._kafka = kafka_producer

    async def _get_kafka(self) -> KafkaEventProducer:
        """Get or create the Kafka producer."""
        if self._kafka is None:
            self._kafka = await KafkaEventProducer.get_instance()
        return self._kafka

    def _order_to_response(self, order: Order) -> OrderResponse:
        """Convert an Order document to OrderResponse."""
        items = []
        for item in order.items:
            items.append(OrderItemResponse(
                product_id=item.get("product_id", ""),
                variant_id=item.get("variant_id", ""),
                product_title=item.get("product_title", ""),
                product_image=item.get("product_image", ""),
                sku=item.get("sku", ""),
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price", 0),
                total_price=item.get("total_price", 0),
            ))

        payment = None
        if order.payment:
            payment = PaymentInfoResponse(
                provider=order.payment.get("provider", ""),
                transaction_id=order.payment.get("transaction_id", ""),
                status=order.payment.get("status", "pending"),
                amount=order.payment.get("amount", 0),
                currency=order.payment.get("currency", "USD"),
            )

        tracking = None
        if order.tracking:
            tracking = TrackingInfoResponse(**order.tracking)

        return OrderResponse(
            id=str(order.id),
            order_number=order.order_number,
            user_id=order.user_id,
            items=items,
            subtotal=order.subtotal,
            tax=order.tax,
            shipping_cost=order.shipping_cost,
            discount=order.discount,
            total=order.total,
            currency=order.currency,
            status=order.status.value if hasattr(order.status, "value") else str(order.status),
            payment=payment,
            shipping_address=order.shipping_address,
            billing_address=order.billing_address,
            tracking=tracking,
            notes=order.notes,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    async def place_order(
        self,
        user_id: str,
        data: PlaceOrderRequest,
    ) -> OrderResponse:
        """Place an order using the saga pattern.

        Args:
            user_id: The ordering user's ID.
            data: Order placement request.

        Returns:
            Created order response.

        Raises:
            ValidationError: If cart is empty.
        """
        cart = await self._cart_service.get_cart(user_id)
        if not cart.items:
            raise ValidationError(message="Cart is empty")

        cart_items = [item.model_dump() for item in cart.items]
        kafka = await self._get_kafka()

        saga = PlaceOrderSaga(
            order_repo=self._order_repo,
            kafka_producer=kafka,
        )

        result = await saga.execute(
            user_id=user_id,
            cart_items=cart_items,
            shipping_address=data.shipping_address.model_dump(),
            billing_address=data.billing_address.model_dump() if data.billing_address else None,
            payment_method_id=data.payment_method_id,
            notes=data.notes,
        )

        # Clear cart after successful order
        await self._cart_service.clear_cart(user_id)

        order = await self._order_repo.get_by_id(result["order_id"])
        return self._order_to_response(order)

    async def get_order(self, order_id: str, user_id: str | None = None) -> OrderResponse:
        """Get an order by ID.

        Args:
            order_id: The order's ID.
            user_id: Optional user ID for ownership verification.

        Returns:
            Order response.

        Raises:
            NotFoundError: If order not found or unauthorized.
        """
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundError(detail={"resource": "Order", "id": order_id})

        if user_id and order.user_id != user_id:
            raise NotFoundError(detail={"resource": "Order", "id": order_id})

        return self._order_to_response(order)

    async def get_user_orders(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
    ) -> PaginatedOrderResponse:
        """Get paginated orders for a user.

        Args:
            user_id: The user's ID.
            page: Page number.
            page_size: Items per page.
            status_filter: Optional status filter.

        Returns:
            Paginated order response.
        """
        orders, total = await self._order_repo.get_by_user(
            user_id, page, page_size, status_filter
        )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return PaginatedOrderResponse(
            items=[self._order_to_response(o) for o in orders],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    async def cancel_order(
        self,
        order_id: str,
        user_id: str,
        reason: str = "",
    ) -> OrderResponse:
        """Cancel an order.

        Args:
            order_id: The order ID.
            user_id: The user's ID (for ownership check).
            reason: Cancellation reason.

        Returns:
            Updated order response.

        Raises:
            NotFoundError: If order not found.
            ValidationError: If order cannot be cancelled.
        """
        order = await self._order_repo.get_by_id(order_id)
        if order is None or order.user_id != user_id:
            raise NotFoundError(detail={"resource": "Order", "id": order_id})

        cancellable = {OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING}
        current_status = order.status if isinstance(order.status, OrderStatus) else OrderStatus(order.status)

        if current_status not in cancellable:
            raise ValidationError(
                message=f"Order in '{current_status.value}' status cannot be cancelled",
            )

        await self._order_repo.update(
            order_id,
            status=OrderStatus.CANCELLED.value,
            cancel_reason=reason,
        )

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.ORDER_EVENTS,
                event_type=OrderEvents.CANCELLED,
                payload={
                    "order_id": order_id,
                    "user_id": user_id,
                    "reason": reason,
                },
                key=order_id,
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        return await self.get_order(order_id)

    async def refund_order(
        self,
        order_id: str,
        amount: int | None = None,
        reason: str = "",
    ) -> OrderResponse:
        """Refund an order (admin only).

        Args:
            order_id: The order ID.
            amount: Refund amount in cents (None = full refund).
            reason: Refund reason.

        Returns:
            Updated order response.
        """
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundError(detail={"resource": "Order", "id": order_id})

        refund_amount = amount or order.total

        await self._order_repo.update(
            order_id,
            status=OrderStatus.REFUNDED.value,
        )

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.ORDER_EVENTS,
                event_type=OrderEvents.REFUNDED,
                payload={
                    "order_id": order_id,
                    "user_id": order.user_id,
                    "refund_amount": refund_amount,
                    "reason": reason,
                },
                key=order_id,
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        return await self.get_order(order_id)
