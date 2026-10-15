"""The MCP server (SD-007). Tools call the service layer directly; there is no second HTTP hop.

The authenticated account comes from a context variable: the HTTP transport sets it from the
bearer API key, the stdio transport from the SD_API_KEY environment variable.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from mcp.server.mcpserver import MCPServer

from smart_docs.api.deps import Principal, resolve_principal
from smart_docs.api.routes import has_body
from smart_docs.api.serializers import node_out, project_base_url, project_out
from smart_docs.db import session_factory
from smart_docs.errors import SDError, Unauthorized
from smart_docs.services import projects as projects_svc
from smart_docs.services import search as search_svc
from smart_docs.services import tree as tree_svc
from smart_docs.services.render import llms_txt
from smart_docs.services.usage import usage_report
from smart_docs.worker.app import enqueue_enrich

current_principal: ContextVar[Principal | None] = ContextVar("sd_principal", default=None)

INSTRUCTIONS = (
    "Smart Docs is a knowledge base of Markdown pages organised as project -> folders -> pages. "
    "Paths look like `docs/api/auth`. Start with list_projects, then list_tree for a project. "
    "A public page is served at {public_base_url}/{handle}/{project}/{path} (HTML), the same URL "
    "plus `.md` (raw Markdown) and {project}/llms.txt (the project index). "
    "If you pass summary and tags when creating or updating a page, no model is called (agent mode)."
)

server = MCPServer("smart-docs", instructions=INSTRUCTIONS)


def _principal() -> Principal:
    p = current_principal.get()
    if p is None:
        raise Unauthorized("No API key. Set SD_API_KEY (stdio) or send Authorization: Bearer sd_... (HTTP).")
    return p


def _json(data: Any) -> str:
    return json.dumps(data, default=str, ensure_ascii=False, indent=1)


def _error(e: SDError) -> str:
    return _json({"error": e.to_dict()})


async def _call(fn):
    try:
        async with session_factory()() as session:
            result = await fn(session)
            await session.commit()
            return _json(result)
    except SDError as e:
        return _error(e)


@server.tool(
    description=(
        "List the projects of the authenticated account with their public URLs. "
        "Example: list_projects() -> [{slug: 'notes', name: 'Notes', public_url: '.../enrique/notes'}]"
    )
)
async def list_projects() -> str:
    p = _principal()
    p.require("read")

    async def run(session):
        return [project_out(x, p.account.handle) for x in await projects_svc.list_projects(session, p.account)]

    return await _call(run)


@server.tool(
    description=(
        "Create a project. Example: create_project(name='Field notes', description='Things I learned') "
        "-> {slug: 'field-notes', public_url: ...}. Pages go inside it with create_page."
    )
)
async def create_project(name: str, description: str = "", slug: str | None = None) -> str:
    p = _principal()
    p.require("write")

    async def run(session):
        return project_out(
            await projects_svc.create_project(session, p.account, name=name, slug=slug, description=description),
            p.account.handle,
        )

    return await _call(run)


@server.tool(
    description=(
        "The tree of a project as nested JSON (paths, kinds, titles, public flags), WITHOUT page bodies. "
        "Call this first. Example: list_tree(project='notes') or list_tree(project='notes', folder='docs/api'). "
        "Use get_page to read one page's Markdown."
    )
)
async def list_tree(project: str, folder: str | None = None) -> str:
    p = _principal()
    p.require("read")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        nodes = await tree_svc.list_nodes(session, proj, under=folder)
        return tree_svc.build_tree(nodes, root=folder.strip("/") if folder else None)

    return await _call(run)


@server.tool(
    description=(
        "Read one page: Markdown, summary, tags, version and public URL. "
        "Example: get_page(project='notes', path='docs/api/auth'). "
        "The version is what update_page expects in expected_version."
    )
)
async def get_page(project: str, path: str) -> str:
    p = _principal()
    p.require("read")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        node = await tree_svc.get_node(session, proj, path)
        d = node_out(node, p.account.handle, proj.slug)
        d.pop("html", None)
        return d

    return await _call(run)


@server.tool(
    description=(
        "Create a page (or a folder with kind='folder') under parent_path, or at the root when parent_path is empty. "
        "Example: create_page(project='notes', parent_path='docs/api', title='Auth', markdown='# Auth\\n...'). "
        "Pass summary and tags to skip the model (agent mode). Returns path, version and public_url. "
        "Missing parent folders are NOT created: make them first with kind='folder'."
    )
)
async def create_page(
    project: str,
    title: str,
    markdown: str = "",
    parent_path: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    kind: str = "page",
    public: bool = False,
) -> str:
    p = _principal()
    p.require("write")
    if public:
        p.require("publish")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        node = await tree_svc.create_node(
            session,
            proj,
            kind=kind,
            title=title,
            parent_path=parent_path,
            markdown=markdown,
            summary=summary,
            tags=tags,
            is_public=public,
        )
        await session.commit()
        if node.kind == "page" and has_body(markdown):
            await enqueue_enrich(node.id)
        return node_out(node, p.account.handle, proj.slug, with_body=False)

    return await _call(run)


@server.tool(
    description=(
        "Update a page's Markdown. content_edit_mode is 'replace' (default), 'append' or 'prepend', so you can add "
        "to a page without reading it first. Send expected_version (from get_page) to avoid clobbering another "
        "writer; a conflict error means re-read and retry. Example: "
        "update_page(project='notes', path='docs/api/auth', markdown='## Tokens\\n...', content_edit_mode='append')."
    )
)
async def update_page(
    project: str,
    path: str,
    markdown: str | None = None,
    content_edit_mode: str = "replace",
    title: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    expected_version: int | None = None,
) -> str:
    p = _principal()
    p.require("write")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        node = await tree_svc.get_node(session, proj, path)
        node = await tree_svc.update_page(
            session,
            node,
            markdown=markdown,
            title=title,
            summary=summary,
            tags=tags,
            expected_version=expected_version,
            content_edit_mode=content_edit_mode,
        )
        await session.commit()
        if markdown is not None and node.kind == "page" and has_body(node.page.markdown if node.page else ""):
            await enqueue_enrich(node.id)
        return node_out(node, p.account.handle, proj.slug, with_body=False)

    return await _call(run)


@server.tool(
    description=(
        "Move or reorder a node (page or folder) and its subtree. new_parent_path empty means the root. "
        "Returns the new path; public URLs change with the path. "
        "Example: move_node(project='notes', path='drafts/auth', new_parent_path='docs/api', position=0)."
    )
)
async def move_node(
    project: str,
    path: str,
    new_parent_path: str | None = None,
    position: int | None = None,
    new_slug: str | None = None,
) -> str:
    p = _principal()
    p.require("write")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        node = await tree_svc.get_node(session, proj, path)
        node = await tree_svc.move_node(
            session, proj, node, new_parent_path=new_parent_path, position=position, new_slug=new_slug
        )
        return node_out(node, p.account.handle, proj.slug, with_body=False)

    return await _call(run)


@server.tool(
    description=(
        "Publish (public=true) or unpublish a page. Returns the public URL; the Markdown form is that URL plus '.md'. "
        "Example: publish_page(project='notes', path='docs/api/auth', public=True)."
    )
)
async def publish_page(project: str, path: str, public: bool = True, expected_version: int | None = None) -> str:
    p = _principal()
    p.require("publish")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        node = await tree_svc.get_node(session, proj, path)
        node = await tree_svc.set_public(session, node, public, expected_version=expected_version)
        return node_out(node, p.account.handle, proj.slug, with_body=False)

    return await _call(run)


@server.tool(
    description=(
        "Soft-delete a page or a folder with everything under it. Example: delete_node(project='notes', path='drafts')."
    )
)
async def delete_node(project: str, path: str) -> str:
    p = _principal()
    p.require("write")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        node = await tree_svc.get_node(session, proj, path)
        removed = await tree_svc.delete_node(session, proj, node)
        return {"deleted": removed, "path": node.path}

    return await _call(run)


@server.tool(
    description=(
        "Semantic search inside one project. Returns up to k pages with path, summary and score (1 = identical). "
        "Pages are searchable once the worker has embedded them (seconds after a save). "
        "Example: search(project='notes', query='how do API keys work', k=5)."
    )
)
async def search(project: str, query: str, k: int = 10) -> str:
    p = _principal()
    p.require("read")

    async def run(session):
        proj = await projects_svc.get_project(session, p.account, project)
        return await search_svc.search(session, proj, query, k=k)

    return await _call(run)


@server.tool(
    description="Today's model usage against the account's limits. Call before spending quota. Example: get_usage()."
)
async def get_usage() -> str:
    p = _principal()

    async def run(session):
        return await usage_report(session, p.account)

    return await _call(run)


@server.resource(
    "sd://{handle}/{project}/llms.txt",
    name="project-llms-txt",
    description="The llms.txt index of a public project: one line per public page with its .md link.",
    mime_type="text/plain",
)
async def project_llms(handle: str, project: str) -> str:
    async with session_factory()() as session:
        proj = await projects_svc.get_public_project(session, handle, project)
        if proj is None:
            return "Not found."
        nodes = await tree_svc.list_public_pages(session, proj)
        return llms_txt(
            project_name=proj.name,
            description=proj.description,
            base_url=project_base_url(handle, project),
            pages=[{"path": n.path, "title": n.title, "summary": n.page.summary if n.page else ""} for n in nodes],
        )


async def principal_from_key(api_key: str | None) -> Principal | None:
    if not api_key:
        return None
    async with session_factory()() as session:
        p = await resolve_principal(session, api_key)
        await session.commit()
        return p
