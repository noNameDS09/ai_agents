"""auth_lookup_policy

Authentication must read `users` before a tenant context exists. The `users`
table is RLS-forced, so a plain SELECT returns nothing for the app role.

Add a narrow, additive SELECT policy: a session may see a user row only when it
already presents that row's API-key hash (set via `app.auth_api_key_hash`). This
grants no tenant data — just "can I authenticate this key?" — and cannot be used
to enumerate users, because the hash is derived from a secret the caller holds.

Revision ID: c3a9d5e6f712
Revises: 8b1f0c7d2e44
Create Date: 2026-10-20 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3a9d5e6f712'
down_revision: Union[str, Sequence[str], None] = '8b1f0c7d2e44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow hash-scoped authentication lookups on users."""
    op.execute(
        """
        CREATE POLICY users_authenticate ON users
        FOR SELECT
        USING (
            api_key_hash IS NOT NULL
            AND api_key_hash = current_setting('app.auth_api_key_hash', true)
        )
        """
    )


def downgrade() -> None:
    """Remove the authentication lookup policy."""
    op.execute("DROP POLICY IF EXISTS users_authenticate ON users")
