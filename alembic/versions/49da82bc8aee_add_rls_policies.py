"""add_rls_policies

Revision ID: 49da82bc8aee
Revises: e7ebf08efa6b
Create Date: 2026-10-19 22:15:19.746220

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49da82bc8aee'
down_revision: Union[str, Sequence[str], None] = 'e7ebf08efa6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = [
    "legal_entities", "evidence",
    "obligations", "controls", "compliance_findings",
    "remediation_tasks", "approvals", "compliance_audit_events",
    "users",
]

# Tables with org_id via FK (use subquery in RLS)
FK_TENANT_TABLES = {
    "licenses": "entity_id IN (SELECT id FROM legal_entities WHERE org_id = current_setting('app.current_org_id', true)::uuid)",
    "control_obligations": "control_id IN (SELECT id FROM controls WHERE org_id = current_setting('app.current_org_id', true)::uuid)",
}


def upgrade() -> None:
    """Upgrade schema."""
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """)
    for table, condition in FK_TENANT_TABLES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING ({condition})
            WITH CHECK ({condition})
        """)
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_organizations ON organizations
        USING (id = current_setting('app.current_org_id', true)::uuid)
        WITH CHECK (id = current_setting('app.current_org_id', true)::uuid)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in FK_TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_organizations ON organizations")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
