"""HyperScale Platform — Chat Service Domain Models.

Beanie ODM models for chat rooms, messages, and presence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from beanie import Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING

from shared.db.mongodb import BaseDocument


class RoomType(str, Enum):
    """Chat room types."""

    DIRECT = "direct"
    GROUP = "group"
    SUPPORT = "support"


class MessageType(str, Enum):
    """Message content types."""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    """Message delivery status."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class PresenceStatus(str, Enum):
    """User presence status."""

    ONLINE = "online"
    AWAY = "away"
    OFFLINE = "offline"


class ChatRoom(BaseDocument):
    """Chat room document.

    Attributes:
        name: Room display name (for groups).
        room_type: Type of chat room.
        members: List of user IDs in the room.
        admins: List of admin user IDs.
        metadata: Room-specific metadata.
        last_message_at: Timestamp of the last message.
        last_message_preview: Preview text of the last message.
        is_archived: Whether the room is archived.
    """

    name: str = ""
    room_type: RoomType = RoomType.DIRECT
    members: list[str] = Field(default_factory=list)
    admins: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_message_at: datetime | None = None
    last_message_preview: str = ""
    is_archived: bool = False

    class Settings:
        """Beanie collection settings."""
        name = "chat_rooms"
        indexes = [
            IndexModel([("members", ASCENDING)]),
            IndexModel([("room_type", ASCENDING)]),
            IndexModel([("last_message_at", DESCENDING)]),
        ]


class Message(BaseDocument):
    """Chat message document.

    Attributes:
        room_id: Reference to the ChatRoom.
        sender_id: User ID of the message sender.
        content: Message text content.
        message_type: Type of message content.
        status: Delivery status.
        reply_to_id: ID of the message being replied to.
        reactions: Map of emoji to list of user IDs.
        attachments: List of attachment metadata dicts.
        edited_at: Timestamp if message was edited.
        is_pinned: Whether the message is pinned.
    """

    room_id: str
    sender_id: str
    content: str = ""
    message_type: MessageType = MessageType.TEXT
    status: MessageStatus = MessageStatus.SENT
    reply_to_id: str | None = None
    reactions: dict[str, list[str]] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    edited_at: datetime | None = None
    is_pinned: bool = False

    class Settings:
        """Beanie collection settings."""
        name = "messages"
        indexes = [
            IndexModel([("room_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("sender_id", ASCENDING)]),
            IndexModel([("room_id", ASCENDING), ("is_pinned", ASCENDING)]),
        ]


class Presence(BaseDocument):
    """User presence tracking document.

    Attributes:
        user_id: The user's ID.
        status: Current presence status.
        last_seen: Last activity timestamp.
        device_info: Information about the user's device.
    """

    user_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    status: PresenceStatus = PresenceStatus.OFFLINE
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    device_info: dict[str, str] = Field(default_factory=dict)

    class Settings:
        """Beanie collection settings."""
        name = "presence"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
            IndexModel([("status", ASCENDING)]),
        ]
