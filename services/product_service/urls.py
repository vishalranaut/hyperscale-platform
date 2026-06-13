"""HyperScale Platform — Product Service Root URLs."""

from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint."""
    return Response({"status": "healthy", "service": "product-service", "version": "1.0.0"})


urlpatterns = [
    path("health", health_check, name="health"),
    path("api/v1/", include("services.product_service.api.urls")),
]
