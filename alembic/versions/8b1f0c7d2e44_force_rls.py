"""force_rls

Apply FORCE ROW LEVEL SECURITY so the table *owner* is also subject to the
tenant isolation policies. Without this, RLS is silently bypassed whenever the
application connects as the table owner (a common default).

Note: Postgres superusers always bypass RLS. The application must therefore
connect as a non-superuser role (see docs/SETUP.md and scripts/init-db.sql).

Revision ID: 8b1f0c7d2e44
Revises: 4fc221c5302a
Create Date: 2026-10-20 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8b1f0c7d2e44'
down_revision: Union[str, Sequence[str], None] = '4fc221c5302a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = [
    "organizations",
    "legal_entities",
    "evidence",
    "obligations",
    "controls",
    "compliance_findings",
    "remediation_tasks",
    "approvals",
    "compliance_audit_events",
    "users",
    "licenses",
    "control_obligations",
]


def upgrade() -> None:
    """Force RLS for table owners as well as ordinary roles."""
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Revert to owner-bypass RLS."""
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
