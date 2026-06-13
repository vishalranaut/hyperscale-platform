"""HyperScale Platform — Exception Hierarchy.

Custom exception classes with structured error responses for
Django REST Framework and GraphQL. Every exception carries an
error code, HTTP status, human-readable message, and optional detail.

Example:
    >>> raise NotFoundError(detail={"resource": "User", "id": "abc123"})
    # Returns HTTP 404 with:
    # {"error": {"code": "NOT_FOUND", "message": "Resource not found", ...}}
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class HyperScaleException(Exception):
    """Base exception for all HyperScale platform errors.

    All service-layer exceptions should subclass this. Provides structured
    error information including an error code, HTTP status, message, and
    optional detail payload.

    Attributes:
        code: Machine-readable error code (e.g., 'NOT_FOUND').
        message: Human-readable error message.
        detail: Optional additional context about the error.
        http_status: HTTP status code to return to the client.

    Args:
        message: Human-readable error message. Defaults to class default.
        code: Machine-readable error code. Defaults to class default.
        detail: Additional error context as a dictionary.
        http_status: HTTP status code. Defaults to class default.

    Example:
        >>> try:
        ...     raise HyperScaleException(
        ...         message="Something went wrong",
        ...         code="INTERNAL_ERROR",
        ...         detail={"context": "processing payment"},
        ...     )
        ... except HyperScaleException as e:
        ...     print(e.to_dict())
    """

    default_code: str = "INTERNAL_ERROR"
    default_message: str = "An internal error occurred"
    default_http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        detail: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.message = message or self.default_message
        self.detail = detail or {}
        self.http_status = http_status or self.default_http_status
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the exception to a structured error dictionary.

        Returns:
            A dictionary suitable for JSON serialization in API responses.
        """
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.detail:
            error["detail"] = self.detail
        return {"error": error}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.code!r}, message={self.message!r}, "
            f"http_status={self.http_status})"
        )


class NotFoundError(HyperScaleException):
    """Raised when a requested resource does not exist.

    HTTP 404 — The server cannot find the requested resource.

    Example:
        >>> raise NotFoundError(detail={"resource": "User", "id": "abc123"})
    """

    default_code = "NOT_FOUND"
    default_message = "Resource not found"
    default_http_status = HTTPStatus.NOT_FOUND


class ValidationError(HyperScaleException):
    """Raised when input validation fails.

    HTTP 422 — The request was well-formed but contains semantic errors.

    Example:
        >>> raise ValidationError(
        ...     detail={"field": "email", "error": "Invalid email format"}
        ... )
    """

    default_code = "VALIDATION_ERROR"
    default_message = "Validation failed"
    default_http_status = HTTPStatus.UNPROCESSABLE_ENTITY


class AuthenticationError(HyperScaleException):
    """Raised when authentication fails or credentials are invalid.

    HTTP 401 — The request requires valid authentication credentials.

    Example:
        >>> raise AuthenticationError(message="Invalid or expired token")
    """

    default_code = "AUTHENTICATION_ERROR"
    default_message = "Authentication failed"
    default_http_status = HTTPStatus.UNAUTHORIZED


class AuthorizationError(HyperScaleException):
    """Raised when the user lacks permission for the requested action.

    HTTP 403 — The server understood the request but refuses to authorize it.

    Example:
        >>> raise AuthorizationError(
        ...     detail={"required_role": "admin", "current_role": "user"}
        ... )
    """

    default_code = "AUTHORIZATION_ERROR"
    default_message = "Insufficient permissions"
    default_http_status = HTTPStatus.FORBIDDEN


class ConflictError(HyperScaleException):
    """Raised when a request conflicts with the current resource state.

    HTTP 409 — The request conflicts with the current state of the resource.

    Example:
        >>> raise ConflictError(
        ...     message="Email already registered",
        ...     detail={"email": "user@example.com"}
        ... )
    """

    default_code = "CONFLICT"
    default_message = "Resource conflict"
    default_http_status = HTTPStatus.CONFLICT


class RateLimitError(HyperScaleException):
    """Raised when the client has exceeded the rate limit.

    HTTP 429 — Too many requests in a given amount of time.

    Example:
        >>> raise RateLimitError(
        ...     detail={"retry_after_seconds": 60, "limit": 100}
        ... )
    """

    default_code = "RATE_LIMITED"
    default_message = "Rate limit exceeded"
    default_http_status = HTTPStatus.TOO_MANY_REQUESTS


class ServiceUnavailableError(HyperScaleException):
    """Raised when an upstream service or dependency is unavailable.

    HTTP 503 — The server is currently unable to handle the request.

    Example:
        >>> raise ServiceUnavailableError(
        ...     detail={"service": "product-service", "reason": "connection timeout"}
        ... )
    """

    default_code = "SERVICE_UNAVAILABLE"
    default_message = "Service temporarily unavailable"
    default_http_status = HTTPStatus.SERVICE_UNAVAILABLE


class PaymentError(HyperScaleException):
    """Raised when a payment processing operation fails.

    HTTP 402 — Payment is required or payment processing failed.

    Example:
        >>> raise PaymentError(
        ...     detail={"provider": "stripe", "decline_code": "insufficient_funds"}
        ... )
    """

    default_code = "PAYMENT_ERROR"
    default_message = "Payment processing failed"
    default_http_status = HTTPStatus.PAYMENT_REQUIRED


class OptimisticLockError(ConflictError):
    """Raised when an optimistic locking conflict is detected.

    This occurs when a document has been modified since it was last read,
    preventing a stale write.

    Example:
        >>> raise OptimisticLockError(
        ...     detail={"resource": "Product", "id": "xyz", "expected_version": 3}
        ... )
    """

    default_code = "OPTIMISTIC_LOCK_CONFLICT"
    default_message = "Resource was modified by another request"


# ── Django REST Framework Exception Handler ──────────────────────────────────


def hyperscale_exception_handler(exc: Exception, context: Any) -> Response | None:
    """Global exception handler for Django REST Framework.

    Converts HyperScaleException instances into structured JSON error
    responses. Falls back to DRF's default handler for other exceptions.

    Args:
        exc: The exception that was raised.
        context: DRF context dictionary with view, request, etc.

    Returns:
        A DRF Response with structured error body, or None for unhandled exceptions.
    """
    # Handle our custom exceptions
    if isinstance(exc, HyperScaleException):
        return Response(
            exc.to_dict(),
            status=exc.http_status,
            content_type="application/json",
        )

    # Handle DRF's built-in exceptions
    if isinstance(exc, APIException):
        return Response(
            {
                "error": {
                    "code": exc.default_code if hasattr(exc, "default_code") else "API_ERROR",
                    "message": str(exc.detail) if hasattr(exc, "detail") else str(exc),
                }
            },
            status=exc.status_code,
            content_type="application/json",
        )

    # Fallback to DRF default handler
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    # Unhandled exceptions — let Django handle them (500 in debug, etc.)
    return None


def format_graphql_error(error: Exception) -> dict[str, Any]:
    """Format exceptions for GraphQL error responses.

    Converts HyperScaleException instances into structured error
    extensions compatible with the GraphQL error specification.

    Args:
        error: The original exception.

    Returns:
        A dictionary with 'message' and 'extensions' keys for GraphQL.
    """
    if isinstance(error, HyperScaleException):
        return {
            "message": error.message,
            "extensions": {
                "code": error.code,
                "http_status": error.http_status,
                "detail": error.detail,
            },
        }
    return {
        "message": str(error),
        "extensions": {
            "code": "INTERNAL_ERROR",
        },
    }
