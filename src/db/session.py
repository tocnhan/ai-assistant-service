# src/db/session.py
import asyncpg
import asyncio
import structlog
from contextlib import asynccontextmanager
from src.core.config import settings

logger = structlog.get_logger()

class DatabasePool:
    _pool: asyncpg.Pool = None

    @classmethod
    async def init(cls, retries: int = 10, delay: float = 3.0):
        dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        
        for attempt in range(1, retries + 1):
            try:
                cls._pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=5,
                    max_size=20,
                    command_timeout=30,
                )
                logger.info("db.connected", attempt=attempt)
                return
            except Exception as e:
                logger.warning("db.connecting", attempt=attempt, retries=retries, error=str(e))
                if attempt == retries:
                    logger.error("db.failed", error=str(e))
                    raise
                await asyncio.sleep(delay)

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()

    @classmethod
    @asynccontextmanager
    async def acquire_with_tenant(cls, company_guid: str):
        async with cls._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"SET LOCAL app.current_tenant = '{company_guid}'"
                )
                yield conn