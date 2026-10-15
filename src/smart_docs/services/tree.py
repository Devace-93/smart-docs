"""The node tree: folders and pages, materialized paths, move and reorder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.errors import Conflict, Invalid, NotFound
from smart_docs.models import Node, Page, Project
from smart_docs.services.render import first_heading, render_html
from smart_docs.slug import is_valid_slug, slugify

MAX_DEPTH = 12


def _normalize_path(path: str | None) -> str:
    path = (path or "").strip().strip("/")
    if path.endswith(".md"):
        path = path[:-3]
    return path


async def get_node(session: AsyncSession, project: Project, path: str) -> Node:
    path = _normalize_path(path)
    node = await session.scalar(
        select(Node).where(Node.project_id == project.id, Node.path == path, Node.deleted_at.is_(None))
    )
    if node is None:
        raise NotFound(f"No node at path {path!r}.", hint="Call list_tree to see the paths that exist.")
    return node


async def get_public_page(session: AsyncSession, project: Project, path: str) -> Node | None:
    """A public page, or None. Private and missing pages look the same on purpose."""
    path = _normalize_path(path)
    return await session.scalar(
        select(Node).where(
            Node.project_id == project.id,
            Node.path == path,
            Node.kind == "page",
            Node.is_public.is_(True),
            Node.deleted_at.is_(None),
        )
    )


async def list_public_pages(session: AsyncSession, project: Project) -> list[Node]:
    rows = await session.scalars(
        select(Node)
        .where(Node.project_id == project.id, Node.kind == "page", Node.is_public.is_(True), Node.deleted_at.is_(None))
        .order_by(Node.path)
    )
    return list(rows)


async def list_nodes(session: AsyncSession, project: Project, *, under: str | None = None) -> list[Node]:
    q = select(Node).where(Node.project_id == project.id, Node.deleted_at.is_(None))
    if under:
        under = _normalize_path(under)
        q = q.where((Node.path == under) | Node.path.like(under + "/%"))
    rows = await session.scalars(q.order_by(Node.path, Node.position))
    return list(rows)


def build_tree(nodes: list[Node], *, root: str | None = None) -> list[dict]:
    """Nest a flat node list into children lists, ordered by position then title."""
    by_parent: dict[uuid.UUID | None, list[Node]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    for lst in by_parent.values():
        lst.sort(key=lambda n: (n.position, n.title.lower()))
    ids = {n.id for n in nodes}

    def pack(n: Node) -> dict:
        return {
            "path": n.path,
            "title": n.title,
            "kind": n.kind,
            "public": n.is_public,
            "version": n.version,
            "updated_at": n.updated_at,
            "summary": (n.page.summary if n.page else None),
            "tags": (list(n.page.tags) if n.page else None),
            "children": [pack(c) for c in by_parent.get(n.id, [])],
        }

    if root is not None:
        roots = [n for n in nodes if n.path == root]
    else:
        roots = [n for n in nodes if n.parent_id is None or n.parent_id not in ids]
        roots.sort(key=lambda n: (n.position, n.title.lower()))
    return [pack(n) for n in roots]


async def _resolve_parent(session: AsyncSession, project: Project, parent_path: str | None) -> Node | None:
    parent_path = _normalize_path(parent_path)
    if not parent_path:
        return None
    parent = await get_node(session, project, parent_path)
    if parent.kind != "page" and parent.kind != "folder":
        raise Invalid("Parent must be a folder or a page.")
    if parent.path.count("/") + 1 >= MAX_DEPTH:
        raise Invalid(f"Tree is limited to {MAX_DEPTH} levels.")
    return parent


async def _unique_slug(
    session: AsyncSession, project: Project, parent: Node | None, base: str, *, exclude: uuid.UUID | None = None
) -> str:
    siblings = await session.scalars(
        select(Node.slug).where(
            Node.project_id == project.id,
            Node.parent_id == (parent.id if parent else None),
            Node.deleted_at.is_(None),
            *([Node.id != exclude] if exclude else []),
        )
    )
    taken = set(siblings)
    slug, i = base, 2
    while slug in taken:
        slug = f"{base}-{i}"
        i += 1
    return slug


async def _next_position(session: AsyncSession, project: Project, parent: Node | None) -> int:
    m = await session.scalar(
        select(func.max(Node.position)).where(
            Node.project_id == project.id, Node.parent_id == (parent.id if parent else None), Node.deleted_at.is_(None)
        )
    )
    return (m if m is not None else -1) + 1


async def create_node(
    session: AsyncSession,
    project: Project,
    *,
    kind: str,
    title: str,
    parent_path: str | None = None,
    slug: str | None = None,
    markdown: str = "",
    summary: str | None = None,
    tags: list[str] | None = None,
    is_public: bool = False,
) -> Node:
    if kind not in ("folder", "page"):
        raise Invalid("kind must be 'folder' or 'page'.")
    title = (title or "").strip() or (first_heading(markdown) if kind == "page" else None) or "Untitled"
    parent = await _resolve_parent(session, project, parent_path)
    base = slugify(slug or title, max_length=128)
    if slug and not is_valid_slug(base):
        raise Invalid("Invalid slug.")
    slug = await _unique_slug(session, project, parent, base)
    path = f"{parent.path}/{slug}" if parent else slug
    node = Node(
        project_id=project.id,
        parent_id=parent.id if parent else None,
        kind=kind,
        slug=slug,
        title=title[:300],
        path=path,
        position=await _next_position(session, project, parent),
        is_public=bool(is_public) if kind == "page" else False,
    )
    session.add(node)
    await session.flush()
    if kind == "page":
        page = Page(node_id=node.id, markdown=markdown or "", html=render_html(markdown or ""))
        _apply_agent_enrichment(page, summary, tags)
        session.add(page)
        await session.flush()
    await session.refresh(node)  # loads the (possibly absent) page row so no lazy load happens later
    return node


def _apply_agent_enrichment(page: Page, summary: str | None, tags: list[str] | None) -> None:
    """Agent mode: the caller supplied summary and tags, so no model call is needed."""
    if summary is not None and summary.strip():
        page.summary = summary.strip()[:600]
        page.tags = _clean_tags(tags or [])
        page.enrich_status = "agent"
        page.enriched_by = "agent"
        page.enriched_at = datetime.now(UTC)
    else:
        page.enrich_status = "pending"
        page.enriched_by = None


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        t = slugify(str(t), max_length=64)
        if t and t != "untitled" and t not in out:
            out.append(t)
    return out[:10]


async def update_page(
    session: AsyncSession,
    node: Node,
    *,
    markdown: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    expected_version: int | None = None,
    content_edit_mode: str = "replace",
) -> Node:
    if expected_version is not None and node.version != expected_version:
        raise Conflict(f"Version moved: you expected {expected_version}, the page is at {node.version}.")
    if node.kind == "page" and markdown is not None:
        page = node.page
        assert page is not None
        if content_edit_mode == "append":
            page.markdown = (page.markdown.rstrip("\n") + "\n\n" + markdown).lstrip("\n")
        elif content_edit_mode == "prepend":
            page.markdown = markdown.rstrip("\n") + "\n\n" + page.markdown
        elif content_edit_mode == "replace":
            page.markdown = markdown
        else:
            raise Invalid("content_edit_mode must be replace, append or prepend.")
        page.html = render_html(page.markdown)
        _apply_agent_enrichment(page, summary, tags)
    elif node.kind == "page" and (summary is not None or tags is not None):
        page = node.page
        assert page is not None
        if summary is not None:
            page.summary = summary.strip()[:600]
        if tags is not None:
            page.tags = _clean_tags(tags)
        page.enrich_status = "agent"
        page.enriched_by = "agent"
        page.enriched_at = datetime.now(UTC)
    if title is not None and title.strip():
        node.title = title.strip()[:300]
    node.version += 1
    node.updated_at = datetime.now(UTC)
    await session.flush()
    return node


async def set_public(session: AsyncSession, node: Node, public: bool, *, expected_version: int | None = None) -> Node:
    if node.kind != "page":
        raise Invalid("Only pages can be published.", hint="Publish each page inside the folder.")
    if expected_version is not None and node.version != expected_version:
        raise Conflict(f"Version moved: you expected {expected_version}, the page is at {node.version}.")
    node.is_public = bool(public)
    node.version += 1
    node.updated_at = datetime.now(UTC)
    await session.flush()
    return node


async def move_node(
    session: AsyncSession,
    project: Project,
    node: Node,
    *,
    new_parent_path: str | None,
    position: int | None = None,
    new_slug: str | None = None,
) -> Node:
    """Re-parent and/or reorder. Rewrites the subtree's paths in one statement."""
    new_parent = await _resolve_parent(session, project, new_parent_path)
    if new_parent is not None:
        if new_parent.id == node.id or new_parent.path == node.path or new_parent.path.startswith(node.path + "/"):
            raise Invalid("Cannot move a node under itself.")
    base = slugify(new_slug, max_length=128) if new_slug else node.slug
    slug = await _unique_slug(session, project, new_parent, base, exclude=node.id)
    old_path = node.path
    new_path = f"{new_parent.path}/{slug}" if new_parent else slug
    parent_changed = (new_parent.id if new_parent else None) != node.parent_id
    if position is None and parent_changed:
        position = await _next_position(session, project, new_parent)
    node.parent_id = new_parent.id if new_parent else None
    node.slug = slug
    node.path = new_path
    if position is not None:
        await _reorder(session, project, new_parent, node, position)
    node.version += 1
    node.updated_at = datetime.now(UTC)
    await session.flush()
    if new_path != old_path:
        await session.execute(
            update(Node)
            .where(Node.project_id == project.id, Node.path.like(old_path + "/%"), Node.deleted_at.is_(None))
            .values(path=func.concat(new_path, func.substr(Node.path, len(old_path) + 1)))
        )
    return node


