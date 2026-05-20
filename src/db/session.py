# src/db/session.py
import asyncpg
from contextlib import asynccontextmanager
from src.core.config import settings

class DatabasePool:
    _pool: asyncpg.Pool = None

    @classmethod
    async def init(cls):
        # asyncpg dùng postgresql:// không phải postgresql+asyncpg://
        dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        cls._pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=5,
            max_size=20,
            command_timeout=30,
        )

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
                    "SELECT set_config('app.current_tenant', $1, TRUE)",
                    company_guid,
                )
                yield conn