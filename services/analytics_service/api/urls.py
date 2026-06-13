"""HyperScale Platform — Analytics Service API URLs."""

from django.urls import path
from services.analytics_service.api import views

urlpatterns = [
    path("metrics", views.get_dashboard_metrics, name="dashboard-metrics"),
]
