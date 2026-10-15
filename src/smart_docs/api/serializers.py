"""Turn ORM rows into API shapes. URLs are computed here so every surface agrees."""

from __future__ import annotations

from smart_docs.config import get_settings
from smart_docs.models import Account, ApiKey, Node, Project


def project_base_url(handle: str, slug: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/{handle}/{slug}"


def account_out(a: Account) -> dict:
    return {
        "id": a.id,
        "email": a.email,
        "handle": a.handle,
        "tier": a.tier,
        "byok_base_url": a.byok_base_url,
        "byok_model": a.byok_model,
        "byok_configured": bool(a.byok_key_enc),
        "created_at": a.created_at,
    }


def api_key_out(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "scopes": list(k.scopes),
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
    }


def project_out(p: Project, handle: str) -> dict:
    base = project_base_url(handle, p.slug)
    return {
        "id": p.id,
        "slug": p.slug,
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at,
        "public_url": base,
        "llms_txt_url": base + "/llms.txt",
    }


def node_out(n: Node, handle: str, project_slug: str, *, with_body: bool = True) -> dict:
    d = {
        "path": n.path,
        "title": n.title,
        "kind": n.kind,
        "public": n.is_public,
        "version": n.version,
        "created_at": n.created_at,
        "updated_at": n.updated_at,
        "public_url": f"{project_base_url(handle, project_slug)}/{n.path}" if n.is_public else None,
    }
    if n.page is not None:
        d.update(
            summary=n.page.summary,
            tags=list(n.page.tags),
            enrich_status=n.page.enrich_status,
            enrich_error=n.page.enrich_error,
        )
        if with_body:
            d.update(markdown=n.page.markdown, html=n.page.html)
    return d
