"""HyperScale Platform — Product Service ASGI Configuration."""

import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.product_service.settings")
django.setup()

from shared.db.mongodb import init_mongodb
from shared.logging import setup_logging
from services.product_service.domain.models import Category, InventoryInfo, Product, SEOData, Variant

_initialized = False


async def lifespan_startup() -> None:
    """Run startup tasks."""
    global _initialized
    if _initialized:
        return
    setup_logging(service_name="product-service")
    await init_mongodb(document_models=[Product, Category, Variant, InventoryInfo, SEOData])
    _initialized = True


_django_app = get_asgi_application()


async def application(scope, receive, send):
    """ASGI application with lifecycle management."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await lifespan_startup()
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                from shared.cache.redis_client import close_redis_client
                from shared.db.mongodb import close_motor_client
                await close_redis_client()
                await close_motor_client()
                await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await lifespan_startup()
        await _django_app(scope, receive, send)
