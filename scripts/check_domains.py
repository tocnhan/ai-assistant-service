import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def check():
    dsn = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(dsn)
    rows = await conn.fetch("""
        SELECT company_guid, domain, is_active 
        FROM ai_service.allowed_domains 
        WHERE company_guid = '550e8400-e29b-41d4-a716-446655440000'
    """)
    for r in rows:
        print(dict(r))
    await conn.close()

asyncio.run(check())