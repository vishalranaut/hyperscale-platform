"""HyperScale Platform — Centralized Configuration.

Pydantic v2 BaseSettings for all service configuration. Supports loading
from .env files, environment variables, and Docker secrets injection.
Follows the 12-Factor App methodology.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment enumeration."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class HyperScaleSettings(BaseSettings):
    """Base settings shared across all HyperScale microservices.

    Configuration is loaded in priority order:
        1. Environment variables
        2. Docker secrets (mounted at /run/secrets/)
        3. .env file
        4. Default values

    Example:
        >>> settings = get_settings()
        >>> print(settings.MONGODB_URL)
        'mongodb://localhost:27017'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        secrets_dir="/run/secrets" if os.path.isdir("/run/secrets") else None,
    )

    # ── General ──────────────────────────────────────────────────────────
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "hyperscale"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-to-a-real-secret-key-in-production"

    # ── MongoDB ──────────────────────────────────────────────────────────
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "hyperscale"
    MONGODB_MIN_POOL_SIZE: int = Field(default=5, ge=1)
    MONGODB_MAX_POOL_SIZE: int = Field(default=50, ge=5)

    # ── Redis ────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_DB: int = Field(default=1, ge=0, le=15)
    REDIS_SESSION_DB: int = Field(default=2, ge=0, le=15)
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=5)

    # ── Kafka ────────────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP_PREFIX: str = "hyperscale"
    KAFKA_AUTO_OFFSET_RESET: str = "earliest"
    KAFKA_ENABLE_IDEMPOTENCE: bool = True

    # ── JWT / Auth ───────────────────────────────────────────────────────
    JWT_SECRET: str = "change-me-to-a-256-bit-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)

    # ── Firebase ─────────────────────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = "./firebase-service-account.json"
    FIREBASE_PROJECT_ID: str = "hyperscale-platform"

    # ── gRPC Service Endpoints ───────────────────────────────────────────
    USER_SERVICE_GRPC_HOST: str = "localhost"
    USER_SERVICE_GRPC_PORT: int = 50051
    PRODUCT_SERVICE_GRPC_HOST: str = "localhost"
    PRODUCT_SERVICE_GRPC_PORT: int = 50052
    ORDER_SERVICE_GRPC_HOST: str = "localhost"
    ORDER_SERVICE_GRPC_PORT: int = 50053
    AI_SERVICE_GRPC_HOST: str = "localhost"
    AI_SERVICE_GRPC_PORT: int = 50054

    # ── HTTP Service Ports ───────────────────────────────────────────────
    USER_SERVICE_PORT: int = 8001
    PRODUCT_SERVICE_PORT: int = 8002
    ORDER_SERVICE_PORT: int = 8003
    NOTIFICATION_SERVICE_PORT: int = 8004
    CHAT_SERVICE_PORT: int = 8005
    ANALYTICS_SERVICE_PORT: int = 8006
    AI_SERVICE_PORT: int = 8007
    GATEWAY_PORT: int = 8000

    # ── OpenTelemetry ────────────────────────────────────────────────────
    OTEL_EXPORTER_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "hyperscale"
    OTEL_TRACES_SAMPLER: str = "parentbased_traceidratio"
    OTEL_TRACES_SAMPLER_ARG: float = Field(default=1.0, ge=0.0, le=1.0)
    LOG_LEVEL: LogLevel = LogLevel.INFO

    # ── Email (SMTP) ────────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM_ADDRESS: str = "noreply@hyperscale.dev"
    EMAIL_FROM_NAME: str = "HyperScale Platform"

    # ── Twilio SMS ───────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # ── Stripe (Payments) ───────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT_DEFAULT_REQUESTS: int = Field(default=100, ge=1)
    RATE_LIMIT_DEFAULT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    RATE_LIMIT_AUTH_REQUESTS: int = Field(default=10, ge=1)
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = Field(default=300, ge=1)

    # ── CORS ─────────────────────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    @field_validator("KAFKA_BOOTSTRAP_SERVERS")
    @classmethod
    def validate_kafka_servers(cls, v: str) -> str:
        """Validate that Kafka bootstrap servers are non-empty."""
        if not v or not v.strip():
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS must not be empty")
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "HyperScaleSettings":
        """Enforce strict validation for production environments."""
        if self.ENVIRONMENT == Environment.PRODUCTION:
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
            if self.JWT_SECRET == "change-me-to-a-256-bit-secret-key":
                raise ValueError("JWT_SECRET must be changed in production")
            if self.SECRET_KEY == "change-me-to-a-real-secret-key-in-production":
                raise ValueError("SECRET_KEY must be changed in production")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def kafka_servers_list(self) -> list[str]:
        """Parse comma-separated Kafka servers into a list."""
        return [s.strip() for s in self.KAFKA_BOOTSTRAP_SERVERS.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.ENVIRONMENT == Environment.TESTING

    @property
    def mongodb_connection_kwargs(self) -> dict[str, Any]:
        """Build Motor client connection keyword arguments."""
        return {
            "minPoolSize": self.MONGODB_MIN_POOL_SIZE,
            "maxPoolSize": self.MONGODB_MAX_POOL_SIZE,
        }

    def get_grpc_address(self, service: str) -> str:
        """Get the gRPC address for a named service.

        Args:
            service: Service name (e.g., 'user', 'product', 'order', 'ai').

        Returns:
            Formatted gRPC address string (host:port).

        Raises:
            ValueError: If service name is not recognized.
        """
        service_map = {
            "user": (self.USER_SERVICE_GRPC_HOST, self.USER_SERVICE_GRPC_PORT),
            "product": (self.PRODUCT_SERVICE_GRPC_HOST, self.PRODUCT_SERVICE_GRPC_PORT),
            "order": (self.ORDER_SERVICE_GRPC_HOST, self.ORDER_SERVICE_GRPC_PORT),
            "ai": (self.AI_SERVICE_GRPC_HOST, self.AI_SERVICE_GRPC_PORT),
        }
        if service not in service_map:
            raise ValueError(f"Unknown gRPC service: {service}. Valid: {list(service_map.keys())}")
        host, port = service_map[service]
        return f"{host}:{port}"


class ServiceSettings(HyperScaleSettings):
    """Extended settings for individual microservices.

    Each service overrides SERVICE_NAME and may add service-specific
    configuration fields.

    Example:
        >>> class UserServiceSettings(ServiceSettings):
        ...     SERVICE_NAME: str = "user-service"
        ...     VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    """

    pass


@lru_cache(maxsize=1)
def get_settings() -> HyperScaleSettings:
    """Get cached singleton settings instance.

    Returns:
        The global HyperScaleSettings instance, loaded once and cached.

    Example:
        >>> settings = get_settings()
        >>> settings.MONGODB_URL
        'mongodb://localhost:27017'
    """
    return HyperScaleSettings()


def get_service_settings(settings_class: type[ServiceSettings] | None = None) -> ServiceSettings:
    """Get settings for a specific service class.

    Args:
        settings_class: Optional service-specific settings class.
            Defaults to base ServiceSettings if not provided.

    Returns:
        A ServiceSettings instance with service-specific config loaded.
    """
    cls = settings_class or ServiceSettings
    return cls()
