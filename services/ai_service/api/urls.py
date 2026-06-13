"""HyperScale Platform — AI Service API URLs."""

from django.urls import path
from services.ai_service.api import views

urlpatterns = [
    path("recommendations", views.get_recommendations, name="ai-recommendations"),
]
