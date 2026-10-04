from typing import Optional

from redis.asyncio import Redis

from config import REDIS_HOST, REDIS_PORT
from model import Session


redis = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)


class Presence:

    @staticmethod
    def _key(user_id: int) -> str:
        return f"user:{user_id}:session"

    async def set_presence(
        self,
        session: Session
    ) -> None:

        await redis.set(
            self._key(session.user_id),
            session.model_dump_json(),
            ex=session.time_to_live
        )

    async def get_presence(
        self,
        user_id: int
    ) -> Optional[Session]:

        raw_data = await redis.get(
            self._key(user_id)
        )

        if raw_data is None:
            return None

        return Session.model_validate_json(
            raw_data
        )

    async def refresh_presence(
        self,
        session: Session
    ) -> bool:

        return bool(
            await redis.expire(
                self._key(session.user_id),
                session.time_to_live
            )
        )

    async def delete_presence(
        self,
        user_id: int
    ) -> None:

        await redis.delete(
            self._key(user_id)
        )

    async def delete_if_current(
        self,
        session: Session
    ) -> bool:

        current = await self.get_presence(
            session.user_id
        )

        if current is None:
            return False

        if current.session_id != session.session_id:
            return False

        await self.delete_presence(
            session.user_id
        )

        return True