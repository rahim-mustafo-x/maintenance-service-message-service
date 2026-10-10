import asyncio
from asyncio import CancelledError
from typing import List, Optional
from uuid import uuid4

from fastapi import WebSocket

from config import PING, PONG, JWT_SECRET_KEY
from connection import Presence
from model import Session, Conversation, Page
from websocket_manager import MessageMembersManager

from jwt import (
    decode,
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidSignatureError,
)


presence = Presence()
message_members_manager = MessageMembersManager()

HEARTBEAT_INTERVAL = 10


def user_id_from_auth(
    auth: str,
) -> int:
    try:
        if auth.startswith("Bearer "):
            token = auth[7:]
        elif auth.startswith("bearer "):
            token = auth[7:]
        else:
            token = auth

        payload = decode(
            token,
            JWT_SECRET_KEY,
            algorithms=["HS256"],
        )

        return int(payload["userId"])

    except (
        ExpiredSignatureError,
        InvalidSignatureError,
        DecodeError,
        ImmatureSignatureError,
        KeyError,
        ValueError,
    ):
        return -1


async def start_conversation(
    auth: str,
    websocket: WebSocket,
    chat_id: str | None,
) -> Session | None:

    user_id = user_id_from_auth(auth)

    if user_id == -1:
        return None

    session = Session(
        session_id=str(uuid4()),
        user_id=user_id,
        chat_id=chat_id,
        time_to_live=30,
    )

    # Claim session and check if it superseded another
    success, superseded = await presence.claim_session(session)

    if not success:
        return None

    await message_members_manager.connect(
        session.session_id,
        websocket,
        session
    )

    return session


async def heartbeat(
    session: Session,
    websocket: WebSocket
) -> None:

    try:
        while True:

            await asyncio.sleep(
                HEARTBEAT_INTERVAL
            )

            # Check if session still owns the presence
            current = await presence.get_presence(
                session.user_id
            )

            if current is None or current.session_id != session.session_id:
                await message_members_manager.close(
                    session.session_id
                )
                return

            # Send binary PING
            try:
                await websocket.send_bytes(PING)
            except Exception:
                await presence.delete_if_current(session)
                await message_members_manager.close(session.session_id)
                return

    except CancelledError:
        return


async def receive_text(
    session: Session,
    text: str,
    websocket: WebSocket
) -> None:
    import json
    try:
        data = json.loads(text)
        event_type = data.get("type")
        payload = data.get("payload", {})
        request_id = data.get("request_id")

        if event_type == "LIST_CONVERSATIONS":
            await handle_list_conversations(session, payload, request_id, websocket)
        elif event_type == "OPEN_CONVERSATION":
            await handle_open_conversation(session, payload, request_id, websocket)
        elif event_type == "SEND_MESSAGE":
            await handle_send_message(session, payload, request_id, websocket)
        elif event_type == "GET_HISTORY":
            await handle_get_history(session, payload, request_id, websocket)
        else:
            await websocket.send_text(json.dumps({
                "type": "ERROR",
                "request_id": request_id,
                "payload": {"code": "UNKNOWN_EVENT", "message": f"Event {event_type} not supported"}
            }))

    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "payload": {"code": "INVALID_JSON", "message": "Invalid JSON payload"}
        }))
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "payload": {"code": "INTERNAL_ERROR", "message": str(e)}
        }))


async def receive_bytes(
    session: Session,
    data: bytes,
) -> None:
    if data == PONG:
        # Only refresh if this session still owns the presence
        if await presence.refresh_presence(session):
            print(f"Heartbeat refreshed for user {session.user_id}")
        else:
            print(f"Heartbeat ignored for superseded session {session.session_id}")


async def disconnect(
    session: Session,
) -> None:

    await presence.delete_if_current(
        session
    )

    await message_members_manager.close(
        session.session_id
    )


async def handle_list_conversations(session, payload, request_id, websocket):
    from repository import ConversationRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")

    page = payload.get("page", 1)
    size = payload.get("size", 10)

    data = await repo.get_conversations_by_user(session.user_id, page, size)

    import json
    await websocket.send_text(json.dumps({
        "type": "CONVERSATIONS_LIST",
        "request_id": request_id,
        "payload": data.model_dump()
    }))

async def handle_open_conversation(session, payload, request_id, websocket):
    chat_id = payload.get("chat_id")
    if not chat_id:
        import json
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "MISSING_CHAT_ID", "message": "chat_id is required"}
        }))
        return

    session.chat_id = chat_id

    import json
    await websocket.send_text(json.dumps({
        "type": "CONVERSATION_OPENED",
        "request_id": request_id,
        "payload": {"chat_id": chat_id}
    }))

