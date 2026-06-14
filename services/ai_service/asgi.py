"""HyperScale Platform — AI Service ASGI Config."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.ai_service.settings")

from contextlib import asynccontextmanager
from shared.logging import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app):
    logger.info("ai_service_starting")
    from shared.db.mongodb import init_beanie
    from services.ai_service.domain.models import RecommendationCache, UserPreference
    
    await init_beanie(document_models=[RecommendationCache, UserPreference])
    yield
    logger.info("ai_service_shutting_down")

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
