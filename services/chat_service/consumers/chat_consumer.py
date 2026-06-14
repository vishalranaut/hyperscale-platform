"""HyperScale Platform — Chat Service WebSocket Consumer.

AsyncWebsocketConsumer implementing real-time chat with typing
indicators, read receipts, and online presence tracking.

Architectural Note (Senior Dev):
    WebSockets maintain persistent stateful connections. In a clustered environment
    with multiple pods, an individual user's socket is tied to a specific pod.
    To allow users on different pods to chat, we use a Redis-backed Channel Layer
    (pub/sub). 
    
    When User A sends a message, Pod A saves it to MongoDB and publishes it to
    a Redis channel (e.g., `room_123`). All pods subscribed to `room_123` receive
    the message and push it down their respective open WebSockets to connected clients.

WebSocket Protocol (JSON):
    Client → Server:
        {"type": "message", "room_id": "...", "content": "...", "reply_to": "..."}
        {"type": "typing", "room_id": "...", "is_typing": true}
        {"type": "read", "room_id": "...", "message_id": "..."}

    Server → Client:
        {"type": "message", "data": {...}}
        {"type": "typing", "user_id": "...", "is_typing": true}
        {"type": "presence", "user_id": "...", "status": "online"}
        {"type": "error", "code": "...", "message": "..."}
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer

from shared.auth.jwt_handler import JWTHandler
from shared.logging import get_logger

logger = get_logger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time chat.

    Handles connection authentication, message broadcasting,
    typing indicators, and read receipts.

    Connection URL:
        ws://host/ws/chat/?token=<jwt_access_token>

    The consumer uses Django Channels groups to broadcast messages
    to all participants in a chat room.
    """

    async def connect(self) -> None:
        """Handle WebSocket connection.

        Authenticates the user via JWT from query parameters,
        then joins all the user's chat room groups.
        """
        # Extract JWT from query params
        query_params = parse_qs(self.scope.get("query_string", b"").decode())
        token = query_params.get("token", [""])[0]

        if not token:
            logger.warning("ws_connect_no_token")
            await self.close(code=4001)
            return

        # Validate JWT
        try:
            jwt_handler = JWTHandler()
            self.user_payload = jwt_handler.decode_token(token)
            self.user_id = self.user_payload.sub
        except Exception as e:
            logger.warning("ws_connect_invalid_token", error=str(e))
            await self.close(code=4001)
            return

        await self.accept()

        # Join user's personal group (for presence and direct messages)
        self.user_group = f"user_{self.user_id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        # Update presence
        await self._update_presence("online")

        # Load user's rooms and join their groups
        await self._join_user_rooms()

        logger.info("ws_connected", user_id=self.user_id)

    async def disconnect(self, close_code: int) -> None:
        """Handle WebSocket disconnection.

        Leaves all room groups and updates presence to offline.

        Args:
            close_code: The WebSocket close code.
        """
        if hasattr(self, "user_id"):
            await self._update_presence("offline")

            # Leave user group
            await self.channel_layer.group_discard(
                self.user_group, self.channel_name
            )

            # Leave all room groups
            if hasattr(self, "room_groups"):
                for group_name in self.room_groups:
                    await self.channel_layer.group_discard(
                        group_name, self.channel_name
                    )

            logger.info("ws_disconnected", user_id=self.user_id, code=close_code)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        """Handle incoming WebSocket messages.

        Routes messages to appropriate handlers based on the 'type' field.

        Args:
            text_data: JSON text message from the client.
            bytes_data: Binary data (not used).
        """
        if not text_data:
            return

        try:
            data = json.loads(text_data)
            msg_type = data.get("type", "")

            if msg_type == "message":
                await self._handle_message(data)
            elif msg_type == "typing":
                await self._handle_typing(data)
            elif msg_type == "read":
                await self._handle_read_receipt(data)
            else:
                await self._send_error("UNKNOWN_TYPE", f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            await self._send_error("INVALID_JSON", "Invalid JSON payload")
        except Exception as e:
            logger.error("ws_receive_error", error=str(e))
            await self._send_error("INTERNAL_ERROR", "An error occurred")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle a new chat message.

        Args:
            data: Message data with room_id, content, and optional reply_to.
        """
        room_id = data.get("room_id", "")
        content = data.get("content", "").strip()
        reply_to = data.get("reply_to")

        if not room_id or not content:
            await self._send_error("VALIDATION_ERROR", "room_id and content are required")
            return

        # Save message to MongoDB
        try:
            from services.chat_service.domain.models import Message, MessageType

            message = Message(
                room_id=room_id,
                sender_id=self.user_id,
                content=content,
                message_type=MessageType.TEXT,
                reply_to_id=reply_to,
            )
            await message.insert()

            # Update room's last message
            from services.chat_service.domain.models import ChatRoom
            from beanie import PydanticObjectId
            from beanie.operators import Set

            room = await ChatRoom.get(PydanticObjectId(room_id))
            if room:
                await room.update(Set({
                    "last_message_at": datetime.now(UTC),
                    "last_message_preview": content[:100],
                }))

            # Broadcast to room group
            group_name = f"room_{room_id}"
            await self.channel_layer.group_send(
                group_name,
                {
                    "type": "chat.message",
                    "data": {
                        "id": str(message.id),
                        "room_id": room_id,
                        "sender_id": self.user_id,
                        "content": content,
                        "message_type": "text",
                        "reply_to_id": reply_to,
                        "created_at": message.created_at.isoformat(),
                    },
                },
            )

            logger.info("message_sent", room_id=room_id, sender=self.user_id)

        except Exception as e:
            logger.error("message_save_failed", error=str(e))
            await self._send_error("SAVE_FAILED", "Failed to save message")

    async def _handle_typing(self, data: dict[str, Any]) -> None:
        """Handle typing indicator.

        Args:
            data: Data with room_id and is_typing flag.
        """
        room_id = data.get("room_id", "")
        is_typing = data.get("is_typing", False)

        if not room_id:
            return

        group_name = f"room_{room_id}"
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "chat.typing",
                "user_id": self.user_id,
                "is_typing": is_typing,
            },
        )

    async def _handle_read_receipt(self, data: dict[str, Any]) -> None:
        """Handle read receipt.

        Args:
            data: Data with room_id and message_id.
        """
        room_id = data.get("room_id", "")
        message_id = data.get("message_id", "")

        if not room_id or not message_id:
            return

        # Update message status
        try:
            from services.chat_service.domain.models import Message, MessageStatus
            from beanie import PydanticObjectId
            from beanie.operators import Set

            message = await Message.get(PydanticObjectId(message_id))
            if message and message.room_id == room_id:
                await message.update(Set({"status": MessageStatus.READ}))

                # Notify the sender
                group_name = f"room_{room_id}"
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "chat.read",
                        "user_id": self.user_id,
                        "message_id": message_id,
                        "room_id": room_id,
                    },
                )
        except Exception as e:
            logger.error("read_receipt_failed", error=str(e))

    async def _join_user_rooms(self) -> None:
        """Join all chat rooms the user is a member of."""
        try:
            from services.chat_service.domain.models import ChatRoom

            rooms = await ChatRoom.find(
                {"members": self.user_id},
                ChatRoom.is_deleted == False,  # noqa: E712
            ).to_list()

            self.room_groups = []
            for room in rooms:
                group_name = f"room_{str(room.id)}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.room_groups.append(group_name)

            logger.debug("joined_rooms", user_id=self.user_id, count=len(rooms))
        except Exception as e:
            logger.error("join_rooms_failed", error=str(e))
            self.room_groups = []

    async def _update_presence(self, status: str) -> None:
        """Update user's online presence.

        Args:
            status: The new presence status ('online', 'away', 'offline').
        """
        try:
            from services.chat_service.domain.models import Presence, PresenceStatus
            from beanie.operators import Set

            presence = await Presence.find_one(Presence.user_id == self.user_id)
            if presence:
                await presence.update(Set({
                    "status": PresenceStatus(status),
                    "last_seen": datetime.now(UTC),
                }))
            else:
                presence = Presence(
                    user_id=self.user_id,
                    status=PresenceStatus(status),
                )
                await presence.insert()

            # Broadcast presence to all user's rooms
            if hasattr(self, "room_groups"):
                for group_name in self.room_groups:
                    await self.channel_layer.group_send(
                        group_name,
                        {
                            "type": "chat.presence",
                            "user_id": self.user_id,
                            "status": status,
                        },
                    )
        except Exception as e:
            logger.error("presence_update_failed", error=str(e))

    async def _send_error(self, code: str, message: str) -> None:
        """Send an error message to the client.

        Args:
            code: Error code.
            message: Human-readable error description.
        """
        await self.send(text_data=json.dumps({
            "type": "error",
            "code": code,
            "message": message,
        }))

    # ── Channel Layer Event Handlers ─────────────────────────────────────────

    async def chat_message(self, event: dict[str, Any]) -> None:
        """Handle incoming chat.message from channel layer.

        Args:
            event: Event data from group_send.
        """
        await self.send(text_data=json.dumps({
            "type": "message",
            "data": event["data"],
        }))

    async def chat_typing(self, event: dict[str, Any]) -> None:
        """Handle incoming chat.typing from channel layer.

        Args:
            event: Event data with user_id and is_typing.
        """
        # Don't echo typing back to the sender
        if event.get("user_id") != self.user_id:
            await self.send(text_data=json.dumps({
                "type": "typing",
                "user_id": event["user_id"],
                "is_typing": event["is_typing"],
            }))

    async def chat_presence(self, event: dict[str, Any]) -> None:
        """Handle incoming chat.presence from channel layer.

        Args:
            event: Event data with user_id and status.
        """
        if event.get("user_id") != self.user_id:
            await self.send(text_data=json.dumps({
                "type": "presence",
                "user_id": event["user_id"],
                "status": event["status"],
            }))

    async def chat_read(self, event: dict[str, Any]) -> None:
        """Handle incoming chat.read from channel layer.

        Args:
            event: Event data with user_id and message_id.
        """
        await self.send(text_data=json.dumps({
            "type": "read_receipt",
            "user_id": event["user_id"],
            "message_id": event["message_id"],
            "room_id": event["room_id"],
        }))

    async def chat_system(self, event: dict[str, Any]) -> None:
        """Handle system messages (e.g., order status updates).

        Args:
            event: Event data with system message content.
        """
        await self.send(text_data=json.dumps({
            "type": "system",
            "data": event.get("data", {}),
        }))
