"""003_sprint3_schema"""
revision = 'sprint3_xxx'  # alembic tự gen
down_revision = '0689772182af'

from alembic import op

def upgrade():
    op.execute("""
        -- 1. tool_call_log (hypertable)
        CREATE TABLE ai_service.tool_call_log (
          id              BIGSERIAL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          company_guid    UUID NOT NULL,
          conversation_id UUID,
          request_id      UUID,
          agent_name      VARCHAR(64),
          tool_name       VARCHAR(128) NOT NULL,
          input_data      JSONB,
          output_data     JSONB,
          latency_ms      INT,
          success         BOOLEAN DEFAULT TRUE,
          error_message   TEXT,
          PRIMARY KEY (id, created_at)
        );
        SELECT create_hypertable('ai_service.tool_call_log', 'created_at',
                                 chunk_time_interval => INTERVAL '7 days');

        -- 2. tenant_model_overrides
        CREATE TABLE ai_service.tenant_model_overrides (
          id              SERIAL PRIMARY KEY,
          company_guid    UUID NOT NULL REFERENCES ai_service.tenants(company_guid),
          agent_role      VARCHAR(64) NOT NULL,  -- 'classifier', 'executor', 'summarizer'
          provider        VARCHAR(32) NOT NULL,
          model           VARCHAR(128) NOT NULL,
          temperature     NUMERIC(3,2),
          max_tokens      INT,
          created_at      TIMESTAMPTZ DEFAULT NOW(),
          UNIQUE (company_guid, agent_role)
        );

        -- 3. industry_packs skeleton
        CREATE TABLE ai_service.industry_packs (
          id              SERIAL PRIMARY KEY,
          pack_id         VARCHAR(64) NOT NULL,  -- 'tourism@1.0.0', 'generic@1.0.0'
          display_name    VARCHAR(128),
          version         VARCHAR(32) NOT NULL,
          is_active       BOOLEAN DEFAULT TRUE,
          config          JSONB DEFAULT '{}',
          created_at      TIMESTAMPTZ DEFAULT NOW(),
          UNIQUE (pack_id)
        );

        -- 4. tenant_pack_overrides skeleton
        CREATE TABLE ai_service.tenant_pack_assignments (
          company_guid    UUID PRIMARY KEY REFERENCES ai_service.tenants(company_guid),
          pack_id         VARCHAR(64) NOT NULL REFERENCES ai_service.industry_packs(pack_id),
          overrides       JSONB DEFAULT '{}',
          assigned_at     TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Bật RLS cho audit_log (bị miss ở migration 001)
    op.execute("""
        ALTER TABLE ai_service.audit_log ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.audit_log FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON ai_service.audit_log
          USING      (company_guid = current_setting('app.current_tenant', TRUE)::UUID);

        -- Grant cho bảng mới
        GRANT SELECT, INSERT ON ai_service.tool_call_log TO ai_app;
        GRANT SELECT, INSERT, UPDATE ON ai_service.tenant_model_overrides TO ai_app;
        GRANT SELECT ON ai_service.industry_packs TO ai_app;
        GRANT SELECT ON ai_service.tenant_pack_assignments TO ai_app;
        GRANT ALL ON ai_service.tool_call_log TO ai_admin;
        GRANT ALL ON ai_service.tenant_model_overrides TO ai_admin;
        GRANT ALL ON ai_service.industry_packs TO ai_admin;
        GRANT ALL ON ai_service.tenant_pack_assignments TO ai_admin;
    """)

def downgrade():
    op.execute("""
        DROP TABLE IF EXISTS ai_service.tenant_pack_assignments;
        DROP TABLE IF EXISTS ai_service.industry_packs;
        DROP TABLE IF EXISTS ai_service.tenant_model_overrides;
        DROP TABLE IF EXISTS ai_service.tool_call_log;
    """)