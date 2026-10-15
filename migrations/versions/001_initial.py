"""Initial schema: accounts, projects, nodes, pages, api keys, usage, login attempts.

Revision ID: 001
Revises: None
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

EMBED_DIMS = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "accounts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("handle", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("tier", sa.String(16), nullable=False, server_default="local"),
        sa.Column("byok_base_url", sa.Text),
        sa.Column("byok_model", sa.Text),
        sa.Column("byok_key_enc", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_projects_account_slug_live", "projects", ["account_id", "slug"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "nodes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", pg.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('folder', 'page')", name="ck_nodes_kind"),
    )
    op.create_index(
        "uq_nodes_project_path_live", "nodes", ["project_id", "path"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_nodes_project_parent", "nodes", ["project_id", "parent_id"])
    op.create_index("ix_nodes_path_prefix", "nodes", ["project_id", "path"], postgresql_ops={"path": "text_pattern_ops"})

    op.create_table(
        "pages",
        sa.Column("node_id", pg.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("markdown", sa.Text, nullable=False, server_default=""),
        sa.Column("html", sa.Text, nullable=False, server_default=""),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("tags", pg.ARRAY(sa.String(64)), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(EMBED_DIMS)),
        sa.Column("enrich_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("enrich_error", sa.Text),
        sa.Column("enriched_by", sa.String(64)),
        sa.Column("enriched_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE INDEX ix_pages_embedding_hnsw ON pages USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "api_keys",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", pg.ARRAY(sa.String(16)), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("meta", pg.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_usage_account_tier_at", "usage_events", ["account_id", "tier", "at"])

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_attempts_key_at", "login_attempts", ["key", "at"])


def downgrade() -> None:
    for table in ("login_attempts", "usage_events", "api_keys", "pages", "nodes", "projects", "accounts"):
        op.drop_table(table)
