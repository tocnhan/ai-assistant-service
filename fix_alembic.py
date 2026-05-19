import asyncio, asyncpg, sys
sys.path.insert(0, '.')
from src.core.config import settings

async def fix():
    conn = await asyncpg.connect(settings.DATABASE_ADMIN_URL)
    await conn.execute("UPDATE alembic_version SET version_num = '0689772182af' WHERE version_num = 'sprint3_xxx'")
    current = await conn.fetchval('SELECT version_num FROM alembic_version')
    print('current revision:', current)
    await conn.close()

asyncio.run(fix())
