import asyncio
from asyncio import CancelledError
from uuid import uuid4

from fastapi import WebSocket

from config import PING, PONG, JWT_SECRET_KEY
from connection import Presence
from model import Session
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
        parts = auth.split()

        if len(parts) != 2:
            return -1

        token = parts[1]

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
    chat_id: str,
) -> Session | None:

    user_id = user_id_from_auth(auth)

    if user_id == -1:
        return None

    old_session = await presence.get_presence(
        user_id
    )

    session = Session(
        session_id=str(uuid4()),
        user_id=user_id,
        chat_id=chat_id,
        time_to_live=30,
    )

    await presence.set_presence(
        session
    )

    if old_session is not None:
        await message_members_manager.close(
            old_session.session_id
        )

    await message_members_manager.connect(
        session.session_id,
        websocket,
    )

    return session


async def heartbeat(
    session: Session,
) -> None:

    try:
        while True:

            await asyncio.sleep(
                HEARTBEAT_INTERVAL
            )

            current = await presence.get_presence(
                session.user_id
            )

            if current is None:
                await message_members_manager.close(
                    session.session_id
                )
                return

            if (
                current.session_id
                != session.session_id
            ):
                await message_members_manager.close(
                    session.session_id
                )
                return

            sent = await message_members_manager.send_message(
                session.session_id,
                PING,
            )

            if not sent:
                await presence.delete_if_current(
                    session
                )
                return

    except CancelledError:
        return


async def receive_text(
    session: Session,
    text: str,
) -> None:

    if text == PONG:

        current = await presence.get_presence(
            session.user_id
        )

        if current is None:
            return

        if (
            current.session_id
            != session.session_id
        ):
            return

        await presence.refresh_presence(
            session
        )

        return

    await handle_message(
        session,
        text,
    )


async def handle_message(
    session: Session,
    text: str,
) -> None:

    print(
        f"user={session.user_id}"
    )

    print(
        f"chat={session.chat_id}"
    )

    print(
        f"text={text}"
    )


async def disconnect(
    session: Session,
) -> None:

    await presence.delete_if_current(
        session
    )

    await message_members_manager.close(
        session.session_id
    )