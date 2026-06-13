"""HyperScale Platform — User Service Root URL Configuration."""

from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint.

    GET /health

    Returns:
        200: Service health status.
    """
    return Response({
        "status": "healthy",
        "service": "user-service",
        "version": "1.0.0",
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def ready_check(request):
    """Readiness check endpoint.

    GET /ready

    Returns:
        200: Service readiness status.
    """
    return Response({
        "status": "ready",
        "service": "user-service",
    })


urlpatterns = [
    path("health", health_check, name="health"),
    path("ready", ready_check, name="ready"),
    path("api/v1/", include("services.user_service.api.urls")),
]
