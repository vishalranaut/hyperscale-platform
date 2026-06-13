"""HyperScale Platform — GraphQL Gateway Settings."""

from pathlib import Path
from shared.config import get_settings

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "services.graphql_gateway.urls"
ASGI_APPLICATION = "services.graphql_gateway.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "corsheaders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "shared.middleware.tracing.RequestTracingMiddleware",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

CORS_ALLOWED_ORIGINS = settings.cors_origins_list
LOGGING_CONFIG = None
SERVICE_NAME = "graphql-gateway"
