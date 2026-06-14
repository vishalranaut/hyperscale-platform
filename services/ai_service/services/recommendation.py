"""HyperScale Platform — AI Recommendation Engine.

Provides product recommendations based on user history.

Architectural Note (Senior Dev):
    We use a Strategy Pattern here. Currently, we use a simple collaborative 
    filtering placeholder. In the future, we can inject a Vertex AI or OpenAI 
    embeddings strategy without changing the core business logic.
"""

from datetime import UTC, datetime
from typing import Any

from services.ai_service.domain.models import RecommendationCache, UserPreference
from shared.logging import get_logger

logger = get_logger(__name__)


class RecommendationService:
    """Service to compute and retrieve personalized recommendations."""
    
    async def compute_recommendations(self, user_id: str) -> None:
        """Compute recommendations asynchronously.
        
        In production, this would make an RPC call to a GPU-backed inference service
        or query a vector database (e.g., Pinecone/Milvus).
        """
        logger.info("computing_recommendations", user_id=user_id)
        
        # Placeholder logic: Find preferences
        prefs = await UserPreference.find_one(UserPreference.user_id == user_id)
        
        # Mock ML Output
        recommended_ids = ["prod_top_1", "prod_top_2", "prod_top_3"]
        scores = {"prod_top_1": 0.95, "prod_top_2": 0.88, "prod_top_3": 0.76}
        
        # Update Cache (Upsert)
        cache = await RecommendationCache.find_one(RecommendationCache.user_id == user_id)
        if cache:
            cache.recommended_product_ids = recommended_ids
            cache.confidence_scores = scores
            cache.updated_at = datetime.now(UTC)
            await cache.save()
        else:
            cache = RecommendationCache(
                user_id=user_id,
                recommended_product_ids=recommended_ids,
                confidence_scores=scores,
            )
            await cache.insert()
            
    async def get_recommendations(self, user_id: str) -> list[str]:
        """Fetch pre-computed recommendations. O(1) latency."""
        cache = await RecommendationCache.find_one(RecommendationCache.user_id == user_id)
        
        if cache and cache.recommended_product_ids:
            return cache.recommended_product_ids
            
        # Fallback to popular items if no personalized cache exists
        return ["prod_pop_1", "prod_pop_2"]
