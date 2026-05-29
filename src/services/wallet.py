# src/services/wallet.py
"""
Credit Wallet Service
- check_balance: kiểm tra balance hiện tại
- debit: trừ credit sau LLM call (atomic, chống race condition)
- credit: cộng credit (topup / refund)
- grant_monthly: cấp monthly grant theo plan
"""
from decimal import Decimal
from uuid import UUID
import asyncpg
from src.core.config import settings


CREDIT_PER_USD = Decimal("100")  # 1 credit = $0.01


class InsufficientBalanceError(Exception):
    pass


class WalletService:

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def get_wallet(self, company_guid: UUID) -> dict:
        row = await self.conn.fetchrow("""
            SELECT balance, monthly_grant, markup_rate, is_hard_stop
            FROM ai_service.tenant_wallets
            WHERE company_guid = $1
        """, str(company_guid))
        if not row:
            raise ValueError(f"Wallet not found for tenant {company_guid}")
        return dict(row)

    async def check_balance(self, company_guid: UUID) -> Decimal:
        wallet = await self.get_wallet(company_guid)
        return Decimal(str(wallet["balance"]))

    async def debit(
        self,
        company_guid: UUID,
        cost_usd: Decimal,
        ref_id: UUID | None = None,
        note: str | None = None,
    ) -> Decimal:
        """
        Trừ credit sau LLM call.
        Atomic qua FOR UPDATE — chống race condition concurrent request.
        Raise InsufficientBalanceError nếu is_hard_stop=True và balance < amount.
        """
        amount = (cost_usd * CREDIT_PER_USD).quantize(Decimal("0.0001"))

        async with self.conn.transaction():
            row = await self.conn.fetchrow("""
                SELECT balance, markup_rate, is_hard_stop
                FROM ai_service.tenant_wallets
                WHERE company_guid = $1
                FOR UPDATE
            """, str(company_guid))

            if not row:
                raise ValueError(f"Wallet not found for tenant {company_guid}")

            markup = Decimal(str(row["markup_rate"]))
            charged = (amount * markup).quantize(Decimal("0.0001"))
            balance = Decimal(str(row["balance"]))

            if row["is_hard_stop"] and balance < charged:
                raise InsufficientBalanceError(
                    f"Insufficient balance: {balance} < {charged}"
                )

            new_balance = balance - charged
            await self.conn.execute("""
                UPDATE ai_service.tenant_wallets
                SET balance = $1, updated_at = NOW()
                WHERE company_guid = $2
            """, float(new_balance), str(company_guid))

            await self.conn.execute("""
                INSERT INTO ai_service.credit_transactions
                    (company_guid, amount, balance_after, tx_type, ref_id, note)
                VALUES ($1, $2, $3, 'debit', $4, $5)
            """, str(company_guid), float(-charged), float(new_balance),
                str(ref_id) if ref_id else None, note)

        return new_balance

    async def credit(
        self,
        company_guid: UUID,
        amount: Decimal,
        tx_type: str = "topup",
        ref_id: UUID | None = None,
        note: str | None = None,
    ) -> Decimal:
        """Cộng credit — topup hoặc refund."""
        async with self.conn.transaction():
            row = await self.conn.fetchrow("""
                SELECT balance FROM ai_service.tenant_wallets
                WHERE company_guid = $1
                FOR UPDATE
            """, str(company_guid))

            if not row:
                raise ValueError(f"Wallet not found for tenant {company_guid}")

            new_balance = Decimal(str(row["balance"])) + amount
            await self.conn.execute("""
                UPDATE ai_service.tenant_wallets
                SET balance = $1, updated_at = NOW()
                WHERE company_guid = $2
            """, float(new_balance), str(company_guid))

            await self.conn.execute("""
                INSERT INTO ai_service.credit_transactions
                    (company_guid, amount, balance_after, tx_type, ref_id, note)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, str(company_guid), float(amount), float(new_balance),
                tx_type, str(ref_id) if ref_id else None, note)

        return new_balance

    async def grant_monthly(self, company_guid: UUID) -> Decimal:
        """Cấp monthly grant theo plan — gọi bởi background job."""
        row = await self.conn.fetchrow("""
            SELECT monthly_grant FROM ai_service.tenant_wallets
            WHERE company_guid = $1
        """, str(company_guid))

        if not row or row["monthly_grant"] == 0:
            return Decimal("0")

        return await self.credit(
            company_guid,
            amount=Decimal(str(row["monthly_grant"])),
            tx_type="monthly_grant",
            note="Monthly grant",
        )