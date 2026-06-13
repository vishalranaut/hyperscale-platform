"""HyperScale Platform — Chat Service API URLs."""

from django.urls import path
from services.chat_service.api import views

urlpatterns = [
    path("rooms", views.list_rooms, name="room-list"),
    path("rooms/", views.create_room, name="room-create"),
    path("rooms/<str:room_id>/messages", views.get_messages, name="room-messages"),
]
