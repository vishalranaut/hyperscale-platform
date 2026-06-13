"""HyperScale Platform — Product Service Django Settings."""

from pathlib import Path
from shared.config import get_settings

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "services.product_service.urls"
ASGI_APPLICATION = "services.product_service.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "shared.middleware.tracing.RequestTracingMiddleware",
    "shared.middleware.auth.AuthMiddleware",
    "shared.middleware.rate_limit.RateLimitMiddleware",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PERMISSION_CLASSES": ["shared.auth.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "shared.exceptions.hyperscale_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

CORS_ALLOWED_ORIGINS = settings.cors_origins_list
CORS_ALLOW_CREDENTIALS = True
LOGGING_CONFIG = None
SERVICE_NAME = "product-service"
SERVICE_PORT = settings.PRODUCT_SERVICE_PORT
GRPC_PORT = settings.PRODUCT_SERVICE_GRPC_PORT
