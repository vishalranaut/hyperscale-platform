"""HyperScale Platform — User Service Django Settings.

Django 5.x settings configured for the user microservice with
MongoDB (via djongo/beanie), Redis, Kafka, and ASGI.
"""

from __future__ import annotations

import os
from pathlib import Path

from shared.config import get_settings

settings = get_settings()

# ── Core ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "services.user_service.urls"
WSGI_APPLICATION = "services.user_service.wsgi.application"
ASGI_APPLICATION = "services.user_service.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Installed Apps ───────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
]

# ── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "shared.middleware.tracing.RequestTracingMiddleware",
    "shared.middleware.auth.AuthMiddleware",
    "shared.middleware.rate_limit.RateLimitMiddleware",
]

# ── Database (MongoDB via Motor — managed outside Django ORM) ────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ── REST Framework ───────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "shared.auth.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "shared.exceptions.hyperscale_exception_handler",
    "DEFAULT_PAGINATION_CLASS": None,
    "UNAUTHENTICATED_USER": None,
}

# ── CORS ─────────────────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = settings.cors_origins_list
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-api-key",
    "x-request-id",
    "x-correlation-id",
]

# ── Logging ──────────────────────────────────────────────────────────────────

LOGGING_CONFIG = None  # Managed by structlog in shared.logging

# ── Service-specific ─────────────────────────────────────────────────────────

SERVICE_NAME = "user-service"
SERVICE_PORT = settings.USER_SERVICE_PORT
GRPC_PORT = settings.USER_SERVICE_GRPC_PORT
