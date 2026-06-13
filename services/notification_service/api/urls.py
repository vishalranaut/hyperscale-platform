"""HyperScale Platform — Notification Service API URLs."""

from django.urls import path
from services.notification_service.api import views

urlpatterns = [
    path("devices", views.register_device, name="device-register"),
    path("notifications", views.get_notifications, name="notification-list"),
    path("notifications/read-all", views.mark_all_read, name="notification-read-all"),
    path("notifications/<str:notification_id>/read", views.mark_read, name="notification-read"),
]
