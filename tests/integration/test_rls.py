import pytest
from uuid import uuid4
from src.db.session import DatabasePool

@pytest.fixture(autouse=True)
async def setup_pool():
    await DatabasePool.init()
    yield
    await DatabasePool.close()

@pytest.mark.asyncio
async def test_rls_prevents_cross_tenant_read():
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())

    # Insert tenant_a vào tenants trước (dùng pool trực tiếp, bypass RLS)
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ai_service.tenants (company_guid, domain, plan)
            VALUES ($1, 'https://tenant-a.com', 'free')
        """, tenant_a)

    # Tenant A insert usage log
    async with DatabasePool.acquire_with_tenant(tenant_a) as conn:
        await conn.execute("""
            INSERT INTO ai_service.llm_usage_log
              (company_guid, agent_name, provider, model, total_tokens, estimated_cost_usd)
            VALUES ($1, 'task', 'gemini', 'flash', 100, 0.001)
        """, tenant_a)

    # Tenant B cố đọc → phải thấy 0 rows
    async with DatabasePool.acquire_with_tenant(tenant_b) as conn:
        rows = await conn.fetch("SELECT * FROM ai_service.llm_usage_log")
        assert len(rows) == 0, "RLS FAILED: tenant B đọc được data tenant A!"

    # Tenant A đọc lại → thấy đúng 1 row
    async with DatabasePool.acquire_with_tenant(tenant_a) as conn:
        rows = await conn.fetch("SELECT * FROM ai_service.llm_usage_log")
        assert len(rows) == 1