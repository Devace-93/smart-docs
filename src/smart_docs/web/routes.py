"""The editor shell and the landing page. All data comes from the REST API over fetch."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.api.deps import Principal, optional_principal
from smart_docs.config import get_settings
from smart_docs.db import get_session
from smart_docs.web.templates import templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, p: Principal | None = Depends(optional_principal)):
    return templates.TemplateResponse(
        request, "landing.html", {"account": p.account if p else None, "tiers": get_settings().tiers_available()}
    )


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/{rest:path}", response_class=HTMLResponse)
async def app_shell(request: Request, rest: str = "", session: AsyncSession = Depends(get_session)):
    return templates.TemplateResponse(request, "app.html", {"tiers": get_settings().tiers_available()})


@router.get("/login", response_class=HTMLResponse)
@router.get("/signup", response_class=HTMLResponse)
async def auth_page(request: Request):
    return templates.TemplateResponse(request, "app.html", {"tiers": get_settings().tiers_available()})
