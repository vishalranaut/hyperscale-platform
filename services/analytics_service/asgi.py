"""HyperScale Platform — Analytics Service ASGI Config."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.analytics_service.settings")

application = get_asgi_application()
