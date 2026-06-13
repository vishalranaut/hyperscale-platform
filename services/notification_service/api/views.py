"""HyperScale Platform — Notification Service REST API Views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from pydantic import BaseModel

from services.notification_service.services.notification_service import NotificationService
from shared.auth.permissions import IsAuthenticated
from shared.logging import get_logger

logger = get_logger(__name__)


class RegisterDeviceRequest(BaseModel):
    """Request schema for registering a device token."""
    token: str
    platform: str
    device_id: str


def _get_service() -> NotificationService:
    return NotificationService()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def register_device(request: Request) -> Response:
    """Register a device for push notifications.

    POST /api/v1/devices
    """
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    data = RegisterDeviceRequest(**request.data)
    
    service = _get_service()
    token = await service.register_device(
        user_id=user_id,
        token=data.token,
        platform=data.platform,
        device_id=data.device_id,
    )

    return Response(
        {
            "id": str(token.id),
            "token": token.token,
            "platform": token.platform.value,
            "device_id": token.device_id,
            "is_active": token.is_active,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def get_notifications(request: Request) -> Response:
    """Get user's notifications.

    GET /api/v1/notifications
    """
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    page = int(request.query_params.get("page", 1))
    page_size = int(request.query_params.get("page_size", 20))

    service = _get_service()
    notifications = await service.get_user_notifications(user_id, page, page_size)

    response_data = []
    for notif in notifications:
        response_data.append({
            "id": str(notif.id),
            "title": notif.title,
            "body": notif.body,
            "notification_type": notif.notification_type.value,
            "status": notif.status.value,
            "data": notif.data,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        })

    return Response({"notifications": response_data, "page": page, "page_size": page_size})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def mark_read(request: Request, notification_id: str) -> Response:
    """Mark a notification as read.

    POST /api/v1/notifications/{notification_id}/read
    """
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    service = _get_service()
    
    notif = await service.mark_as_read(notification_id, user_id)
    
    return Response({
        "id": str(notif.id),
        "status": notif.status.value,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def mark_all_read(request: Request) -> Response:
    """Mark all unread notifications as read.

    POST /api/v1/notifications/read-all
    """
    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    service = _get_service()
    
    updated_count = await service.mark_all_as_read(user_id)
    
    return Response({"updated_count": updated_count})
