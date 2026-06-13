"""HyperScale Platform — Order Service REST API Views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from services.order_service.domain.schemas import (
    AddCartItemRequest,
    CancelOrderRequest,
    PlaceOrderRequest,
    RefundOrderRequest,
)
from services.order_service.services.order_service import CartService, OrderService
from shared.auth.permissions import IsAdminUser, IsAuthenticated
from shared.logging import get_logger

logger = get_logger(__name__)


class _OrderRepo:
    """Lightweight order repository for view layer dependency injection."""

    async def create(self, **fields):
        from services.order_service.domain.models import Order
        order = Order(**fields)
        await order.insert()
        return order

    async def get_by_id(self, order_id):
        from services.order_service.domain.models import Order
        from beanie import PydanticObjectId
        try:
            order = await Order.get(PydanticObjectId(order_id))
            return order if order and not order.is_deleted else None
        except Exception:
            return None

    async def update(self, order_id, **fields):
        from services.order_service.domain.models import Order
        from beanie import PydanticObjectId
        from beanie.operators import Set
        from datetime import UTC, datetime
        order = await self.get_by_id(order_id)
        if order:
            fields["updated_at"] = datetime.now(UTC)
            await order.update(Set(fields))
            await order.sync()
        return order

    async def get_by_user(self, user_id, page=1, page_size=20, status_filter=None):
        from services.order_service.domain.models import Order
        filters = [Order.user_id == user_id, Order.is_deleted == False]  # noqa: E712
        if status_filter:
            filters.append(Order.status == status_filter)
        total = await Order.find(*filters).count()
        skip = (page - 1) * page_size
        orders = await Order.find(*filters).sort("-created_at").skip(skip).limit(page_size).to_list()
        return orders, total


def _get_services():
    """Factory to create order services."""
    repo = _OrderRepo()
    cart = CartService()
    return OrderService(order_repo=repo, cart_service=cart), cart


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def get_cart(request: Request) -> Response:
    """Get the current user's cart.

    GET /api/v1/cart
    """
    _, cart_service = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    result = await cart_service.get_cart(user_id)
    return Response(result.model_dump(mode="json"))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def add_cart_item(request: Request) -> Response:
    """Add an item to the cart.

    POST /api/v1/cart/items
    """
    _, cart_service = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    data = AddCartItemRequest(**request.data)
    result = await cart_service.add_item(user_id, data)
    return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
async def remove_cart_item(request: Request, product_id: str) -> Response:
    """Remove an item from the cart.

    DELETE /api/v1/cart/items/{product_id}
    """
    _, cart_service = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    variant_id = request.query_params.get("variant_id", "")
    result = await cart_service.remove_item(user_id, product_id, variant_id)
    return Response(result.model_dump(mode="json"))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def place_order(request: Request) -> Response:
    """Place an order from the current cart.

    POST /api/v1/orders
    """
    order_service, _ = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    data = PlaceOrderRequest(**request.data)
    result = await order_service.place_order(user_id, data)
    return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def get_order(request: Request, order_id: str) -> Response:
    """Get an order by ID.

    GET /api/v1/orders/{order_id}
    """
    order_service, _ = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    result = await order_service.get_order(order_id, user_id)
    return Response(result.model_dump(mode="json"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def list_orders(request: Request) -> Response:
    """List user's orders.

    GET /api/v1/orders?page=1&page_size=20&status=confirmed
    """
    order_service, _ = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    result = await order_service.get_user_orders(
        user_id,
        page=int(request.query_params.get("page", 1)),
        page_size=int(request.query_params.get("page_size", 20)),
        status_filter=request.query_params.get("status"),
    )
    return Response(result.model_dump(mode="json"))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def cancel_order(request: Request, order_id: str) -> Response:
    """Cancel an order.

    POST /api/v1/orders/{order_id}/cancel
    """
    order_service, _ = _get_services()
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    data = CancelOrderRequest(**request.data) if request.data else CancelOrderRequest()
    result = await order_service.cancel_order(order_id, user_id, data.reason)
    return Response(result.model_dump(mode="json"))


@api_view(["POST"])
@permission_classes([IsAdminUser])
async def refund_order(request: Request, order_id: str) -> Response:
    """Refund an order (admin only).

    POST /api/v1/orders/{order_id}/refund
    """
    order_service, _ = _get_services()
    data = RefundOrderRequest(**request.data) if request.data else RefundOrderRequest()
    result = await order_service.refund_order(order_id, data.amount, data.reason)
    return Response(result.model_dump(mode="json"))
