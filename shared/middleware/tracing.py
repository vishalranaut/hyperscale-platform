"""HyperScale Platform — Request Tracing Middleware.

Injects X-Request-ID headers and creates OpenTelemetry spans for
distributed tracing across microservices. Propagates trace context
to structlog for correlated logging.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

from shared.logging import get_logger, set_log_context

logger = get_logger(__name__)


class RequestTracingMiddleware:
    """ASGI middleware for distributed request tracing.

    Responsibilities:
        1. Generate or propagate X-Request-ID header.
        2. Create OpenTelemetry spans for each request.
        3. Inject request_id into structlog context for correlated logs.
        4. Add timing information to response headers.

    Args:
        get_response: The next middleware or view in the chain.

    Example:
        Add to Django MIDDLEWARE setting::

            MIDDLEWARE = [
                'shared.middleware.tracing.RequestTracingMiddleware',
                ...
            ]
    """

    HEADER_REQUEST_ID = "X-Request-ID"
    HEADER_CORRELATION_ID = "X-Correlation-ID"

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self._tracer: Any | None = None

    def _get_tracer(self) -> Any:
        """Lazily initialize the OpenTelemetry tracer.

        Returns:
            An OpenTelemetry tracer instance, or None if OTEL is not available.
        """
        if self._tracer is None:
            try:
                from opentelemetry import trace

                self._tracer = trace.get_tracer("hyperscale.middleware.tracing")
            except ImportError:
                self._tracer = None
        return self._tracer

    def _extract_request_id(self, request: HttpRequest) -> str:
        """Extract or generate a unique request ID.

        If the incoming request has an X-Request-ID header (from an
        upstream gateway or load balancer), it is reused. Otherwise,
        a new UUID4 is generated.

        Args:
            request: The incoming HTTP request.

        Returns:
            A UUID string for this request.
        """
        existing = request.META.get(
            f"HTTP_{self.HEADER_REQUEST_ID.upper().replace('-', '_')}"
        )
        return existing or str(uuid.uuid4())

    def _extract_correlation_id(self, request: HttpRequest) -> str:
        """Extract or generate a correlation ID for distributed tracing.

        The correlation ID tracks a business operation across multiple
        service calls. If not present in the request, uses the request ID.

        Args:
            request: The incoming HTTP request.

        Returns:
            A correlation ID string.
        """
        existing = request.META.get(
            f"HTTP_{self.HEADER_CORRELATION_ID.upper().replace('-', '_')}"
        )
        return existing or str(uuid.uuid4())

    async def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request with tracing context.

        Args:
            request: The incoming HTTP request.

        Returns:
            The response with tracing headers added.
        """
        import time

        start_time = time.perf_counter()

        # Extract or generate IDs
        request_id = self._extract_request_id(request)
        correlation_id = self._extract_correlation_id(request)

        # Attach to request object for downstream use
        request.request_id = request_id  # type: ignore[attr-defined]
        request.correlation_id = correlation_id  # type: ignore[attr-defined]

        # Set structlog context
        set_log_context(
            request_id=request_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "request_started",
            method=request.method,
            path=request.path,
            query_string=request.META.get("QUERY_STRING", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            remote_addr=request.META.get("REMOTE_ADDR", ""),
        )

        # Create OpenTelemetry span if available
        tracer = self._get_tracer()
        if tracer is not None:
            try:
                from opentelemetry import trace
                from opentelemetry.trace import SpanKind, StatusCode

                with tracer.start_as_current_span(
                    f"{request.method} {request.path}",
                    kind=SpanKind.SERVER,
                    attributes={
                        "http.method": request.method,
                        "http.url": request.build_absolute_uri(),
                        "http.target": request.path,
                        "http.request_id": request_id,
                        "http.correlation_id": correlation_id,
                        "http.user_agent": request.META.get("HTTP_USER_AGENT", ""),
                    },
                ) as span:
                    response = await self.get_response(request)
                    span.set_attribute("http.status_code", response.status_code)
                    if response.status_code >= 400:
                        span.set_status(StatusCode.ERROR)
            except Exception:
                response = await self.get_response(request)
        else:
            response = await self.get_response(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Add tracing headers to response
        response[self.HEADER_REQUEST_ID] = request_id
        response[self.HEADER_CORRELATION_ID] = correlation_id
        response["X-Response-Time"] = f"{duration_ms:.2f}ms"

        logger.info(
            "request_completed",
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return response