async def _reorder(session: AsyncSession, project: Project, parent: Node | None, node: Node, position: int) -> None:
    siblings = list(
        await session.scalars(
            select(Node)
            .where(
                Node.project_id == project.id,
                Node.parent_id == (parent.id if parent else None),
                Node.deleted_at.is_(None),
                Node.id != node.id,
            )
            .order_by(Node.position, Node.title)
        )
    )
    position = max(0, min(position, len(siblings)))
    siblings.insert(position, node)
    for i, n in enumerate(siblings):
        n.position = i


async def delete_node(session: AsyncSession, project: Project, node: Node) -> int:
    """Soft-delete the node and its subtree. Returns the number of nodes removed."""
    ts = datetime.now(UTC)
    result = await session.execute(
        update(Node)
        .where(
            Node.project_id == project.id,
            Node.deleted_at.is_(None),
            (Node.path == node.path) | Node.path.like(node.path + "/%"),
        )
        .values(deleted_at=ts)
    )
    return result.rowcount or 0


async def project_page_count(session: AsyncSession, project: Project) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Node)
            .where(Node.project_id == project.id, Node.kind == "page", Node.deleted_at.is_(None))
        )
        or 0
    )


__all__ = [
    "build_tree",
    "create_node",
    "delete_node",
    "get_node",
    "get_public_page",
    "list_nodes",
    "list_public_pages",
    "move_node",
    "set_public",
    "update_page",
    "project_page_count",
    "text",
]
