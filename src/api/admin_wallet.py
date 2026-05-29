# src/api/admin_wallet.py
"""
Admin wallet endpoints:
- GET  /admin/tenants/{guid}/wallet        — xem wallet
- POST /admin/tenants/{guid}/wallet/topup  — top-up credit
- POST /admin/tenants/{guid}/wallet/grant  — manual monthly grant
- GET  /admin/tenants/{guid}/usage         — usage + cost 30 ngày
- GET  /admin/usage/anomalies              — tenant tăng đột biến > 3x baseline
"""
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncpg
from src.core.config import settings
from src.services.wallet import WalletService
from src.db.session import DatabasePool

router = APIRouter(prefix="/admin", tags=["admin-wallet"])


class TopupRequest(BaseModel):
    credits: Decimal
    note: str | None = None


# ─── GET wallet ───────────────────────────────────────────────
@router.get("/tenants/{company_guid}/wallet")
async def get_wallet(company_guid: UUID):
    async with DatabasePool._pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT balance, monthly_grant, markup_rate, is_hard_stop, updated_at
            FROM ai_service.tenant_wallets
            WHERE company_guid = $1
        """, str(company_guid))

    if not row:
        raise HTTPException(404, detail="Wallet not found")

    return dict(row)


# ─── POST topup ───────────────────────────────────────────────
@router.post("/tenants/{company_guid}/wallet/topup")
async def topup_wallet(company_guid: UUID, body: TopupRequest):
    async with DatabasePool._pool.acquire() as conn:
        wallet = WalletService(conn)
        try:
            new_balance = await wallet.credit(
                company_guid=company_guid,
                amount=body.credits,
                tx_type="topup",
                note=body.note,
            )
        except ValueError as e:
            raise HTTPException(404, detail=str(e))

    return {"company_guid": str(company_guid), "new_balance": new_balance}


# ─── POST manual grant ────────────────────────────────────────
@router.post("/tenants/{company_guid}/wallet/grant")
async def manual_grant(company_guid: UUID):
    async with DatabasePool._pool.acquire() as conn:
        wallet = WalletService(conn)
        try:
            new_balance = await wallet.grant_monthly(company_guid)
        except ValueError as e:
            raise HTTPException(404, detail=str(e))

    return {"company_guid": str(company_guid), "new_balance": new_balance}


# ─── GET usage 30 ngày ────────────────────────────────────────
@router.get("/tenants/{company_guid}/usage")
async def get_usage(company_guid: UUID):
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                DATE_TRUNC('day', created_at) AS day,
                COUNT(*)                       AS total_calls,
                SUM(total_tokens)              AS total_tokens,
                SUM(estimated_cost_usd)        AS total_cost_usd
            FROM ai_service.llm_usage_log
            WHERE company_guid = $1
              AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY 1
            ORDER BY 1 DESC
        """, str(company_guid))

    return [dict(r) for r in rows]


# ─── GET anomalies ────────────────────────────────────────────
@router.get("/usage/anomalies")
async def get_anomalies():
    """
    Tenant nào có cost hôm nay > 3x baseline (avg 7 ngày trước).
    """
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH daily AS (
                SELECT
                    company_guid,
                    DATE_TRUNC('day', created_at) AS day,
                    SUM(estimated_cost_usd) AS cost
                FROM ai_service.llm_usage_log
                WHERE created_at >= NOW() - INTERVAL '8 days'
                GROUP BY 1, 2
            ),
            baseline AS (
                SELECT company_guid, AVG(cost) AS avg_cost
                FROM daily
                WHERE day < DATE_TRUNC('day', NOW())
                GROUP BY 1
            ),
            today AS (
                SELECT company_guid, cost AS today_cost
                FROM daily
                WHERE day = DATE_TRUNC('day', NOW())
            )
            SELECT
                t.company_guid,
                t.today_cost,
                b.avg_cost AS baseline_cost,
                ROUND(t.today_cost / NULLIF(b.avg_cost, 0), 2) AS ratio
            FROM today t
            JOIN baseline b USING (company_guid)
            WHERE t.today_cost > b.avg_cost * 3
            ORDER BY ratio DESC
        """)

    return [dict(r) for r in rows]