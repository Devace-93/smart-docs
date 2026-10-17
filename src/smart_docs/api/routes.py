"""REST API v1. Everything the editor and the MCP server can do is reachable here."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.api import schemas
from smart_docs.api.deps import Principal, current_principal, current_principal_unverified
from smart_docs.api.serializers import account_out, api_key_out, node_out, project_out
from smart_docs.config import get_settings
from smart_docs.db import get_session
from smart_docs.llm.client import ollama_status
from smart_docs.services import accounts as accounts_svc
from smart_docs.services import projects as projects_svc
from smart_docs.services import search as search_svc
from smart_docs.services import tree as tree_svc
from smart_docs.services.usage import usage_report
from smart_docs.worker.app import enqueue_enrich

router = APIRouter(prefix="/api/v1")


def has_body(markdown: str) -> bool:
    """A page with only a heading is not worth a model call; the first real save queues it."""
    lines = [ln.strip() for ln in (markdown or "").splitlines() if ln.strip()]
    return any(not ln.startswith("#") for ln in lines)


ERR = {401: {"model": schemas.ErrorOut}, 404: {"model": schemas.ErrorOut}, 409: {"model": schemas.ErrorOut}}


# ---- health -----------------------------------------------------------------


@router.get("/health", tags=["meta"])
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    s = get_settings()
    db_ok = True
    try:
        await session.execute(tree_svc.text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "ok": db_ok,
        "instance": s.instance_name,
        "db": "ok" if db_ok else "down",
        "tiers": s.tiers_available(),
        "ollama": await ollama_status() if s.local_enabled else {"reachable": False, "disabled": True},
        "signups_open": s.signups_open,
    }


# ---- me ---------------------------------------------------------------------
# Sign up and log in happen at accounts.3m4.net (SD-013); the session arrives
# as the `3m4_session` cookie or a bearer JWT and the account is provisioned
# from it on first sight.


@router.get("/me", response_model=schemas.AccountOut, tags=["me"], responses=ERR)
async def me(p: Principal = Depends(current_principal_unverified)):
    """Who am I. Answers for an unverified e-mail too, so the editor can show the banner."""
    return account_out(p.account, p.identity)


@router.patch("/me", response_model=schemas.AccountOut, tags=["me"], responses=ERR)
async def patch_me(
    body: schemas.AccountPatch, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    p.require("write")
    account = await accounts_svc.update_settings(
        session,
        p.account,
        tier=body.tier,
        byok_base_url=body.byok_base_url,
        byok_model=body.byok_model,
        byok_key=body.byok_key,
    )
    await session.commit()
    return account_out(account)


@router.get("/me/usage", tags=["me"], responses=ERR, summary="Today's model usage and the limits that apply")
async def my_usage(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)) -> dict:
    return await usage_report(session, p.account)


@router.get("/me/keys", response_model=list[schemas.ApiKeyOut], tags=["me"], responses=ERR)
async def list_keys(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    return [api_key_out(k) for k in await accounts_svc.list_api_keys(session, p.account)]


@router.post("/me/keys", response_model=schemas.ApiKeyCreated, status_code=201, tags=["me"], responses=ERR)
async def create_key(
    body: schemas.ApiKeyIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    if p.via != "session":
        from smart_docs.errors import Forbidden

        raise Forbidden("API keys can only be created from a logged-in session.")
    key, plaintext = await accounts_svc.create_api_key(session, p.account, name=body.name, scopes=body.scopes)
    await session.commit()
    return {**api_key_out(key), "key": plaintext}


@router.delete("/me/keys/{key_id}", status_code=204, tags=["me"], responses=ERR)
async def revoke_key(
    key_id: uuid.UUID, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    await accounts_svc.revoke_api_key(session, p.account, key_id)
    await session.commit()
    return Response(status_code=204)


# ---- projects ---------------------------------------------------------------


@router.get("/projects", response_model=list[schemas.ProjectOut], tags=["projects"], responses=ERR)
async def list_projects(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    p.require("read")
    return [project_out(x, p.account.handle) for x in await projects_svc.list_projects(session, p.account)]


@router.post("/projects", response_model=schemas.ProjectOut, status_code=201, tags=["projects"], responses=ERR)
async def create_project(
    body: schemas.ProjectIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    p.require("write")
    project = await projects_svc.create_project(
        session, p.account, name=body.name, slug=body.slug, description=body.description
    )
    await session.commit()
    return project_out(project, p.account.handle)


@router.get("/projects/{slug}", response_model=schemas.ProjectOut, tags=["projects"], responses=ERR)
async def get_project(
    slug: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    p.require("read")
    return project_out(await projects_svc.get_project(session, p.account, slug), p.account.handle)


@router.patch("/projects/{slug}", response_model=schemas.ProjectOut, tags=["projects"], responses=ERR)
async def patch_project(
    slug: str,
    body: schemas.ProjectPatch,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("write")
    project = await projects_svc.get_project(session, p.account, slug)
    await session.commit()
    return project_out(
        await projects_svc.update_project(session, project, name=body.name, description=body.description),
        p.account.handle,
    )


@router.delete("/projects/{slug}", status_code=204, tags=["projects"], responses=ERR)
async def delete_project(
    slug: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    p.require("write")
    await projects_svc.delete_project(session, await projects_svc.get_project(session, p.account, slug))
    await session.commit()
    return Response(status_code=204)


# ---- tree and nodes ---------------------------------------------------------


@router.get(
    "/projects/{slug}/tree",
    response_model=list[schemas.TreeNode],
    tags=["nodes"],
    responses=ERR,
    summary="The project tree as nested JSON, without page bodies",
)
async def get_tree(
    slug: str,
    under: str | None = None,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("read")
    project = await projects_svc.get_project(session, p.account, slug)
    nodes = await tree_svc.list_nodes(session, project, under=under)
    return tree_svc.build_tree(nodes, root=under.strip("/") if under else None)


@router.post("/projects/{slug}/nodes", response_model=schemas.NodeOut, status_code=201, tags=["nodes"], responses=ERR)
async def create_node(
    slug: str,
    body: schemas.NodeIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("write")
    if body.public:
        p.require("publish")
    project = await projects_svc.get_project(session, p.account, slug)
    node = await tree_svc.create_node(
        session,
        project,
        kind=body.kind,
        title=body.title,
        parent_path=body.parent_path,
        slug=body.slug,
        markdown=body.markdown,
        summary=body.summary,
        tags=body.tags,
        is_public=body.public,
    )
    await session.commit()
    if node.kind == "page" and has_body(body.markdown):
        await enqueue_enrich(node.id)
    return node_out(node, p.account.handle, project.slug)


@router.get("/projects/{slug}/nodes/{path:path}", response_model=schemas.NodeOut, tags=["nodes"], responses=ERR)
async def get_node(
    slug: str, path: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    p.require("read")
    project = await projects_svc.get_project(session, p.account, slug)
    return node_out(await tree_svc.get_node(session, project, path), p.account.handle, project.slug)


@router.patch("/projects/{slug}/nodes/{path:path}", response_model=schemas.NodeOut, tags=["nodes"], responses=ERR)
async def patch_node(
    slug: str,
    path: str,
    body: schemas.NodePatch,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("write")
    project = await projects_svc.get_project(session, p.account, slug)
    node = await tree_svc.get_node(session, project, path)
    expected = body.expected_version
    if expected is None and request.headers.get("if-match"):
        expected = int(request.headers["if-match"].strip('"'))
    node = await tree_svc.update_page(
        session,
        node,
        markdown=body.markdown,
        title=body.title,
        summary=body.summary,
        tags=body.tags,
        expected_version=expected,
        content_edit_mode=body.content_edit_mode,
    )
    await session.commit()
    if node.kind == "page" and body.markdown is not None and has_body(node.page.markdown if node.page else ""):
        await enqueue_enrich(node.id)
    return node_out(node, p.account.handle, project.slug)


@router.post("/projects/{slug}/nodes/{path:path}/move", response_model=schemas.NodeOut, tags=["nodes"], responses=ERR)
async def move_node(
    slug: str,
    path: str,
    body: schemas.MoveIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("write")
    project = await projects_svc.get_project(session, p.account, slug)
    node = await tree_svc.get_node(session, project, path)
    node = await tree_svc.move_node(
        session, project, node, new_parent_path=body.new_parent_path, position=body.position, new_slug=body.new_slug
    )
    await session.commit()
    return node_out(node, p.account.handle, project.slug, with_body=False)


@router.post(
    "/projects/{slug}/nodes/{path:path}/publish", response_model=schemas.NodeOut, tags=["nodes"], responses=ERR
)
async def publish_node(
    slug: str,
    path: str,
    body: schemas.PublishIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("publish")
    project = await projects_svc.get_project(session, p.account, slug)
    node = await tree_svc.get_node(session, project, path)
    node = await tree_svc.set_public(session, node, body.public, expected_version=body.expected_version)
    await session.commit()
    return node_out(node, p.account.handle, project.slug, with_body=False)


@router.delete("/projects/{slug}/nodes/{path:path}", status_code=204, tags=["nodes"], responses=ERR)
async def delete_node(
    slug: str, path: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
):
    p.require("write")
    project = await projects_svc.get_project(session, p.account, slug)
    node = await tree_svc.get_node(session, project, path)
    await tree_svc.delete_node(session, project, node)
    await session.commit()
    return Response(status_code=204)


# ---- render -----------------------------------------------------------------


class RenderIn(schemas.BaseModel):
    markdown: str


@router.post("/render", tags=["meta"], summary="Render Markdown to the same sanitized HTML public pages use")
async def render(body: RenderIn, p: Principal = Depends(current_principal)) -> dict:
    from smart_docs.services.render import render_html

    return {"html": render_html(body.markdown)}


# ---- search -----------------------------------------------------------------


@router.get(
    "/projects/{slug}/search",
    response_model=list[schemas.SearchHit],
    tags=["search"],
    responses=ERR,
    summary="Semantic search over the project's pages",
)
async def search(
    slug: str,
    q: str,
    k: int = 10,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    p.require("read")
    project = await projects_svc.get_project(session, p.account, slug)
    return await search_svc.search(session, project, q, k=k)