async def handle_send_message(session, payload, request_id, websocket):
    from repository import RoomRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient
    from model import Room
    import json

    text = payload.get("text")
    images = payload.get("images", [])

    if not session.chat_id:
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "NO_ACTIVE_CHAT", "message": "No conversation opened"}
        }))
        return

    # 1. Persist to DB
    client = AsyncIOMotorClient(MONGODB_URL)
    repo = RoomRepository(client, "maintenance_service")

    room_id = str(uuid4())
    room = Room(
        room_id=room_id,
        conversation_id=session.chat_id,
        text=text,
        who_sent=session.user_id,
        images=images
    )
    await repo.add(room)

    # 2. Broadcast via Redis
    msg_json = json.dumps(room.model_dump())
    await message_members_manager.broadcast_message(session.chat_id, msg_json)

    await websocket.send_text(json.dumps({
        "type": "MESSAGE_SENT",
        "request_id": request_id,
        "payload": room.model_dump()
    }))

async def handle_get_history(session, payload, request_id, websocket):
    from repository import RoomRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient
    import json

    page = payload.get("page", 1)
    size = payload.get("size", 10)

    if not session.chat_id:
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "NO_ACTIVE_CHAT", "message": "No conversation opened"}
        }))
        return

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = RoomRepository(client, "maintenance_service")

    data = await repo.get_messages(session.chat_id, page, size)

    await websocket.send_text(json.dumps({
        "type": "MESSAGES_PAGE",
        "request_id": request_id,
        "payload": data.model_dump()
    }))

async def get_user_service_data(path: str, auth: str):
    """Call USER-SERVICE through Eureka with a canonical Bearer JWT header."""
    from py_eureka_client.eureka_client import do_service_async

    # USER-SERVICE's JwtFilter accepts the exact "Bearer " prefix.
    # The message service's own decoder is more permissive, so normalize here.
    raw_token = auth.strip()
    if raw_token[:7].lower() == "bearer ":
        raw_token = raw_token[7:].strip()
    if not raw_token:
        raise RuntimeError("Missing access token for USER-SERVICE request")

    response = await do_service_async(
        "USER-SERVICE",
        path,
        return_type="json",
        headers={"Authorization": f"Bearer {raw_token}"},
        timeout=5,
    )
    if not isinstance(response, dict):
        raise RuntimeError("USER-SERVICE returned an invalid response")
    if response.get("code") not in (200, 302):
        raise RuntimeError(response.get("message") or "USER-SERVICE request failed")
    return response.get("data")


async def create_conversation(
    auth: str,
    target_user_id: int,
) -> Conversation | None:
    user_id = user_id_from_auth(auth)
    if user_id == -1 or target_user_id == user_id:
        return None

    from repository import ConversationRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient
    from model import Conversation
    import uuid

    # Resolve the participant from USER-SERVICE via Eureka, not MongoDB.
    target_user = await get_user_service_data(f"/v1/user/{target_user_id}", auth)
    if not isinstance(target_user, dict) or target_user.get("id") is None:
        return None
    target_name = target_user.get("fullName") or target_user.get("phoneNumber") or f"User {target_user_id}"

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")

    existing = await repo.get_page(
        query={"people": {"$all": [user_id, target_user_id]}},
        page=1,
        size=1
    )
    if existing.items:
        conversation = existing.items[0]
        if conversation.name == "New Chat":
            await repo.update_fields(
                conversation.conversation_id,
                {"name": target_name}
            )
            conversation.name = target_name
        return conversation

    new_conv = Conversation(
        conversation_id=str(uuid.uuid4()),
        name=target_name,
        people=[user_id, target_user_id]
    )
    await repo.create_conversation(new_conv)
    return new_conv

async def conversations(
    auth: str,
    page: int,
    size: int,
) -> Page[Conversation] | None:
    user_id = user_id_from_auth(auth)
    if user_id == -1:
        return None

    from repository import ConversationRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")

    return await repo.get_conversations_by_user(user_id, page, size)

async def conversations(
    auth: str,
    page: int,
    size: int,
) -> Page[Conversation] | None:
    user_id = user_id_from_auth(auth)
    if user_id == -1:
        return None

    from repository import ConversationRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")

    return await repo.get_conversations_by_user(user_id, page, size)

async def search_users(
    auth: str,
    query: str,
) -> List[dict]:
    user_id = user_id_from_auth(auth)
    if user_id == -1:
        return []

    from urllib.parse import quote

    # USER-SERVICE owns user identity and search; message-service only stores chats.
    data = await get_user_service_data(
        f"/v1/user/search?q={quote(query)}",
        auth,
    )
    if not isinstance(data, list):
        return []

    return [
        {
            "userId": user.get("id"),
            "name": user.get("fullName") or user.get("phoneNumber") or f"User {user.get('id')}",
            "phoneNumber": user.get("phoneNumber"),
            "avatar": None,
        }
        for user in data
        if isinstance(user, dict) and user.get("id") is not None
    ]
