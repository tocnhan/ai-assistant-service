"""007_sprint7_credit_wallet

Revision ID: 9d9c0f8331ef
Revises: d365ee120fbf
Create Date: 2026-05-29 20:11:10.340157

"""
from typing import Sequence, Union
from alembic import op

revision: str = '9d9c0f8331ef'
down_revision: Union[str, Sequence[str], None] = 'd365ee120fbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        -- 1. tenant_wallets
        CREATE TABLE ai_service.tenant_wallets (
            id              SERIAL PRIMARY KEY,
            company_guid    UUID NOT NULL UNIQUE
                REFERENCES ai_service.tenants(company_guid) ON DELETE CASCADE,
            balance         NUMERIC(12, 4) NOT NULL DEFAULT 0,
            monthly_grant   NUMERIC(12, 4) NOT NULL DEFAULT 0,
            markup_rate     NUMERIC(4, 2)  NOT NULL DEFAULT 1.5,
            is_hard_stop    BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );

        -- 2. credit_packages
        CREATE TABLE ai_service.credit_packages (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR(128) NOT NULL UNIQUE,
            credits         NUMERIC(12, 4) NOT NULL,
            price_usd       NUMERIC(10, 2) NOT NULL,
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );

        -- 3. credit_transactions — hypertable
        CREATE TABLE ai_service.credit_transactions (
            id              BIGSERIAL,
            company_guid    UUID NOT NULL
                REFERENCES ai_service.tenants(company_guid) ON DELETE CASCADE,
            amount          NUMERIC(12, 4) NOT NULL,
            balance_after   NUMERIC(12, 4) NOT NULL,
            tx_type         VARCHAR(32) NOT NULL,
            ref_id          UUID,
            note            TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        );

        SELECT create_hypertable(
            'ai_service.credit_transactions',
            'created_at',
            chunk_time_interval => INTERVAL '7 days'
        );

        -- 4. Index
        CREATE INDEX idx_tenant_wallets_guid
            ON ai_service.tenant_wallets(company_guid);

        CREATE INDEX idx_credit_transactions_guid
            ON ai_service.credit_transactions(company_guid, created_at DESC);

        -- 5. RLS
        ALTER TABLE ai_service.tenant_wallets ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.tenant_wallets FORCE ROW LEVEL SECURITY;

        CREATE POLICY tenant_isolation ON ai_service.tenant_wallets
            USING (company_guid = current_setting('app.current_tenant', TRUE)::UUID);

        ALTER TABLE ai_service.credit_transactions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.credit_transactions FORCE ROW LEVEL SECURITY;

        CREATE POLICY tenant_isolation ON ai_service.credit_transactions
            USING (company_guid = current_setting('app.current_tenant', TRUE)::UUID);

        -- 6. Grants
        GRANT SELECT, INSERT, UPDATE    ON ai_service.tenant_wallets       TO ai_app;
        GRANT SELECT, INSERT            ON ai_service.credit_transactions  TO ai_app;
        GRANT SELECT                    ON ai_service.credit_packages      TO ai_app;
        GRANT ALL                       ON ai_service.tenant_wallets       TO ai_admin;
        GRANT ALL                       ON ai_service.credit_transactions  TO ai_admin;
        GRANT ALL                       ON ai_service.credit_packages      TO ai_admin;
        GRANT USAGE, SELECT ON SEQUENCE ai_service.tenant_wallets_id_seq      TO ai_app;
        GRANT USAGE, SELECT ON SEQUENCE ai_service.credit_packages_id_seq     TO ai_app;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS ai_service.credit_transactions;
        DROP TABLE IF EXISTS ai_service.tenant_wallets;
        DROP TABLE IF EXISTS ai_service.credit_packages;
    """)