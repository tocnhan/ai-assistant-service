# scripts/seed_test_data.py
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncpg
from src.core.config import settings

async def seed():
    dsn = settings.DATABASE_ADMIN_URL
    conn = await asyncpg.connect(dsn)
    await conn.execute("""
        INSERT INTO ai_service.tenants (company_guid, domain, plan)
        VALUES ('550e8400-e29b-41d4-a716-446655440000', 'https://test.com', 'free')
        ON CONFLICT DO NOTHING;
    """)
    await conn.close()

asyncio.run(seed())