"""HyperScale Platform — Product Service REST API Views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from services.product_service.domain.schemas import (
    CreateCategoryRequest,
    CreateProductRequest,
    ProductSearchParams,
    UpdateInventoryRequest,
    UpdateProductRequest,
)
from services.product_service.repositories.product_repository import (
    CategoryRepository,
    ProductRepository,
    VariantRepository,
)
from services.product_service.services.product_service import ProductService
from shared.auth.permissions import IsAdminUser, IsAuthenticated
from shared.logging import get_logger

logger = get_logger(__name__)


def _get_service() -> ProductService:
    """Factory to create ProductService with dependencies."""
    return ProductService(
        product_repo=ProductRepository(),
        category_repo=CategoryRepository(),
        variant_repo=VariantRepository(),
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def create_product(request: Request) -> Response:
    """Create a new product.

    POST /api/v1/products

    Returns:
        201: Created product response.
    """
    data = CreateProductRequest(**request.data)
    service = _get_service()
    result = await service.create_product(data)
    return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
async def list_products(request: Request) -> Response:
    """Search and list products.

    GET /api/v1/products?query=...&category_id=...&page=1

    Returns:
        200: Paginated product response.
    """
    params = ProductSearchParams(
        query=request.query_params.get("query"),
        category_id=request.query_params.get("category_id"),
        brand=request.query_params.get("brand"),
        min_price=_parse_int(request.query_params.get("min_price")),
        max_price=_parse_int(request.query_params.get("max_price")),
        status=request.query_params.get("status"),
        in_stock=_parse_bool(request.query_params.get("in_stock")),
        sort_by=request.query_params.get("sort_by", "created_at"),
        sort_order=request.query_params.get("sort_order", "desc"),
        page=int(request.query_params.get("page", 1)),
        page_size=int(request.query_params.get("page_size", 20)),
    )
    service = _get_service()
    result = await service.search_products(params)
    return Response(result.model_dump(mode="json"))


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
async def product_detail(request: Request, product_id: str) -> Response:
    """Get, update, or delete a product.

    GET /api/v1/products/{product_id}
    PUT /api/v1/products/{product_id}
    DELETE /api/v1/products/{product_id}
    """
    service = _get_service()

    if request.method == "GET":
        result = await service.get_product(product_id)
        return Response(result.model_dump(mode="json"))

    if request.method == "PUT":
        data = UpdateProductRequest(**request.data)
        result = await service.update_product(product_id, data)
        return Response(result.model_dump(mode="json"))

    if request.method == "DELETE":
        await service.delete_product(product_id)
        return Response({"message": "Product deleted"}, status=status.HTTP_200_OK)

    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def update_inventory(request: Request, product_id: str) -> Response:
    """Update product inventory.

    POST /api/v1/products/{product_id}/inventory

    Request Body:
        {"delta": 10, "reason": "restock"}
    """
    data = UpdateInventoryRequest(**request.data)
    service = _get_service()
    result = await service.update_inventory(product_id, data)
    return Response(result.model_dump(mode="json"))


@api_view(["GET"])
@permission_classes([AllowAny])
async def category_tree(request: Request) -> Response:
    """Get the full category tree.

    GET /api/v1/categories/tree
    """
    service = _get_service()
    result = await service.get_category_tree()
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAdminUser])
async def create_category(request: Request) -> Response:
    """Create a product category.

    POST /api/v1/categories
    """
    data = CreateCategoryRequest(**request.data)
    service = _get_service()
    result = await service.create_category(data)
    return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


def _parse_int(value: str | None) -> int | None:
    """Parse optional int query param."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_bool(value: str | None) -> bool | None:
    """Parse optional bool query param."""
    if value is None:
        return None
    return value.lower() in ("true", "1", "yes")
