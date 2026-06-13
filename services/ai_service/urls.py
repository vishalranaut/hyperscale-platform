"""HyperScale Platform — AI Service Root URLs."""

from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "healthy", "service": "ai-service"})


urlpatterns = [
    path("health", health_check),
    path("api/v1/", include("services.ai_service.api.urls")),
]
