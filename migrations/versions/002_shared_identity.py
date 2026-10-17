"""Shared identity (SD-013): accounts mirror accounts.3m4.net.

Destructive by decision: every account and everything hanging from it
(projects, nodes, pages, API keys, usage events) is deleted. There were no
real users when this shipped (2026-10-16). Passwords and login attempts go
away; `identity_id` ties a row to its accounts.3m4.net user.

Revision ID: 002
Revises: 001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM accounts")  # cascades to projects, nodes, pages, api_keys, usage_events
    op.drop_table("login_attempts")
    op.drop_column("accounts", "password_hash")
    op.add_column("accounts", sa.Column("identity_id", pg.UUID(as_uuid=True), nullable=False))
    op.create_unique_constraint("uq_accounts_identity_id", "accounts", ["identity_id"])


def downgrade() -> None:
    op.execute("DELETE FROM accounts")  # rows without a password cannot come back as local accounts
    op.drop_constraint("uq_accounts_identity_id", "accounts", type_="unique")
    op.drop_column("accounts", "identity_id")
    op.add_column("accounts", sa.Column("password_hash", sa.Text, nullable=False))
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_attempts_key_at", "login_attempts", ["key", "at"])
