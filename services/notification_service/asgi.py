"""HyperScale Platform — Notification Service ASGI Config."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.notification_service.settings")

from contextlib import asynccontextmanager
from shared.logging import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app):
    """Lifespan context for Notification Service.
    
    Handles startup tasks such as connecting to databases and
    spinning up Kafka consumer background tasks.
    """
    logger.info("notification_service_starting")
    from shared.db.mongodb import init_beanie
    from services.notification_service.domain.models import Notification, PushToken
    
    # Initialize MongoDB/Beanie
    await init_beanie(document_models=[Notification, PushToken])
    
    # Start Kafka Consumers
    from services.notification_service.kafka_handlers import start_consumers
    await start_consumers()
    
    yield
    
    logger.info("notification_service_shutting_down")
    # Shutdown logic (e.g., stopping consumers) would go here

# Wrap the Django ASGI app in the lifespan manager.
# Note: Django 5.0+ supports ASGI lifespans natively, but using Starlette/FastAPI's
# approach or a custom middleware is sometimes required depending on the setup.
# For simplicity in this ASGI file, we'll expose a wrapped application.

from asgiref.wsgi import WsgiToAsgi
# (Assuming a standard Django setup, though we should really use Starlette or FastAPI 
# for the root ASGI app if we want proper lifespan support, or Django's modern ASGI).
# We'll use a basic ASGI wrapper.
django_app = get_asgi_application()

async def application(scope, receive, send):
    if scope["type"] == "lifespan":
        async with lifespan(django_app):
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
    else:
        await django_app(scope, receive, send)
