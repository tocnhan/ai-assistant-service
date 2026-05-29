# src/services/wallet_gate.py
"""
WalletGate — check balance trước LLM call, debit sau.
Thay thế QuotaManager cũ.
"""
from decimal import Decimal
from uuid import UUID
import logging
from src.services.wallet import WalletService, InsufficientBalanceError
from src.db.session import DatabasePool

logger = logging.getLogger(__name__)


class WalletGate:

    @staticmethod
    async def check(company_guid: UUID) -> bool:
        """
        Kiểm tra balance trước khi cho phép LLM call.
        Return False nếu hết credit và is_hard_stop=True.
        """
        async with DatabasePool._pool.acquire() as conn:
            try:
                wallet = WalletService(conn)
                balance = await wallet.check_balance(company_guid)
                return balance > Decimal("0")
            except ValueError:
                # Wallet chưa tạo → tạo mới với balance 0
                logger.warning(f"Wallet not found for {company_guid}, creating...")
                await WalletGate._create_wallet(company_guid)
                return False

    @staticmethod
    async def debit_after_call(
        company_guid: UUID,
        cost_usd: float,
        ref_id: UUID | None = None,
        note: str | None = None,
    ) -> None:
        """
        Trừ credit sau khi LLM call xong.
        Không raise — log lỗi thay vì crash request.
        """
        async with DatabasePool._pool.acquire() as conn:
            try:
                wallet = WalletService(conn)
                await wallet.debit(
                    company_guid=company_guid,
                    cost_usd=Decimal(str(cost_usd)),
                    ref_id=ref_id,
                    note=note,
                )
            except InsufficientBalanceError:
                logger.warning(
                    f"Debit failed — insufficient balance for {company_guid}"
                )
            except Exception as e:
                logger.error(f"Wallet debit error for {company_guid}: {e}")

    @staticmethod
    async def _create_wallet(company_guid: UUID) -> None:
        """Auto-create wallet khi tenant chưa có."""
        async with DatabasePool._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ai_service.tenant_wallets (company_guid)
                VALUES ($1)
                ON CONFLICT (company_guid) DO NOTHING
            """, str(company_guid))