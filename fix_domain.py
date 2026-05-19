import asyncio, asyncpg, sys
sys.path.insert(0, '.')
from src.core.config import settings

async def fix():
    conn = await asyncpg.connect(settings.DATABASE_ADMIN_URL)
    await conn.execute(
        "INSERT INTO ai_service.allowed_domains (company_guid, domain, is_active) VALUES ($1, $2, TRUE)",
        '550e8400-e29b-41d4-a716-446655440000', 'https://allowed-shop.com'
    )
    print('done')
    await conn.close()

asyncio.run(fix())