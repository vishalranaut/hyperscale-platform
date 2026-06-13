"""HyperScale Platform — AI Service API Views."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from shared.auth.permissions import IsAuthenticated


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_recommendations(request: Request) -> Response:
    """Get personalized recommendations."""
    # Mock data for skeleton
    return Response({
        "recommended_products": [
            "prod_1",
            "prod_2",
            "prod_3",
        ]
    })
