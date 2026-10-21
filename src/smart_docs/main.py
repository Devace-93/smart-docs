"""FastAPI application: REST API, MCP over HTTP, the editor shell and the public pages."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from smart_docs.api.routes import router as api_router
from smart_docs.config import get_settings
from smart_docs.db import dispose_engine
from smart_docs.errors import NotFound, RateLimited, SDError
from smart_docs.mcp.http import build_mcp_asgi_app
from smart_docs.public.routes import not_found_response
from smart_docs.public.routes import router as public_router
from smart_docs.web.routes import router as web_router
from smart_docs.web.templates import STATIC_DIR
from smart_docs.worker.app import app as queue_app

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the job queue connection and the MCP session manager for the life of the process."""
    try:
        async with queue_app.open_async(), app.state.mcp_lifespan():
            yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    """Build the application. Each call owns a fresh MCP session manager, which can only start once."""
    s = get_settings()
    mcp_asgi, mcp_lifespan = build_mcp_asgi_app()
    app = FastAPI(
        title=s.instance_name,
        version="0.1.0",
        description=(
            "Smart Docs REST API. People and agents use the same endpoints. "
            "Authenticate with `Authorization: Bearer sd_<API key>`, or with a 3m4 accounts session "
            "(the `3m4_session` cookie from accounts.3m4.net, also accepted as a bearer JWT). "
            "Public pages live at `/{handle}/{project}/{path}` with `.md` and `llms.txt` variants."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.exception_handler(SDError)
    async def sd_error(request: Request, exc: SDError):
        wants_html = request.url.path.startswith(("/app", "/login", "/signup")) or (
            not request.url.path.startswith("/api/") and "text/html" in request.headers.get("accept", "")
        )
        if isinstance(exc, NotFound) and wants_html:
            return not_found_response(request)
        headers = exc.headers() if isinstance(exc, RateLimited) else {}
        return JSONResponse(exc.to_dict(), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"code": "invalid", "message": "Request validation failed.", "hint": "", "errors": exc.errors()},
            status_code=422,
        )

    @app.get("/robots.txt", include_in_schema=False)
    async def robots():
        return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api/\n")

    @app.get("/llms.txt", include_in_schema=False)
    async def instance_llms():
        return PlainTextResponse(
            f"# {s.instance_name}\n\n> A Smart Docs instance. Every public project publishes its own llms.txt at "
            f"{s.public_base_url.rstrip('/')}/{{handle}}/{{project}}/llms.txt.\n\n"
            f"- [API reference]({s.public_base_url.rstrip('/')}/openapi.json)\n"
            f"- [How agents use this instance]({s.public_base_url.rstrip('/')}/docs)\n"
        )

    @app.get("/og-image.png", include_in_schema=False)
    async def og_image():
        from fastapi.responses import FileResponse

        return FileResponse(STATIC_DIR / "og-image.png", media_type="image/png")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.mcp_lifespan = mcp_lifespan
    app.add_route("/mcp", mcp_asgi, methods=["GET", "POST", "DELETE"], include_in_schema=False)
    app.include_router(api_router)
    app.include_router(web_router)
    app.include_router(public_router)
    return app


app = create_app()
