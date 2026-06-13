"""HyperScale Platform — User Service ASGI Configuration.

ASGI entry point for the user microservice. Initializes MongoDB
(Beanie ODM) and structlog on startup.
"""

from __future__ import annotations

import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.user_service.settings")
django.setup()

from shared.db.mongodb import init_mongodb
from shared.logging import setup_logging
from services.user_service.domain.models import (
    OAuthConnection,
    Permission,
    Role,
    User,
    UserProfile,
)

_initialized = False


async def lifespan_startup() -> None:
    """Run startup tasks: logging, database, indexes."""
    global _initialized
    if _initialized:
        return

    setup_logging(service_name="user-service")

    await init_mongodb(
        document_models=[User, Role, Permission, UserProfile, OAuthConnection],
    )

    _initialized = True


_django_app = get_asgi_application()


async def application(scope: dict, receive: object, send: object) -> None:
    """ASGI application entry point with startup lifecycle.

    Args:
        scope: ASGI connection scope.
        receive: ASGI receive callable.
        send: ASGI send callable.
    """
    if scope["type"] == "lifespan":
        while True:
            message = await receive()  # type: ignore[operator]
            if message["type"] == "lifespan.startup":
                await lifespan_startup()
                await send({"type": "lifespan.startup.complete"})  # type: ignore[operator]
            elif message["type"] == "lifespan.shutdown":
                from shared.cache.redis_client import close_redis_client
                from shared.db.mongodb import close_motor_client

                await close_redis_client()
                await close_motor_client()
                await send({"type": "lifespan.shutdown.complete"})  # type: ignore[operator]
                return
    else:
        await lifespan_startup()
        await _django_app(scope, receive, send)  # type: ignore[arg-type]
