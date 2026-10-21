"""Pydantic models for the REST API. They drive the OpenAPI spec agents read."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AccountOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool = True
    handle: str = Field(description="Public URL handle, mirrored from accounts.3m4.net: /{handle}/{project}/{path}")
    name: str | None = None
    avatar_url: str | None = None
    tier: str
    byok_base_url: str | None = None
    byok_model: str | None = None
    byok_configured: bool = False
    created_at: datetime


class AccountPatch(BaseModel):
    tier: str | None = None
    byok_base_url: str | None = None
    byok_model: str | None = None
    byok_key: str | None = Field(default=None, description="Stored encrypted. Send an empty string to remove it.")


class ApiKeyIn(BaseModel):
    name: str = "key"
    scopes: list[str] = Field(default_factory=lambda: ["read", "write", "publish"])


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Shown once. Store it now.")


class ProjectIn(BaseModel):
    name: str
    slug: str | None = None
    description: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    created_at: datetime
    public_url: str
    llms_txt_url: str


class NodeIn(BaseModel):
    kind: str = Field(default="page", pattern="^(page|folder)$")
    title: str = ""
    parent_path: str | None = Field(
        default=None, description="Folder or page path to create under. Empty for the root."
    )
    slug: str | None = None
    markdown: str = ""
    summary: str | None = Field(default=None, description="Agent mode: supply summary and tags and no model is called.")
    tags: list[str] | None = None
    public: bool = False


class NodePatch(BaseModel):
    title: str | None = None
    markdown: str | None = None
    content_edit_mode: str = Field(default="replace", pattern="^(replace|append|prepend)$")
    summary: str | None = None
    tags: list[str] | None = None
    expected_version: int | None = None


class MoveIn(BaseModel):
    new_parent_path: str | None = None
    position: int | None = None
    new_slug: str | None = None


class PublishIn(BaseModel):
    public: bool = True
    expected_version: int | None = None


class NodeOut(BaseModel):
    path: str
    title: str
    kind: str
    public: bool
    version: int
    created_at: datetime
    updated_at: datetime
    public_url: str | None = None
    markdown: str | None = None
    html: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    enrich_status: str | None = None
    enrich_error: str | None = None
    embedded: bool | None = Field(
        default=None, description="True once the worker stored the embedding, so search can find the page."
    )


class TreeNode(BaseModel):
    path: str
    title: str
    kind: str
    public: bool
    version: int
    updated_at: datetime
    summary: str | None = None
    tags: list[str] | None = None
    children: list[TreeNode] = Field(default_factory=list)


class SearchHit(BaseModel):
    path: str
    title: str
    summary: str
    tags: list[str]
    public: bool
    score: float


class ErrorOut(BaseModel):
    code: str
    message: str
    hint: str = ""
