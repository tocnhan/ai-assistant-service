"""006_sprint6_tool_plugin

Revision ID: d365ee120fbf
Revises: 5228d1a84c24
Create Date: 2026-05-27 10:06:49.169138

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd365ee120fbf'
down_revision: Union[str, Sequence[str], None] = '5228d1a84c24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        -- 1. tool_definitions
        --    Global registry — code plugin nằm trên filesystem,
        --    DB chỉ chứa metadata + schema. KHÔNG lưu code Python vào DB.
        CREATE TABLE ai_service.tool_definitions (
            id              SERIAL PRIMARY KEY,
            tool_name       VARCHAR(128) NOT NULL UNIQUE,
            display_name    VARCHAR(128),
            description     TEXT,
            plugin_class    VARCHAR(256) NOT NULL,
            config_schema   JSONB NOT NULL DEFAULT '{}',
            input_schema    JSONB NOT NULL DEFAULT '{}',
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );

        -- 2. tenant_tool_configs
        --    Config per-tenant cho từng tool.
        --    Cùng plugin http_api_call, tenant du lịch trỏ booking API,
        --    tenant F&B trỏ POS API — chỉ khác config, không khác code.
        CREATE TABLE ai_service.tenant_tool_configs (
            id              SERIAL PRIMARY KEY,
            company_guid    UUID NOT NULL
                REFERENCES ai_service.tenants(company_guid) ON DELETE CASCADE,
            tool_name       VARCHAR(128) NOT NULL
                REFERENCES ai_service.tool_definitions(tool_name) ON DELETE CASCADE,
            is_enabled      BOOLEAN DEFAULT TRUE,
            config          JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_guid, tool_name)
        );

        -- 3. Index
        CREATE INDEX idx_tenant_tool_configs_guid
            ON ai_service.tenant_tool_configs(company_guid);

        CREATE INDEX idx_tenant_tool_configs_enabled
            ON ai_service.tenant_tool_configs(company_guid, is_enabled)
            WHERE is_enabled = TRUE;

        -- 4. RLS — tenant_tool_configs
        --    Tenant A không đọc được config của tenant B
        ALTER TABLE ai_service.tenant_tool_configs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.tenant_tool_configs FORCE ROW LEVEL SECURITY;

        CREATE POLICY tenant_isolation ON ai_service.tenant_tool_configs
            USING (company_guid = current_setting('app.current_tenant', TRUE)::UUID);

        -- tool_definitions KHÔNG có RLS — là global registry

        -- 5. Grants
        GRANT SELECT                    ON ai_service.tool_definitions     TO ai_app;
        GRANT SELECT, INSERT, UPDATE    ON ai_service.tenant_tool_configs  TO ai_app;
        GRANT ALL                       ON ai_service.tool_definitions     TO ai_admin;
        GRANT ALL                       ON ai_service.tenant_tool_configs  TO ai_admin;
        GRANT USAGE, SELECT ON SEQUENCE ai_service.tool_definitions_id_seq    TO ai_app;
        GRANT USAGE, SELECT ON SEQUENCE ai_service.tenant_tool_configs_id_seq TO ai_app;
    """)


def downgrade():
    op.execute("""
        DROP TABLE IF EXISTS ai_service.tenant_tool_configs;
        DROP TABLE IF EXISTS ai_service.tool_definitions;
    """)