"""Semantic search inside one project (pgvector cosine distance)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.errors import Invalid
from smart_docs.llm.client import embed
from smart_docs.models import Node, Page, Project


async def search(
    session: AsyncSession, project: Project, query: str, *, k: int = 10, public_only: bool = False
) -> list[dict]:
    query = (query or "").strip()
    if not query:
        raise Invalid("Query is empty.")
    k = max(1, min(int(k), 50))
    [vector] = await embed([query])
    distance = Page.embedding.cosine_distance(vector).label("distance")
    q = (
        select(Node, distance)
        .join(Page, Page.node_id == Node.id)
        .where(Node.project_id == project.id, Node.deleted_at.is_(None), Page.embedding.is_not(None))
    )
    if public_only:
        q = q.where(Node.is_public.is_(True))
    rows = (await session.execute(q.order_by(distance).limit(k + 1))).all()
    results = [
        {
            "path": n.path,
            "title": n.title,
            "summary": n.page.summary if n.page else "",
            "tags": list(n.page.tags) if n.page else [],
            "public": n.is_public,
            "score": round(1.0 - float(d), 4),
        }
        for n, d in rows[:k]
    ]
    return results
