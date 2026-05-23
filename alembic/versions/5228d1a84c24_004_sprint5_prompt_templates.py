"""004_sprint5_prompt_templates

Revision ID: 5228d1a84c24
Revises: 8b32f1048493
Create Date: 2026-05-22 15:31:32.390264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5228d1a84c24'
down_revision: Union[str, Sequence[str], None] = '8b32f1048493'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE TABLE ai_service.prompt_templates (
            id              SERIAL PRIMARY KEY,
            pack_id         VARCHAR(64) NOT NULL,
            intent          VARCHAR(64) NOT NULL,
            role            VARCHAR(32) NOT NULL DEFAULT 'system',
            template_text   TEXT NOT NULL,
            version         INT NOT NULL DEFAULT 1,
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (pack_id, intent, role, version)
        );

        ALTER TABLE ai_service.tenant_pack_assignments ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ai_service.tenant_pack_assignments FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON ai_service.tenant_pack_assignments
            USING (company_guid = current_setting('app.current_tenant', TRUE)::UUID);

        GRANT SELECT ON ai_service.prompt_templates TO ai_app;
        GRANT ALL ON ai_service.prompt_templates TO ai_admin;
    """)


def downgrade():
    op.execute("""
        DROP TABLE IF EXISTS ai_service.prompt_templates;
        DROP POLICY IF EXISTS tenant_isolation ON ai_service.tenant_pack_assignments;
        ALTER TABLE ai_service.tenant_pack_assignments DISABLE ROW LEVEL SECURITY;
    """)