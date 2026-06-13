"""HyperScale Platform — Product Service Business Logic.

Service layer implementing product catalog, search, inventory
management, and category tree operations.
"""

from __future__ import annotations

from typing import Any

from services.product_service.domain.models import Product
from services.product_service.domain.schemas import (
    CategoryResponse,
    CategoryTreeResponse,
    CreateCategoryRequest,
    CreateProductRequest,
    InventoryResponse,
    PaginatedProductResponse,
    ProductResponse,
    ProductSearchParams,
    UpdateInventoryRequest,
    UpdateProductRequest,
    VariantResponse,
)
from services.product_service.repositories.product_repository import (
    CategoryRepository,
    ProductRepository,
    VariantRepository,
)
from shared.cache.redis_client import cache_aside, invalidate_cache
from shared.exceptions import ConflictError, NotFoundError, ValidationError
from shared.kafka.producer import KafkaEventProducer
from shared.kafka.schemas import KafkaTopics, ProductEvents
from shared.logging import get_logger

logger = get_logger(__name__)


class ProductService:
    """Business logic layer for product management.

    Args:
        product_repo: Product repository instance.
        category_repo: Category repository instance.
        variant_repo: Variant repository instance.
        kafka_producer: Kafka event producer (optional).
    """

    def __init__(
        self,
        product_repo: ProductRepository,
        category_repo: CategoryRepository,
        variant_repo: VariantRepository,
        kafka_producer: KafkaEventProducer | None = None,
    ) -> None:
        self._product_repo = product_repo
        self._category_repo = category_repo
        self._variant_repo = variant_repo
        self._kafka = kafka_producer

    async def _get_kafka(self) -> KafkaEventProducer:
        """Get or create the Kafka producer."""
        if self._kafka is None:
            self._kafka = await KafkaEventProducer.get_instance()
        return self._kafka

    def _product_to_response(
        self,
        product: Product,
        variants: list[Any] | None = None,
    ) -> ProductResponse:
        """Convert a Product document to a ProductResponse schema."""
        inv = product.inventory or {}
        stock_qty = inv.get("stock_quantity", 0)
        reserved = inv.get("reserved", 0)
        available = max(stock_qty - reserved, 0)
        threshold = inv.get("threshold", 10)

        inventory_resp = InventoryResponse(
            stock_quantity=stock_qty,
            reserved=reserved,
            available=available,
            threshold=threshold,
            warehouse_id=inv.get("warehouse_id", "default"),
            track_inventory=inv.get("track_inventory", True),
            is_low_stock=available <= threshold,
            is_out_of_stock=available == 0,
        )

        variant_responses = []
        if variants:
            for v in variants:
                variant_responses.append(VariantResponse(
                    id=str(v.id),
                    sku=v.sku,
                    attributes=v.attributes,
                    price=v.price,
                    compare_price=v.compare_price,
                    stock=v.stock,
                    images=v.images,
                    is_available=v.is_available,
                ))

        return ProductResponse(
            id=str(product.id),
            sku=product.sku,
            title=product.title,
            description=product.description,
            price=product.price,
            compare_price=product.compare_price,
            currency=product.currency,
            images=product.images,
            category_id=product.category_id,
            brand=product.brand,
            attributes=product.attributes,
            variants=variant_responses,
            inventory=inventory_resp,
            status=product.status.value if hasattr(product.status, "value") else str(product.status),
            tags=product.tags,
            rating=product.rating,
            review_count=product.review_count,
            seller_id=product.seller_id,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

    async def create_product(self, data: CreateProductRequest) -> ProductResponse:
        """Create a new product.

        Args:
            data: Product creation data.

        Returns:
            Created product response.

        Raises:
            ConflictError: If SKU already exists.
        """
        existing = await self._product_repo.get_by_sku(data.sku)
        if existing:
            raise ConflictError(
                message=f"Product with SKU '{data.sku}' already exists",
                detail={"sku": data.sku},
            )

        inventory = {
            "stock_quantity": data.inventory.stock_quantity if data.inventory else 0,
            "reserved": 0,
            "threshold": data.inventory.threshold if data.inventory else 10,
            "warehouse_id": data.inventory.warehouse_id if data.inventory else "default",
            "track_inventory": data.inventory.track_inventory if data.inventory else True,
        }

        product = await self._product_repo.create(
            sku=data.sku,
            title=data.title,
            description=data.description,
            price=data.price,
            compare_price=data.compare_price,
            currency=data.currency,
            images=data.images,
            category_id=data.category_id,
            brand=data.brand,
            attributes=data.attributes,
            tags=data.tags,
            status=data.status.value,
            inventory=inventory,
        )

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.PRODUCT_EVENTS,
                event_type=ProductEvents.CREATED,
                payload={
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "title": product.title,
                    "price": product.price,
                },
                key=str(product.id),
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        await invalidate_cache("products")

        return self._product_to_response(product)

    async def update_product(
        self, product_id: str, data: UpdateProductRequest
    ) -> ProductResponse:
        """Update a product with optimistic locking.

        Args:
            product_id: The product ID.
            data: Partial update data.

        Returns:
            Updated product response.

        Raises:
            NotFoundError: If product not found.
        """
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(detail={"resource": "Product", "id": product_id})

        updates = data.model_dump(exclude_none=True)
        if "status" in updates:
            updates["status"] = updates["status"].value if hasattr(updates["status"], "value") else updates["status"]

        if updates:
            product = await self._product_repo.update(product_id, **updates)

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.PRODUCT_EVENTS,
                event_type=ProductEvents.UPDATED,
                payload={
                    "product_id": product_id,
                    "updated_fields": list(updates.keys()),
                },
                key=product_id,
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        await invalidate_cache("products")

        variants = await self._variant_repo.get_by_product(product_id)
        return self._product_to_response(product, variants)

    async def get_product(self, product_id: str) -> ProductResponse:
        """Get a product by ID with variants.

        Args:
            product_id: The product ID.

        Returns:
            Full product response.

        Raises:
            NotFoundError: If product not found.
        """
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(detail={"resource": "Product", "id": product_id})

        variants = await self._variant_repo.get_by_product(product_id)
        return self._product_to_response(product, variants)

    async def search_products(
        self, params: ProductSearchParams
    ) -> PaginatedProductResponse:
        """Search products with filters and pagination.

        Args:
            params: Search parameters.

        Returns:
            Paginated product response.
        """
        products, total = await self._product_repo.search(
            query=params.query,
            category_id=params.category_id,
            brand=params.brand,
            min_price=params.min_price,
            max_price=params.max_price,
            status=params.status.value if params.status else None,
            tags=params.tags,
            in_stock=params.in_stock,
            page=params.page,
            page_size=params.page_size,
            sort_by=params.sort_by,
            sort_order=params.sort_order,
        )

        total_pages = (total + params.page_size - 1) // params.page_size if total > 0 else 0

        return PaginatedProductResponse(
            items=[self._product_to_response(p) for p in products],
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_previous=params.page > 1,
        )

    async def update_inventory(
        self,
        product_id: str,
        data: UpdateInventoryRequest,
    ) -> ProductResponse:
        """Update product inventory with atomic operations.

        Args:
            product_id: The product ID.
            data: Inventory update with delta and reason.

        Returns:
            Updated product response.

        Raises:
            NotFoundError: If product not found.
            ValidationError: If update would result in negative stock.
        """
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(detail={"resource": "Product", "id": product_id})

        current_stock = product.inventory.get("stock_quantity", 0)
        if current_stock + data.delta < 0:
            raise ValidationError(
                message="Insufficient stock",
                detail={
                    "current_stock": current_stock,
                    "requested_delta": data.delta,
                },
            )

        updated = await self._product_repo.update_inventory_atomic(
            product_id, data.delta
        )

        if updated is None:
            raise NotFoundError(detail={"resource": "Product", "id": product_id})

        # Check stock levels and emit events
        new_stock = current_stock + data.delta
        threshold = product.inventory.get("threshold", 10)

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.PRODUCT_EVENTS,
                event_type=ProductEvents.INVENTORY_UPDATED,
                payload={
                    "product_id": product_id,
                    "delta": data.delta,
                    "reason": data.reason,
                    "new_stock": new_stock,
                },
                key=product_id,
            )

            if new_stock <= threshold and new_stock > 0:
                await kafka.publish(
                    topic=KafkaTopics.PRODUCT_EVENTS,
                    event_type=ProductEvents.INVENTORY_LOW_STOCK,
                    payload={
                        "product_id": product_id,
                        "current_stock": new_stock,
                        "threshold": threshold,
                    },
                    key=product_id,
                )

            if new_stock == 0:
                await kafka.publish(
                    topic=KafkaTopics.PRODUCT_EVENTS,
                    event_type=ProductEvents.INVENTORY_OUT_OF_STOCK,
                    payload={"product_id": product_id},
                    key=product_id,
                )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        await invalidate_cache("products")

        return await self.get_product(product_id)

    async def delete_product(self, product_id: str) -> bool:
        """Soft-delete a product.

        Args:
            product_id: The product ID.

        Returns:
            True if deleted.

        Raises:
            NotFoundError: If product not found.
        """
        success = await self._product_repo.soft_delete(product_id)
        if not success:
            raise NotFoundError(detail={"resource": "Product", "id": product_id})

        try:
            kafka = await self._get_kafka()
            await kafka.publish(
                topic=KafkaTopics.PRODUCT_EVENTS,
                event_type=ProductEvents.DELETED,
                payload={"product_id": product_id},
                key=product_id,
            )
        except Exception as e:
            logger.error("kafka_publish_failed", error=str(e))

        await invalidate_cache("products")
        return True

    @cache_aside(ttl=600, namespace="categories")
    async def get_category_tree(self) -> dict[str, Any]:
        """Get the full category tree (cached 10 min).

        Returns:
            Serialized category tree structure.
        """
        all_cats = await self._category_repo.get_tree()

        # Build tree structure
        cat_map: dict[str, dict[str, Any]] = {}
        roots: list[dict[str, Any]] = []

        for cat in all_cats:
            cat_dict = {
                "id": str(cat.id),
                "name": cat.name,
                "slug": cat.slug,
                "parent_id": cat.parent_id,
                "description": cat.description,
                "image_url": cat.image_url,
                "sort_order": cat.sort_order,
                "product_count": cat.product_count,
                "children": [],
            }
            cat_map[str(cat.id)] = cat_dict

        for cat_dict in cat_map.values():
            parent_id = cat_dict["parent_id"]
            if parent_id and parent_id in cat_map:
                cat_map[parent_id]["children"].append(cat_dict)
            else:
                roots.append(cat_dict)

        return {"categories": roots}

    async def create_category(self, data: CreateCategoryRequest) -> CategoryResponse:
        """Create a new product category.

        Args:
            data: Category creation data.

        Returns:
            Created category response.
        """
        existing = await self._category_repo.get_by_slug(data.slug)
        if existing:
            raise ConflictError(
                message=f"Category with slug '{data.slug}' already exists",
            )

        # Build materialized path
        path = data.slug
        if data.parent_id:
            parent = await self._category_repo.get_by_id(data.parent_id)
            if parent:
                path = f"{parent.path}/{data.slug}" if parent.path else data.slug

        category = await self._category_repo.create(
            name=data.name,
            slug=data.slug,
            parent_id=data.parent_id,
            description=data.description,
            image_url=data.image_url,
            sort_order=data.sort_order,
            path=path,
        )

        await invalidate_cache("categories")

        return CategoryResponse(
            id=str(category.id),
            name=category.name,
            slug=category.slug,
            parent_id=category.parent_id,
            description=category.description,
            image_url=category.image_url,
            sort_order=category.sort_order,
            product_count=0,
        )
