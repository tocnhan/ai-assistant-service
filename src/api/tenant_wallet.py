# src/api/tenant_wallet.py
"""
Tenant wallet endpoints (tenant tự xem, không sửa được):
- GET /tenant/wallet        — xem balance + monthly_grant
- GET /tenant/usage         — usage 30 ngày của chính tenant
- GET /tenant/transactions  — lịch sử credit transactions 30 ngày
"""
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException
from src.db.session import DatabasePool

router = APIRouter(prefix="/tenant", tags=["tenant-wallet"])


# ─── GET wallet ───────────────────────────────────────────────
@router.get("/wallet")
async def get_my_wallet(x_company_guid: UUID = Header(...)):
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, TRUE)",
            str(x_company_guid)
        )
        row = await conn.fetchrow("""
            SELECT balance, monthly_grant, markup_rate, updated_at
            FROM ai_service.tenant_wallets
            WHERE company_guid = $1
        """, str(x_company_guid))

    if not row:
        raise HTTPException(404, detail="Wallet not found")

    wallet = dict(row)
    wallet["balance_display"] = f"{wallet['balance']:.0f} credits"

    return wallet


# ─── GET usage 30 ngày ────────────────────────────────────────
@router.get("/usage")
async def get_my_usage(x_company_guid: UUID = Header(...)):
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, TRUE)",
            str(x_company_guid)
        )
        rows = await conn.fetch("""
            SELECT
                DATE_TRUNC('day', created_at) AS day,
                agent_name,
                provider,
                model,
                COUNT(*)                       AS total_calls,
                SUM(total_tokens)              AS total_tokens,
                SUM(estimated_cost_usd)        AS total_cost_usd
            FROM ai_service.llm_usage_log
            WHERE company_guid = $1
              AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY 1, 2, 3, 4
            ORDER BY 1 DESC
        """, str(x_company_guid))

    return [dict(r) for r in rows]


# ─── GET transactions 30 ngày ─────────────────────────────────
@router.get("/transactions")
async def get_my_transactions(x_company_guid: UUID = Header(...)):
    async with DatabasePool._pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, TRUE)",
            str(x_company_guid)
        )
        rows = await conn.fetch("""
            SELECT
                id,
                amount,
                balance_after,
                tx_type,
                note,
                created_at
            FROM ai_service.credit_transactions
            WHERE company_guid = $1
              AND created_at >= NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC
            LIMIT 100
        """, str(x_company_guid))

    return [dict(r) for r in rows]