import asyncio
import os
import asyncpg
import asyncio, asyncpg, sys
sys.path.insert(0, '.')
from src.core.config import settings

async def check():
    conn = await asyncpg.connect(settings.DATABASE_ADMIN_URL)
    rows = await conn.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'ai_service'
        AND table_name IN ('tool_definitions', 'tenant_tool_configs')
    """)
    for r in rows:
        print(r['table_name'])
    await conn.close()

asyncio.run(check())