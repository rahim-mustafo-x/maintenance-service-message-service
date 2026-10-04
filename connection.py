from redis import Redis
from config import REDIS_HOST, REDIS_PORT
from model import Session
from json import loads
from typing import Optional

redis = Redis(
    host=REDIS_HOST, port=REDIS_PORT
)

class Presence:
    @staticmethod
    def _key(user_id) -> str:
        return f'user:{user_id}'
    async def set_presence(self, session:Session):
        await redis.set(
            self._key(session.user_id),
            session.model_dump_json(),
            ex=session.time_to_live
        )
    async def get_presence(self, user_id) -> Optional[Session]:
        raw_data = await redis.get(self._key(user_id))
        if raw_data:
            return loads(raw_data)
        else:
            return None
    async def delete_presence(self, user_id):
        await redis.delete(self._key(user_id))