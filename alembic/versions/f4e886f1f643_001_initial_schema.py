"""001_initial_schema

Revision ID: f4e886f1f643
Revises: 
Create Date: 2026-05-18 15:13:33.322124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4e886f1f643'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        CREATE SCHEMA IF NOT EXISTS ai_service;
    """)

    op.execute("""
        CREATE TABLE ai_service.tenants (
          company_guid    UUID PRIMARY KEY,
          domain          VARCHAR(255) NOT NULL,
          display_name    VARCHAR(255),
          plan            VARCHAR(32) NOT NULL DEFAULT 'free',
          status          VARCHAR(32) NOT NULL DEFAULT 'active',
          metadata        JSONB DEFAULT '{}',
          created_at      TIMESTAMPTZ DEFAULT NOW(),
          updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE TABLE ai_service.tenant_quotas (
          company_guid           UUID PRIMARY KEY REFERENCES ai_service.tenants(company_guid),
          monthly_token_limit    BIGINT,
          monthly_cost_limit_usd NUMERIC(10,2),
          daily_request_limit    INT,
          current_month_tokens   BIGINT DEFAULT 0,
          current_month_cost_usd NUMERIC(10,2) DEFAULT 0,
          current_day_requests   INT DEFAULT 0,
          reset_month_at         TIMESTAMPTZ,
          reset_day_at           TIMESTAMPTZ,
          hard_limit             BOOLEAN DEFAULT TRUE,
          updated_at             TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE TABLE ai_service.conversations (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          company_guid    UUID NOT NULL REFERENCES ai_service.tenants(company_guid),
          user_guid       UUID NOT NULL,
          title           VARCHAR(255),
          total_messages  INT DEFAULT 0,
          total_cost_usd  NUMERIC(10,4) DEFAULT 0,
          created_at      TIMESTAMPTZ DEFAULT NOW(),
          last_message_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE TABLE ai_service.llm_usage_log (
          id                  BIGSERIAL,
          created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          company_guid        UUID NOT NULL,
          user_guid           UUID,
          conversation_id     UUID,
          request_id          UUID,
          agent_name          VARCHAR(64) NOT NULL,
          provider            VARCHAR(32) NOT NULL,
          model               VARCHAR(128) NOT NULL,
          prompt_tokens       INT NOT NULL DEFAULT 0,
          output_tokens       INT NOT NULL DEFAULT 0,
          cached_tokens       INT NOT NULL DEFAULT 0,
          thoughts_tokens     INT NOT NULL DEFAULT 0,
          tool_tokens         INT NOT NULL DEFAULT 0,
          total_tokens        INT NOT NULL DEFAULT 0,
          estimated_cost_usd  NUMERIC(10,6) NOT NULL DEFAULT 0,
          latency_ms          INT,
          success             BOOLEAN DEFAULT TRUE,
          error_code          VARCHAR(64),
          PRIMARY KEY (id, created_at)
        );
        SELECT create_hypertable('ai_service.llm_usage_log', 'created_at',
                                 chunk_time_interval => INTERVAL '7 days');
    """)

    op.execute("""
        CREATE TABLE ai_service.audit_log (
          id              BIGSERIAL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          company_guid    UUID,
          user_guid       UUID,
          event_type      VARCHAR(64) NOT NULL,
          severity        VARCHAR(16),
          details         JSONB,
          ip_address      INET,
          PRIMARY KEY (id, created_at)
        );
        SELECT create_hypertable('ai_service.audit_log', 'created_at',
                                 chunk_time_interval => INTERVAL '30 days');
    """)

    op.execute("""
        CREATE TABLE ai_service.model_pricing (
          id                          SERIAL PRIMARY KEY,
          provider                    VARCHAR(32) NOT NULL,
          model                       VARCHAR(128) NOT NULL,
          effective_from              DATE NOT NULL,
          effective_to                DATE,
          input_price_per_million     NUMERIC(10,6) NOT NULL,
          output_price_per_million    NUMERIC(10,6) NOT NULL,
          cached_price_per_million    NUMERIC(10,6),
          notes                       TEXT,
          UNIQUE (provider, model, effective_from)
        );
    """)

    op.execute("""
        ALTER TABLE ai_service.conversations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.conversations FORCE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.llm_usage_log ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.llm_usage_log FORCE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.tenant_quotas  ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.tenant_quotas  FORCE ROW LEVEL SECURITY;

        CREATE POLICY tenant_isolation ON ai_service.conversations
          USING      (company_guid = current_setting('app.current_tenant')::UUID)
          WITH CHECK (company_guid = current_setting('app.current_tenant')::UUID);

        CREATE POLICY tenant_isolation ON ai_service.llm_usage_log
          USING      (company_guid = current_setting('app.current_tenant')::UUID)
          WITH CHECK (company_guid = current_setting('app.current_tenant')::UUID);

        CREATE POLICY tenant_isolation ON ai_service.tenant_quotas
          USING      (company_guid = current_setting('app.current_tenant')::UUID)
          WITH CHECK (company_guid = current_setting('app.current_tenant')::UUID);
    """)

    op.execute("""
        GRANT USAGE ON SCHEMA ai_service TO ai_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ai_service TO ai_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ai_service TO ai_app;
        GRANT ALL ON ALL TABLES IN SCHEMA ai_service TO ai_admin;
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA ai_service CASCADE;")
