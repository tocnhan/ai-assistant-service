# src/memory/conversation.py
import json
from src.cache.redis_client import get_redis

WINDOW_SIZE = 10   # giữ 10 turn gần nhất
TTL_SECONDS = 86400  # 24h


class ConversationMemory:
    def __init__(self, company_guid: str):
        self.company_guid = company_guid

    def _key(self, conversation_id: str) -> str:
        return f"conv:{self.company_guid}:{conversation_id}"

    async def get(self, conversation_id: str) -> list[dict]:
        """Lấy toàn bộ history, trả về list messages."""
        redis = get_redis()
        raw = await redis.lrange(self._key(conversation_id), 0, -1)
        return [json.loads(item) for item in raw]

    async def append(self, conversation_id: str, role: str, content: str):
        """Thêm 1 turn, tự trim nếu vượt WINDOW_SIZE."""
        redis = get_redis()
        key = self._key(conversation_id)
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)

        pipe = redis.pipeline()
        pipe.rpush(key, message)
        # Giữ đúng WINDOW_SIZE turn (mỗi turn = 2 message: user + assistant)
        pipe.ltrim(key, -(WINDOW_SIZE * 2), -1)
        pipe.expire(key, TTL_SECONDS)
        await pipe.execute()

    async def clear(self, conversation_id: str):
        redis = get_redis()
        await redis.delete(self._key(conversation_id))