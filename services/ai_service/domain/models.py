"""HyperScale Platform — AI Service Domain Models.

Models for user preferences and recommendation caching.

Architectural Note (Senior Dev):
    AI models are notoriously slow compared to typical web requests. 
    We pre-compute recommendations asynchronously and cache them here,
    serving O(1) reads to the frontend.
"""

from datetime import UTC, datetime
from typing import Any

from beanie import Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING

from shared.db.mongodb import BaseDocument


class RecommendationCache(BaseDocument):
    """Pre-computed recommendations for a user.
    
    This acts as a materialized view of the AI model's output.
    """
    user_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    recommended_product_ids: list[str] = Field(default_factory=list)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    model_version: str = "v1"
    
    class Settings:
        name = "recommendation_cache"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
        ]


class UserPreference(BaseDocument):
    """Explicit and implicit user preferences."""
    user_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    viewed_categories: dict[str, int] = Field(default_factory=dict)
    purchased_categories: dict[str, int] = Field(default_factory=dict)
    
    class Settings:
        name = "user_preferences"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
        ]
