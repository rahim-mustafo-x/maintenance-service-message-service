import asyncio
from typing import Dict, Any
from model import Session
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
        """
        Publishes a message to the global Redis broadcast channel.
        """
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
        """
        Background task to listen for messages and session invalidations.
        """
        while True:
            try:
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
                            for session_id, member in list(self.members.items()):
                                # Check presence of each local member
                                current = await presence.get_presence(
                                    # The member tuple is (websocket, session)
                                    member[1].user_id if hasattr(member[1], 'user_id') else None
                                )
                                if current and current.chat_id == chat_id:
                                    await member[0].send_text(json.dumps({
                                        "type": "MESSAGE",
                                        "payload": {
                                            "text": msg_text,
                                            "who_sent": "other"
                                        }
                                    }))
                        except Exception as e:
                            print(f"Error processing broadcast: {e}")
            except Exception as e:
                print(f"Redis connection lost in listener: {e}. Retrying in 5s...")
                await asyncio.sleep(5)