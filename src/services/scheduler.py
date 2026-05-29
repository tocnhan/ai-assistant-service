# src/services/scheduler.py
"""
Background jobs cho wallet:
- monthly_grant_job: cấp credit hàng tháng cho tất cả tenant
- reconcile_job: đối soát credit_transactions vs llm_usage_log mỗi giờ
Chạy qua apscheduler, khởi động trong lifespan.
"""
import logging
from decimal import Decimal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.db.session import DatabasePool
from src.services.wallet import WalletService

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def monthly_grant_job():
    """Cấp monthly grant cho tất cả tenant có monthly_grant > 0."""
    logger.info("Running monthly grant job...")
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT company_guid FROM ai_service.tenant_wallets
            WHERE monthly_grant > 0
        """)

    success, failed = 0, 0
    for row in rows:
        try:
            async with DatabasePool._pool.acquire() as conn:
                wallet = WalletService(conn)
                await wallet.grant_monthly(row["company_guid"])
            success += 1
        except Exception as e:
            logger.error(f"Grant failed for {row['company_guid']}: {e}")
            failed += 1

    logger.info(f"Monthly grant done — success={success}, failed={failed}")


async def reconcile_job():
    """
    Đối soát: tổng debit trong credit_transactions
    phải khớp với tổng cost trong llm_usage_log.
    Log warning nếu lệch > $0.01.
    """
    logger.info("Running reconcile job...")
    async with DatabasePool._pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH wallet_debits AS (
                SELECT
                    company_guid,
                    SUM(ABS(amount)) AS total_debited
                FROM ai_service.credit_transactions
                WHERE tx_type = 'debit'
                  AND created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY company_guid
            ),
            usage_costs AS (
                SELECT
                    company_guid,
                    SUM(estimated_cost_usd) * 100 AS total_cost_credits
                FROM ai_service.llm_usage_log
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY company_guid
            )
            SELECT
                w.company_guid,
                w.total_debited,
                u.total_cost_credits,
                ABS(w.total_debited - u.total_cost_credits) AS diff
            FROM wallet_debits w
            JOIN usage_costs u USING (company_guid)
            WHERE ABS(w.total_debited - u.total_cost_credits) > 1
        """)

    for row in rows:
        logger.warning(
            f"Reconcile mismatch — tenant={row['company_guid']} "
            f"debited={row['total_debited']} "
            f"cost={row['total_cost_credits']} "
            f"diff={row['diff']}"
        )

    logger.info(f"Reconcile done — {len(rows)} mismatch(es) found")


def start_scheduler():
    scheduler.add_job(
        monthly_grant_job,
        trigger="cron",
        day=1, hour=0, minute=0,  # mùng 1 hàng tháng lúc 00:00
        id="monthly_grant",
    )
    scheduler.add_job(
        reconcile_job,
        trigger="interval",
        hours=1,
        id="reconcile",
    )
    scheduler.start()
    logger.info("Scheduler started — monthly_grant + reconcile jobs registered")


def stop_scheduler():
    scheduler.shutdown()