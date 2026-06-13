"""HyperScale Platform — User Service WSGI Configuration."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.user_service.settings")

application = get_wsgi_application()
