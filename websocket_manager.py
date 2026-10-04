from typing import Dict

from fastapi import WebSocket


class MessageMembersManager:

    def __init__(self):
        # session_id -> websocket
        self.members: Dict[str, WebSocket] = {}

    async def connect(
        self,
        session_id: str,
        websocket: WebSocket
    ) -> None:

        await websocket.accept()

        self.members[session_id] = websocket

    @staticmethod
    async def disconnect(
        session: Session,
    ) -> None:

        await _presence.delete_if_current(
            session
        )

        _message_members_manager.disconnect(
            session.session_id
        )

    async def send_message(
        self,
        session_id: str,
        message: str
    ) -> bool:

        websocket = self.members.get(
            session_id
        )

        if websocket is None:
            return False

        try:

            await websocket.send_text(
                message
            )

            return True

        except Exception:

            await self.disconnect(
                session_id
            )

            return False

    async def close(
        self,
        session_id: str
    ) -> None:

        websocket = self.members.pop(
            session_id,
            None
        )

        if websocket is None:
            return

        try:
            await websocket.close()

        except Exception:
            pass

    def exists(
        self,
        session_id: str
    ) -> bool:

        return session_id in self.members