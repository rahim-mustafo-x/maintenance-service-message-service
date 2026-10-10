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


async def get_authorized_conversation(user_id: int, conversation_id: str):
    """Return a direct conversation only when the user is one of its two participants."""
    from repository import ConversationRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient

    if not conversation_id:
        return None
    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")
    conversation = await repo.get_by_id(conversation_id)
    if conversation is None:
        return None
    people = conversation.people or []
    if len(people) != 2 or len(set(people)) != 2 or user_id not in people:
        return None
    return conversation


async def handle_list_conversations(session, payload, request_id, websocket):
    from repository import ConversationRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")
    await normalize_direct_conversations(client, session.user_id)

    page = payload.get("page", 1)
    size = payload.get("size", 10)

    data = await repo.get_conversations_by_user(session.user_id, page, size)

    import json
    await websocket.send_text(json.dumps({
        "type": "CONVERSATIONS_LIST",
        "request_id": request_id,
        "payload": data.model_dump(mode="json")
    }))

async def handle_open_conversation(session, payload, request_id, websocket):
    import json
    chat_id = payload.get("chat_id")
    if not chat_id:
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "MISSING_CHAT_ID", "message": "chat_id is required"}
        }))
        return

    conversation = await get_authorized_conversation(session.user_id, chat_id)
    if conversation is None:
        session.chat_id = None
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "CONVERSATION_FORBIDDEN", "message": "Conversation not found or you are not a participant"}
        }))
        return

    session.chat_id = conversation.conversation_id
    await websocket.send_text(json.dumps({
        "type": "CONVERSATION_OPENED",
        "request_id": request_id,
        "payload": {"chat_id": conversation.conversation_id}
    }))

