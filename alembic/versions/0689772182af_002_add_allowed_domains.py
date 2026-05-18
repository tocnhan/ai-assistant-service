"""002_add_allowed_domains

Revision ID: 0689772182af
Revises: f4e886f1f643
Create Date: 2026-05-18 21:17:55.656945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0689772182af'
down_revision: Union[str, Sequence[str], None] = 'f4e886f1f643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ai_service.allowed_domains (
          id              SERIAL PRIMARY KEY,
          company_guid    UUID REFERENCES ai_service.tenants(company_guid),
          domain          VARCHAR(255) NOT NULL,
          is_active       BOOLEAN DEFAULT TRUE,
          created_at      TIMESTAMPTZ DEFAULT NOW(),
          UNIQUE (company_guid, domain)
        );
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_service.allowed_domains;")