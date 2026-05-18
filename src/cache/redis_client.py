# src/cache/redis_client.py
import redis.asyncio as aioredis
import structlog
from src.core.config import settings

logger = structlog.get_logger()

redis: aioredis.Redis = None

async def init_redis():
    global redis
    redis = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    # Ping để verify connection ngay khi startup
    await redis.ping()
    logger.info("redis.connected", url=settings.REDIS_URL)

async def close_redis():
    global redis
    if redis:
        await redis.aclose()