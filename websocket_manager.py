import asyncio
from typing import Dict
from redis.asyncio import Redis

from fastapi import WebSocket

from config import REDIS_HOST, REDIS_PORT


class MessageMembersManager:

    def __init__(self):
        # session_id -> (websocket, session)
        self.members: Dict[str, tuple[WebSocket, Any]] = {}
        self.redis = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        self.broadcast_channel = "messages:broadcast"
        self.invalidation_channel = "sessions:invalidation"

    async def connect(
        self,
        session_id: str,
        websocket: WebSocket,
        session: Any
    ) -> None:

        await websocket.accept()

        self.members[session_id] = (websocket, session)

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

        member = self.members.get(
            session_id
        )

        if member is None:
            return False

        websocket, _ = member

        try:

            await websocket.send_text(
                message
            )

            return True

        except Exception:

            await self.close(
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

    async def broadcast_message(
        self,
        chat_id: str,
        message: str
    ) -> None:
        \"\"\"
        Publishes a message to the global Redis broadcast channel.
        \"\"\"
        payload = {
            "chat_id": chat_id,
            "message": message
        }
        import json
        await self.redis.publish(
            self.broadcast_channel,
            json.dumps(payload)
        )

    async def listen_for_broadcasts(self, presence):
        \"\"\"
        Background task to listen for messages and session invalidations.
        \"\"\"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(
            self.broadcast_channel,
            self.invalidation_channel
        )

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            channel = message["channel"]
            data = message["data"]

            if channel == self.invalidation_channel:
                # Session invalidation: data is the JSON of the superseded session
                import json
                try:
                    session_data = json.loads(data)
                    session_id = session_data["session_id"]
                    await self.close(session_id)
                except Exception as e:
                    print(f"Error processing invalidation: {e}")

            elif channel == self.broadcast_channel:
                # Message broadcast: data is {chat_id, message}
                import json
                try:
                    payload = json.loads(data)
                    chat_id = payload["chat_id"]
                    msg_text = payload["message"]

                    # Deliver to all local members associated with this chat
                    # We need to check which local sessions belong to this chat
                    # This requires iterating over sessions or having a chat->sessions map.
                    # For now, we'll check the presence of each local member.
                    for session_id, websocket in list(self.members.items()):
                        # We can't easily check chat_id without the session object
                        # This is a gap. We should store session objects or use Redis.
                        # For now, we'll rely on the session data in Redis.
                        current = await presence.get_presence(
                            # we need user_id. We'll have to store user_id in members map.
                            # I'll fix the members map to store (websocket, session)
                            None
                        )
                except Exception as e:
                    print(f"Error processing broadcast: {e}")