async def handle_send_message(session, payload, request_id, websocket):
    from repository import RoomRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient
    from model import Room
    import json

    text = payload.get("text")
    images = payload.get("images", [])

    if not isinstance(text, str) or not text.strip():
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "EMPTY_MESSAGE", "message": "Message text cannot be empty"}
        }))
        return
    if not isinstance(images, list):
        images = []

    if not session.chat_id:
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "NO_ACTIVE_CHAT", "message": "No conversation opened"}
        }))
        return

    # Validate membership on every send, not just when the chat is opened.
    conversation = await get_authorized_conversation(session.user_id, session.chat_id)
    if conversation is None:
        session.chat_id = None
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "CONVERSATION_FORBIDDEN", "message": "Conversation not found or you are not a participant"}
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
    from repository import ConversationRepository
    conversation_repo = ConversationRepository(client, "maintenance_service")
    from datetime import datetime, timezone
    await conversation_repo.update_fields(
        session.chat_id,
        {"updated_at": datetime.now(timezone.utc)}
    )

    # 2. Broadcast via Redis
    msg_json = json.dumps(room.model_dump(mode="json"))
    await message_members_manager.broadcast_message(session.chat_id, msg_json)

    await websocket.send_text(json.dumps({
        "type": "MESSAGE_SENT",
        "request_id": request_id,
        "payload": room.model_dump(mode="json")
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

    conversation = await get_authorized_conversation(session.user_id, session.chat_id)
    if conversation is None:
        session.chat_id = None
        await websocket.send_text(json.dumps({
            "type": "ERROR",
            "request_id": request_id,
            "payload": {"code": "CONVERSATION_FORBIDDEN", "message": "Conversation not found or you are not a participant"}
        }))
        return

    client = AsyncIOMotorClient(MONGODB_URL)
    repo = RoomRepository(client, "maintenance_service")

    data = await repo.get_messages(session.chat_id, page, size)

    await websocket.send_text(json.dumps({
        "type": "MESSAGES_PAGE",
        "request_id": request_id,
        # Pydantic's default dump contains datetime objects, which json.dumps
        # cannot serialize. JSON mode converts timestamps to ISO-8601 strings so
        # the history response reaches the browser after refresh.
        "payload": data.model_dump(mode="json")
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


async def normalize_direct_conversations(client, user_id: int) -> None:
    """
    Merge legacy duplicate 1:1 conversation records for this user into one stable
    conversation ID. Message documents are reassigned before duplicate conversations
    are removed, so chat history is preserved.
    """
    from datetime import datetime, timezone

    def timestamp(value) -> float:
        if not isinstance(value, datetime):
            return 0.0
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()

    db = client["maintenance_service"]
    conversations_collection = db["conversations"]
    rooms_collection = db["rooms"]

    cursor = conversations_collection.find({"people": user_id})
    groups: dict[tuple[int, int], list[dict]] = {}

    async for document in cursor:
        people = document.get("people") or []
        try:
            unique_people = sorted({int(person) for person in people})
        except (TypeError, ValueError):
            continue
        if len(unique_people) != 2 or user_id not in unique_people:
            continue
        groups.setdefault((unique_people[0], unique_people[1]), []).append(document)

    for (low_id, high_id), documents in groups.items():
        canonical_id = f"direct-{low_id}-{high_id}"
        # Repository lookups use MongoDB _id, so the canonical document must
        # have that exact key, not merely a matching conversation_id field.
        canonical = next(
            (doc for doc in documents if doc.get("_id") == canonical_id),
            None,
        )

        if canonical is None:
            # Prefer the most recently active legacy record as the source metadata.
            source = max(documents, key=lambda doc: timestamp(doc.get("updated_at")))
            canonical = {
                "_id": canonical_id,
                "conversation_id": canonical_id,
                "name": source.get("name") or "Conversation",
                "profile_image": source.get("profile_image"),
                "people": [low_id, high_id],
                "updated_at": max(
                    (doc.get("updated_at") for doc in documents if doc.get("updated_at") is not None),
                    key=timestamp,
                    default=datetime.now(timezone.utc),
                ),
            }
            try:
                await conversations_collection.insert_one(canonical)
            except Exception:
                # Another request may have created the canonical record concurrently.
                canonical = await conversations_collection.find_one({"_id": canonical_id})
                if canonical is None:
                    raise

        # Always use the deterministic ID as the canonical conversation ID.
        # A legacy document may have an _id that differs from conversation_id.
        canonical_id = f"direct-{low_id}-{high_id}"
        latest_updated = max(
            (doc.get("updated_at") for doc in documents if doc.get("updated_at") is not None),
            key=timestamp,
            default=canonical.get("updated_at") or datetime.now(timezone.utc),
        )
        await conversations_collection.update_one(
            {"_id": canonical_id},
            {"$set": {
                "conversation_id": canonical_id,
                "people": [low_id, high_id],
                "updated_at": latest_updated,
            }},
        )

        legacy_ids = []
        for document in documents:
            old_id = document.get("_id")
            old_conversation_id = document.get("conversation_id") or old_id
            if old_conversation_id and old_conversation_id != canonical_id:
                await rooms_collection.update_many(
                    {"conversation_id": old_conversation_id},
                    {"$set": {"conversation_id": canonical_id}},
                )
            if old_id is not None and old_id != canonical_id:
                legacy_ids.append(old_id)

        # Keep legacy conversation documents until the merge has been verified.
        # The frontend hides duplicate participant pairs, while preserving old records
        # gives us a recovery path if a legacy message references an unexpected ID.

        # Legacy conversations may have stale/missing updated_at values. Derive
        # activity from the newest preserved message after all history is moved.
        latest_message = await rooms_collection.find(
            {"conversation_id": canonical_id},
            {"created_at": 1},
        ).sort("created_at", -1).limit(1).to_list(length=1)
        if latest_message and latest_message[0].get("created_at") is not None:
            message_time = latest_message[0]["created_at"]
            if timestamp(message_time) > timestamp(latest_updated):
                await conversations_collection.update_one(
                    {"_id": canonical_id},
                    {"$set": {"updated_at": message_time}},
                )


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
    await normalize_direct_conversations(client, user_id)

    low_id, high_id = sorted((user_id, target_user_id))
    # Every pair has one deterministic conversation ID, including legacy chats.
    conversation_id = f"direct-{low_id}-{high_id}"
    existing_by_id = await repo.get_by_id(conversation_id)
    if existing_by_id is not None:
        # Conversation.name is shared storage and cannot represent each participant's
        # opposite-side display name. The frontend resolves the peer profile by ID.
        return existing_by_id

    new_conv = Conversation(
        conversation_id=conversation_id,
        name=target_name,
        people=[low_id, high_id]
    )
    try:
        await repo.create_conversation(new_conv)
        return new_conv
    except Exception:
        existing_by_id = await repo.get_by_id(conversation_id)
        if existing_by_id is not None:
            return existing_by_id
        raise

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
    # Repair old duplicate chats on read, moving their messages before deleting extras.
    await normalize_direct_conversations(client, user_id)

    return await repo.get_conversations_by_user(user_id, page, size)

async def messages(
    auth: str,
    conversation_id: str,
    page: int,
    size: int,
) -> Page | None:
    user_id = user_id_from_auth(auth)
    if user_id == -1:
        return None
    conversation = await get_authorized_conversation(user_id, conversation_id)
    if conversation is None:
        return None
    from repository import RoomRepository
    from config import MONGODB_URL
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGODB_URL)
    repo = RoomRepository(client, "maintenance_service")
    return await repo.get_messages(conversation_id, page, size)


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
