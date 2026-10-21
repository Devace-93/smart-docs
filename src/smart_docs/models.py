"""ORM models. The schema itself lives in `migrations/`; these classes mirror it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBED_DIMS = 768


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The user id at accounts.3m4.net (the JWT `sub`). E-mail and handle mirror its claims (SD-014).
    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    byok_base_url: Mapped[str | None] = mapped_column(Text)
    byok_model: Mapped[str | None] = mapped_column(Text)
    byok_key_enc: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    projects: Mapped[list[Project]] = relationship(back_populates="account")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index(
            "uq_projects_account_slug_live",
            "account_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="projects")


class Node(Base):
    """A folder or a page in a project tree. Pages also own a `Page` row."""

    __tablename__ = "nodes"
    __table_args__ = (
        Index(
            "uq_nodes_project_path_live",
            "project_id",
            "path",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_nodes_project_parent", "project_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # folder | page
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    page: Mapped[Page | None] = relationship(back_populates="node", uselist=False, lazy="joined")


class Page(Base):
    __tablename__ = "pages"

    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    embedding = mapped_column(Vector(EMBED_DIMS), nullable=True)
    enrich_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    enrich_error: Mapped[str | None] = mapped_column(Text)
    enriched_by: Mapped[str | None] = mapped_column(String(64))
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    node: Mapped[Node] = relationship(back_populates="page")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageEvent(Base):
    """One row per model call an account spent. Limits are counted over this table."""

    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_account_tier_at", "account_id", "tier", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
