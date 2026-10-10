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

    @staticmethod
    def _invalidation_channel() -> str:
        return "sessions:invalidation"

    async def set_presence(
        self,
        session: Session
    ) -> None:
        try:
            await redis.set(
                self._key(session.user_id),
                session.model_dump_json(),
                ex=session.time_to_live
            )
        except Exception as e:
            print(f"Redis Error (set_presence): {e}")

    async def claim_session(
        self,
        session: Session
    ) -> tuple[bool, bool]:
        """
        Claims session ownership.
        Returns (success, superseded_old_session).
        """
        try:
            user_key = self._key(session.user_id)
            old_data = await redis.get(user_key)

            # If already owned by this session, just refresh
            if old_data:
                old_session = Session.model_validate_json(old_data)
                if old_session.session_id == session.session_id:
                    await redis.expire(user_key, session.time_to_live)
                    return True, False

            # Claim the session
            await redis.set(
                user_key,
                session.model_dump_json(),
                ex=session.time_to_live
            )

            superseded = False
            if old_data:
                superseded = True
                # Notify other instances to close the old session
                await redis.publish(
                    self._invalidation_channel(),
                    old_data
                )

            return True, superseded
        except Exception as e:
            print(f"Redis Error (claim_session): {e}")
            return False, False

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
        """
        Refreshes TTL only if this session still owns the presence.
        """
        user_key = self._key(session.user_id)
        current = await self.get_presence(session.user_id)

        if current and current.session_id == session.session_id:
            return bool(
                await redis.expire(
                    user_key,
                    session.time_to_live
                )
            )
        return False

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