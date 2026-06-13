"""HyperScale Platform — Structured Logging.

Provides structured JSON logging via structlog with AsyncContextVar-based
context propagation for request_id, user_id, and service_name injection
into every log line. Integrates with Django's logging framework.

Example:
    >>> from shared.logging import setup_logging, get_logger
    >>> setup_logging(service_name="user-service", log_level="DEBUG")
    >>> logger = get_logger(__name__)
    >>> logger.info("user_registered", user_id="abc123", email="a@b.com")
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from shared.config import Environment, get_settings

# ── Context Variables ────────────────────────────────────────────────────────
# These are propagated across async contexts automatically.

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)
service_name_ctx: ContextVar[str | None] = ContextVar("service_name", default=None)
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_log_context(
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    service_name: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Set logging context variables for the current async task.

    Args:
        request_id: Unique identifier for the current HTTP request.
        user_id: Authenticated user's identifier.
        service_name: Name of the current microservice.
        correlation_id: Distributed tracing correlation ID.
    """
    if request_id is not None:
        request_id_ctx.set(request_id)
    if user_id is not None:
        user_id_ctx.set(user_id)
    if service_name is not None:
        service_name_ctx.set(service_name)
    if correlation_id is not None:
        correlation_id_ctx.set(correlation_id)


def clear_log_context() -> None:
    """Reset all logging context variables to their defaults."""
    request_id_ctx.set(None)
    user_id_ctx.set(None)
    service_name_ctx.set(None)
    correlation_id_ctx.set(None)


def _inject_context_vars(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor that injects context variables into log events.

    Args:
        logger: The wrapped logger object.
        method_name: The name of the log method called.
        event_dict: The event dictionary being processed.

    Returns:
        The event_dict enriched with context variables.
    """
    ctx_values = {
        "request_id": request_id_ctx.get(None),
        "user_id": user_id_ctx.get(None),
        "service_name": service_name_ctx.get(None),
        "correlation_id": correlation_id_ctx.get(None),
    }
    for key, value in ctx_values.items():
        if value is not None and key not in event_dict:
            event_dict[key] = value
    return event_dict


def _add_log_level_number(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add numeric log level for machine parsing.

    Args:
        logger: The wrapped logger object.
        method_name: The name of the log method called.
        event_dict: The event dictionary being processed.

    Returns:
        The event_dict with level_number added.
    """
    level_map = {
        "debug": 10,
        "info": 20,
        "warning": 30,
        "error": 40,
        "critical": 50,
    }
    event_dict["level_number"] = level_map.get(method_name, 0)
    return event_dict


def setup_logging(
    service_name: str | None = None,
    log_level: str | None = None,
    json_format: bool | None = None,
) -> None:
    """Configure structlog and stdlib logging for the application.

    Sets up structured logging with JSON output for production and
    colored console output for development. Integrates with Django's
    logging framework.

    Args:
        service_name: Name of the microservice (injected into all logs).
            Defaults to settings.SERVICE_NAME.
        log_level: Logging level string. Defaults to settings.LOG_LEVEL.
        json_format: Force JSON format. None auto-detects from environment.
            Production/staging → JSON, development/testing → console.

    Example:
        >>> setup_logging(service_name="user-service", log_level="DEBUG")
    """
    settings = get_settings()
    service_name = service_name or settings.SERVICE_NAME
    log_level = log_level or settings.LOG_LEVEL.value

    # Set global service context
    service_name_ctx.set(service_name)

    # Determine output format
    if json_format is None:
        json_format = settings.ENVIRONMENT in (Environment.PRODUCTION, Environment.STAGING)

    # Shared processors for both structlog and stdlib
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_context_vars,
        structlog.stdlib.add_log_level,
        _add_log_level_number,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        # Production: JSON lines for log aggregation
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Development: colorful console output
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            pad_event=40,
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        renderer,
                    ],
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                    "stream": sys.stdout,
                },
            },
            "root": {
                "handlers": ["console"],
                "level": log_level,
            },
            "loggers": {
                "django": {"level": "INFO", "propagate": True},
                "django.db.backends": {"level": "WARNING", "propagate": True},
                "django.request": {"level": "INFO", "propagate": True},
                "uvicorn": {"level": "INFO", "propagate": True},
                "aiokafka": {"level": "WARNING", "propagate": True},
                "grpc": {"level": "WARNING", "propagate": True},
            },
        }
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog bound logger instance.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
            If None, uses the root logger.

    Returns:
        A configured structlog BoundLogger.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("operation_completed", duration_ms=42)
    """
    return structlog.get_logger(name)


# Import logging.config at module level after function definitions
import logging.config  # noqa: E402
