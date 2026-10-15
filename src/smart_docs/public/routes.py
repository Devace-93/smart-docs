"""Public, unauthenticated routes (SD-006): HTML, raw Markdown, llms.txt and llms-full.txt.

Private and missing pages both return 404 so their existence is never leaked.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.api.serializers import project_base_url
from smart_docs.config import get_settings
from smart_docs.db import get_session
from smart_docs.errors import NotFound
from smart_docs.models import Node, Project
from smart_docs.services import projects as projects_svc
from smart_docs.services import tree as tree_svc
from smart_docs.services.render import llms_full_txt, llms_txt, markdown_with_front_matter
from smart_docs.web.templates import templates

router = APIRouter(tags=["public"])


def _cache_headers(etag: str) -> dict[str, str]:
    s = get_settings()
    return {"Cache-Control": f"public, max-age={s.public_cache_seconds}", "ETag": f'"{etag}"'}


async def _project_or_404(session: AsyncSession, handle: str, slug: str) -> Project:
    if handle in get_settings().reserved_handles:
        raise NotFound("Not found.", hint="")
    project = await projects_svc.get_public_project(session, handle, slug)
    if project is None:
        raise NotFound("Not found.", hint="")
    return project


def _page_dicts(project: Project, nodes: list[Node], handle: str) -> list[dict]:
    return [
        {
            "path": n.path,
            "title": n.title,
            "summary": n.page.summary if n.page else "",
            "tags": list(n.page.tags) if n.page else [],
            "updated_at": n.updated_at,
            "body": markdown_with_front_matter(
                n.page.markdown if n.page else "",
                title=n.title,
                summary=n.page.summary if n.page else "",
                tags=list(n.page.tags) if n.page else [],
                updated=n.updated_at,
                canonical=f"{project_base_url(handle, project.slug)}/{n.path}",
            ),
        }
        for n in nodes
    ]


@router.get("/{handle}/{slug}/llms.txt", response_class=PlainTextResponse, summary="Project index for models")
async def project_llms_txt(handle: str, slug: str, session: AsyncSession = Depends(get_session)):
    project = await _project_or_404(session, handle, slug)
    nodes = await tree_svc.list_public_pages(session, project)
    body = llms_txt(
        project_name=project.name,
        description=project.description,
        base_url=project_base_url(handle, slug),
        pages=_page_dicts(project, nodes, handle),
    )
    return PlainTextResponse(
        body, headers=_cache_headers(f"{project.id}-{len(nodes)}"), media_type="text/plain; charset=utf-8"
    )


@router.get(
    "/{handle}/{slug}/llms-full.txt", response_class=PlainTextResponse, summary="Every public page in one fetch"
)
async def project_llms_full(handle: str, slug: str, session: AsyncSession = Depends(get_session)):
    project = await _project_or_404(session, handle, slug)
    nodes = await tree_svc.list_public_pages(session, project)
    body = llms_full_txt(
        project_name=project.name,
        description=project.description,
        base_url=project_base_url(handle, slug),
        pages=_page_dicts(project, nodes, handle),
    )
    return PlainTextResponse(
        body, headers=_cache_headers(f"{project.id}-full-{len(nodes)}"), media_type="text/plain; charset=utf-8"
    )


@router.get("/{handle}/{slug}", response_class=HTMLResponse, summary="Public project index")
async def project_index(handle: str, slug: str, request: Request, session: AsyncSession = Depends(get_session)):
    project = await _project_or_404(session, handle, slug)
    nodes = await tree_svc.list_public_pages(session, project)
    return templates.TemplateResponse(
        request,
        "public_project.html",
        {
            "project": project,
            "handle": handle,
            "pages": _page_dicts(project, nodes, handle),
            "base_url": project_base_url(handle, slug),
            "tree": tree_svc.build_tree(nodes),
        },
        headers=_cache_headers(f"{project.id}-index-{len(nodes)}"),
    )


@router.get(
    "/{handle}/{slug}/{path:path}.md", response_class=PlainTextResponse, summary="Raw Markdown with front matter"
)
async def page_markdown(handle: str, slug: str, path: str, session: AsyncSession = Depends(get_session)):
    project = await _project_or_404(session, handle, slug)
    node = await tree_svc.get_public_page(session, project, path)
    if node is None or node.page is None:
        raise NotFound("Not found.", hint="")
    body = markdown_with_front_matter(
        node.page.markdown,
        title=node.title,
        summary=node.page.summary,
        tags=list(node.page.tags),
        updated=node.updated_at,
        canonical=f"{project_base_url(handle, slug)}/{node.path}",
    )
    return PlainTextResponse(
        body, headers=_cache_headers(f"{node.id}-{node.version}"), media_type="text/markdown; charset=utf-8"
    )


@router.get("/{handle}/{slug}/{path:path}", response_class=HTMLResponse, summary="Public page as HTML")
async def page_html(handle: str, slug: str, path: str, request: Request, session: AsyncSession = Depends(get_session)):
    project = await _project_or_404(session, handle, slug)
    node = await tree_svc.get_public_page(session, project, path)
    if node is None or node.page is None:
        raise NotFound("Not found.", hint="")
    siblings = await tree_svc.list_public_pages(session, project)
    return templates.TemplateResponse(
        request,
        "public_page.html",
        {
            "project": project,
            "handle": handle,
            "node": node,
            "page": node.page,
            "base_url": project_base_url(handle, slug),
            "tree": tree_svc.build_tree(siblings),
            "canonical": f"{project_base_url(handle, slug)}/{node.path}",
        },
        headers=_cache_headers(f"{node.id}-{node.version}"),
    )


def not_found_response(request: Request) -> Response:
    return templates.TemplateResponse(request, "404.html", {}, status_code=404)
