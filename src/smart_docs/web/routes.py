"""The editor shell and the landing page. All data comes from the REST API over fetch.

Login and signup live at accounts.3m4.net (SD-014): `/login` and `/signup`
only redirect there and ask to come back to the editor.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from smart_docs.api.deps import Principal, optional_principal
from smart_docs.config import get_settings
from smart_docs.web.templates import templates

router = APIRouter(include_in_schema=False)


def accounts_page(page: str) -> str:
    """`{ACCOUNTS_URL}/{page}?return_to=<the editor>`."""
    s = get_settings()
    query = urlencode({"return_to": f"{s.public_base_url.rstrip('/')}/app"})
    return f"{s.accounts_url.rstrip('/')}/{page}?{query}"


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, p: Principal | None = Depends(optional_principal)):
    return templates.TemplateResponse(
        request, "landing.html", {"account": p.account if p else None, "tiers": get_settings().tiers_available()}
    )


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/{rest:path}", response_class=HTMLResponse)
async def app_shell(request: Request, rest: str = ""):
    return templates.TemplateResponse(request, "app.html", {"tiers": get_settings().tiers_available()})


@router.get("/login")
async def login():
    return RedirectResponse(accounts_page("login"), status_code=302)


@router.get("/signup")
async def signup():
    return RedirectResponse(accounts_page("signup"), status_code=302)
