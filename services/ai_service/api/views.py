"""HyperScale Platform — AI Service API Views."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from shared.auth.permissions import IsAuthenticated


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def get_recommendations(request: Request) -> Response:
    """Get personalized recommendations.
    
    Architectural Note (Senior Dev):
        This endpoint avoids synchronous ML inference. It hits our MongoDB
        pre-computed cache. If the cache misses, it returns a fast fallback
        and triggers a background task (e.g., Celery) to compute for next time.
    """
    from services.ai_service.services.recommendation import RecommendationService
    
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    service = RecommendationService()
    
    product_ids = await service.get_recommendations(user_id)
    
    return Response({
        "recommended_products": product_ids
    })
