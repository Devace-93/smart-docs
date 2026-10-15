"""Projects: one tree of folders and pages per project."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.errors import Invalid, NotFound
from smart_docs.models import Account, Project
from smart_docs.slug import is_valid_slug, slugify


async def list_projects(session: AsyncSession, account: Account) -> list[Project]:
    rows = await session.scalars(
        select(Project)
        .where(Project.account_id == account.id, Project.deleted_at.is_(None))
        .order_by(Project.created_at)
    )
    return list(rows)


async def get_project(session: AsyncSession, account: Account, slug: str) -> Project:
    project = await session.scalar(
        select(Project).where(Project.account_id == account.id, Project.slug == slug, Project.deleted_at.is_(None))
    )
    if project is None:
        raise NotFound(f"Project {slug!r} not found.", hint="Call list_projects to see your projects.")
    return project


async def get_public_project(session: AsyncSession, handle: str, slug: str) -> Project | None:
    return await session.scalar(
        select(Project)
        .join(Account, Account.id == Project.account_id)
        .where(Account.handle == handle, Project.slug == slug, Project.deleted_at.is_(None))
    )


async def create_project(
    session: AsyncSession, account: Account, *, name: str, slug: str | None = None, description: str = ""
) -> Project:
    name = name.strip()
    if not name:
        raise Invalid("Project name is required.")
    slug = slugify(slug or name, max_length=64)
    if not is_valid_slug(slug):
        raise Invalid("Invalid project slug.")
    existing = await session.scalar(
        select(Project).where(Project.account_id == account.id, Project.slug == slug, Project.deleted_at.is_(None))
    )
    if existing is not None:
        raise Invalid(f"A project with slug {slug!r} already exists.")
    project = Project(account_id=account.id, name=name, slug=slug, description=description.strip())
    session.add(project)
    await session.flush()
    return project


async def update_project(
    session: AsyncSession, project: Project, *, name: str | None = None, description: str | None = None
) -> Project:
    if name is not None:
        if not name.strip():
            raise Invalid("Project name is required.")
        project.name = name.strip()
    if description is not None:
        project.description = description.strip()
    await session.flush()
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    project.deleted_at = datetime.now(UTC)
    await session.flush()


async def project_by_id(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return await session.get(Project, project_id)
