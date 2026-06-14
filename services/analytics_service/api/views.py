"""HyperScale Platform — Analytics Service API Views."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from shared.auth.permissions import IsAdminUser


@api_view(["GET"])
@permission_classes([IsAdminUser])
async def get_dashboard_metrics(request: Request) -> Response:
    """Get high-level dashboard metrics (Admin only).
    
    Architectural Note (Senior Dev):
        In a massive scale system, this endpoint would hit Redis or a materialized
        view. Here, we fetch the most recent DailyMetric document which is kept
        updated in near-real-time via Kafka.
    """
    from services.analytics_service.domain.models import DailyMetric
    from datetime import UTC, datetime
    
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    metric = await DailyMetric.find_one(DailyMetric.date_str == today_str)
    
    if not metric:
        return Response({
            "total_users": 0,
            "active_orders": 0,
            "revenue_mtd": 0.0,
        })
        
    return Response({
        "total_users": metric.total_users,
        "active_orders": metric.active_orders,
        "revenue_mtd": metric.revenue_cents / 100.0,
    })
