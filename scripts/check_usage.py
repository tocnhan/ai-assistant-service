import asyncio, asyncpg, sys
sys.path.insert(0, '.')
from src.core.config import settings

async def check():
    conn = await asyncpg.connect(settings.DATABASE_ADMIN_URL)

    rows = await conn.fetch("""
        SELECT
            provider,
            model,
            COUNT(*) as requests,
            SUM(prompt_tokens) as total_prompt,
            SUM(output_tokens) as total_output,
            SUM(total_tokens) as total_tokens,
            ROUND(SUM(estimated_cost_usd)::numeric, 6) as total_cost_usd
        FROM ai_service.llm_usage_log
        GROUP BY provider, model
        ORDER BY total_cost_usd DESC
    """)
    for r in rows:
        print(f"  {r['provider']}/{r['model']}")
        print(f"    requests : {r['requests']}")
        print(f"    tokens   : {r['total_tokens']} (prompt={r['total_prompt']}, output={r['total_output']})")
        print(f"    cost     : ${r['total_cost_usd']}")

    rows = await conn.fetch("""
        SELECT
            company_guid,
            COUNT(*) as requests,
            SUM(total_tokens) as total_tokens,
            ROUND(SUM(estimated_cost_usd)::numeric, 6) as total_cost_usd
        FROM ai_service.llm_usage_log
        GROUP BY company_guid
        ORDER BY total_cost_usd DESC
    """)
    for r in rows:
        print(f"  {r['company_guid']}: {r['requests']} reqs, {r['total_tokens']} tokens, ${r['total_cost_usd']}")

    rows = await conn.fetch("""
        SELECT
            created_at,
            provider,
            model,
            prompt_tokens,
            output_tokens,
            total_tokens,
            ROUND(estimated_cost_usd::numeric, 6) as cost_usd,
            latency_ms
        FROM ai_service.llm_usage_log
        ORDER BY created_at DESC
        LIMIT 10
    """)
    for r in rows:
        print(f"  {r['created_at'].strftime('%H:%M:%S')} | {r['provider']}/{r['model']} | {r['total_tokens']} tokens | ${r['cost_usd']} | {r['latency_ms']}ms")

    await conn.close()

asyncio.run(check())
