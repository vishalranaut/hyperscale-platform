"""HyperScale Platform — Chat Service WebSocket URL Routing."""

from django.urls import re_path

from services.chat_service.consumers.chat_consumer import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/$", ChatConsumer.as_asgi()),
]
