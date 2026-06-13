"""HyperScale Platform — GraphQL Gateway ASGI Config."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.graphql_gateway.settings")

application = get_asgi_application()
