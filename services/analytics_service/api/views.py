"""HyperScale Platform — Analytics Service API Views."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from shared.auth.permissions import IsAdminUser


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_dashboard_metrics(request: Request) -> Response:
    """Get high-level dashboard metrics (Admin only)."""
    # Mock data for skeleton
    return Response({
        "total_users": 10500,
        "active_orders": 240,
        "revenue_mtd": 54200.00,
    })
