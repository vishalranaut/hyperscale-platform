"""HyperScale Platform — Notification Service Logic.

Manages user notifications, push token registration, and triggering
Firebase Cloud Messaging (FCM) pushes.
"""

from __future__ import annotations

from typing import Any

from services.notification_service.domain.models import (
    DevicePlatform,
    Notification,
    NotificationStatus,
    NotificationType,
    PushToken,
)
from services.notification_service.services.firebase_client import FirebaseClient
from shared.exceptions import NotFoundError
from shared.logging import get_logger

logger = get_logger(__name__)


class NotificationService:
    """Business logic layer for notifications.

    Args:
        firebase_client: Optional FirebaseClient instance.
    """

    def __init__(self, firebase_client: FirebaseClient | None = None) -> None:
        self._firebase = firebase_client or FirebaseClient()

    async def register_device(
        self,
        user_id: str,
        token: str,
        platform: str,
        device_id: str,
    ) -> PushToken:
        """Register a new device token for push notifications.

        Args:
            user_id: The user's ID.
            token: FCM token.
            platform: 'ios', 'android', or 'web'.
            device_id: Unique device identifier.

        Returns:
            The created or updated PushToken.
        """
        # Invalidate old token for this device if it exists
        existing_device = await PushToken.find_one(
            PushToken.device_id == device_id
        )
        if existing_device:
            if existing_device.token != token:
                existing_device.is_active = False
                await existing_device.save()

        # Check if token already exists
        push_token = await PushToken.find_one(PushToken.token == token)
        if push_token:
            push_token.user_id = user_id
            push_token.device_id = device_id
            push_token.platform = DevicePlatform(platform)
            push_token.is_active = True
            await push_token.save()
        else:
            push_token = PushToken(
                user_id=user_id,
                token=token,
                platform=DevicePlatform(platform),
                device_id=device_id,
                is_active=True,
            )
            await push_token.insert()

        logger.info("device_registered", user_id=user_id, device_id=device_id)
        return push_token

    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        notification_type: str = "system_alert",
        data: dict[str, Any] | None = None,
    ) -> Notification:
        """Create a notification and attempt push delivery.

        Args:
            user_id: Recipient user ID.
            title: Notification title.
            body: Notification body.
            notification_type: Type of notification.
            data: Optional data payload.

        Returns:
            The created Notification document.
        """
        # Save to database
        notification = Notification(
            user_id=user_id,
            title=title,
            body=body,
            notification_type=NotificationType(notification_type),
            data=data or {},
        )
        await notification.insert()

        # Find active push tokens for user
        tokens = await PushToken.find(
            PushToken.user_id == user_id,
            PushToken.is_active == True  # noqa: E712
        ).to_list()

        # Stringify data for FCM
        str_data = {k: str(v) for k, v in (data or {}).items()}

        # Send pushes asynchronously (in a real app, use Celery/BackgroundTasks)
        # Here we just await them sequentially for simplicity.
        success_count = 0
        for push_token in tokens:
            success = await self._firebase.send_to_token(
                token=push_token.token,
                title=title,
                body=body,
                data=str_data,
            )
            if success:
                success_count += 1
            else:
                # Token might be invalid, mark it inactive
                push_token.is_active = False
                await push_token.save()

        logger.info(
            "notification_sent",
            user_id=user_id,
            notification_id=str(notification.id),
            tokens_attempted=len(tokens),
            success_count=success_count,
        )

        return notification

    async def get_user_notifications(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Notification]:
        """Get paginated notifications for a user."""
        skip = (page - 1) * page_size
        return await Notification.find(
            Notification.user_id == user_id,
            Notification.is_deleted == False  # noqa: E712
        ).sort("-created_at").skip(skip).limit(page_size).to_list()

    async def mark_as_read(self, notification_id: str, user_id: str) -> Notification:
        """Mark a notification as read."""
        from beanie import PydanticObjectId
        from beanie.operators import Set

        notification = await Notification.get(PydanticObjectId(notification_id))
        if not notification or notification.user_id != user_id:
            raise NotFoundError(detail={"resource": "Notification", "id": notification_id})

        await notification.update(Set({"status": NotificationStatus.READ}))
        return notification

    async def mark_all_as_read(self, user_id: str) -> int:
        """Mark all unread notifications as read for a user."""
        from beanie.operators import Set

        result = await Notification.find(
            Notification.user_id == user_id,
            Notification.status == NotificationStatus.UNREAD
        ).update(Set({"status": NotificationStatus.READ}))
        
        return result.modified_count
