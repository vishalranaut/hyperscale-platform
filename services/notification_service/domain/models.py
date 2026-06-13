"""HyperScale Platform — Notification Service Domain Models.

Beanie ODM models for notifications and user push tokens.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from beanie import Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING

from shared.db.mongodb import BaseDocument


class NotificationType(str, Enum):
    """Types of notifications."""

    ORDER_UPDATE = "order_update"
    NEW_MESSAGE = "new_message"
    PROMOTION = "promotion"
    SYSTEM_ALERT = "system_alert"


class NotificationStatus(str, Enum):
    """Notification read/delivery status."""

    UNREAD = "unread"
    READ = "read"


class Notification(BaseDocument):
    """A notification delivered to a user.

    Attributes:
        user_id: The recipient's user ID.
        title: Notification title.
        body: Notification body/message.
        notification_type: Type of notification.
        status: Read status.
        data: Optional payload/deep-link data.
    """

    user_id: str
    title: str
    body: str
    notification_type: NotificationType = NotificationType.SYSTEM_ALERT
    status: NotificationStatus = NotificationStatus.UNREAD
    data: dict[str, Any] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""
        name = "notifications"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
        ]


class DevicePlatform(str, Enum):
    """Supported device platforms."""

    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class PushToken(BaseDocument):
    """Push notification token for a user's device.

    Attributes:
        user_id: The owner of the device.
        token: Firebase Cloud Messaging (FCM) token.
        platform: Device platform (ios, android, web).
        device_id: Unique device identifier.
        is_active: Whether the token is currently active.
    """

    user_id: str
    token: Indexed(str, unique=True)  # type: ignore[valid-type]
    platform: DevicePlatform
    device_id: str
    is_active: bool = True

    class Settings:
        """Beanie collection settings."""
        name = "push_tokens"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("token", ASCENDING)], unique=True),
        ]
