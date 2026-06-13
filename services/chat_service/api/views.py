"""HyperScale Platform — Chat Service REST API Views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from pydantic import BaseModel, Field

from shared.auth.permissions import IsAuthenticated
from shared.exceptions import NotFoundError
from shared.logging import get_logger

logger = get_logger(__name__)


class CreateRoomRequest(BaseModel):
    """Request schema for creating a room."""
    name: str = ""
    room_type: str = "group"
    members: list[str] = Field(default_factory=list)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
async def create_room(request: Request) -> Response:
    """Create a new chat room.

    POST /api/v1/rooms
    """
    from services.chat_service.domain.models import ChatRoom, RoomType

    user_id = request.user_payload.sub  # type: ignore[attr-defined]
    data = CreateRoomRequest(**request.data)
    
    # Ensure current user is in members and is admin
    members = set(data.members)
    members.add(user_id)

    room = ChatRoom(
        name=data.name,
        room_type=RoomType(data.room_type),
        members=list(members),
        admins=[user_id],
    )
    await room.insert()

    return Response(
        {
            "id": str(room.id),
            "name": room.name,
            "room_type": room.room_type.value,
            "members": room.members,
            "admins": room.admins,
            "created_at": room.created_at.isoformat() if room.created_at else None,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def list_rooms(request: Request) -> Response:
    """List current user's chat rooms.

    GET /api/v1/rooms
    """
    from services.chat_service.domain.models import ChatRoom
    user_id = request.user_payload.sub  # type: ignore[attr-defined]

    rooms = await ChatRoom.find(
        {"members": user_id},
        ChatRoom.is_deleted == False  # noqa: E712
    ).sort("-last_message_at").to_list()

    response_data = []
    for room in rooms:
        response_data.append({
            "id": str(room.id),
            "name": room.name,
            "room_type": room.room_type.value,
            "members": room.members,
            "last_message_at": room.last_message_at.isoformat() if room.last_message_at else None,
            "last_message_preview": room.last_message_preview,
        })

    return Response(response_data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
async def get_messages(request: Request, room_id: str) -> Response:
    """Get message history for a room.

    GET /api/v1/rooms/{room_id}/messages
    """
    from services.chat_service.domain.models import ChatRoom, Message
    from beanie import PydanticObjectId

    user_id = request.user_payload.sub  # type: ignore[attr-defined]

    # Verify membership
    room = await ChatRoom.get(PydanticObjectId(room_id))
    if not room or user_id not in room.members:
        raise NotFoundError(detail={"resource": "Room", "id": room_id})

    # Fetch messages
    page = int(request.query_params.get("page", 1))
    page_size = int(request.query_params.get("page_size", 50))
    skip = (page - 1) * page_size

    messages = await Message.find(
        Message.room_id == room_id,
        Message.is_deleted == False  # noqa: E712
    ).sort("-created_at").skip(skip).limit(page_size).to_list()

    response_data = []
    for msg in messages:
        response_data.append({
            "id": str(msg.id),
            "sender_id": msg.sender_id,
            "content": msg.content,
            "message_type": msg.message_type.value,
            "status": msg.status.value,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    return Response({"messages": response_data, "page": page, "page_size": page_size})
