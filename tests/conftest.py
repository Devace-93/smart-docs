"""Tests run against a real Postgres (DATABASE_URL), the same engine as production.

Model calls never happen: jobs queue in Postgres and no worker runs. Sessions
are minted by `tests/sessions.py` with a throwaway Ed25519 key and the
verifier reads its JWKS from a stub, so the suite needs no accounts service
and no network (SD-013).
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LOCAL_ENABLED", "false")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("ACCOUNTS_URL", "http://accounts.test")

from smart_docs import m4session  # noqa: E402
from smart_docs.db import dispose_engine  # noqa: E402
from smart_docs.main import create_app  # noqa: E402
from tests.sessions import JWKS, mint  # noqa: E402


@pytest.fixture(autouse=True)
def stub_jwks(monkeypatch):
    """The verifier reads the test key set instead of calling the accounts service."""
    monkeypatch.setattr(m4session, "fetch_jwks", lambda url: JWKS)
    m4session.clear_cache()


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_collection_modifyitems(items):
    """Every test is async and runs under anyio, so fixtures and tests share one task."""
    for item in items:
        item.add_marker(pytest.mark.anyio)


@pytest.fixture
async def client():
    """Jobs are queued in Postgres but no worker runs, so no model is ever called."""
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            yield c
    await dispose_engine()  # every test runs in its own event loop; pooled connections cannot cross loops


@pytest.fixture
async def user(client):
    """A verified 3m4 session, sent as a bearer JWT; the first request provisions the account."""
    session = mint()
    client.headers["Authorization"] = "Bearer " + session["token"]
    r = await client.get("/api/v1/me")
    assert r.status_code == 200, r.text
    account = r.json()
    account["session"] = session
    return account


@pytest.fixture
async def project(client, user):
    r = await client.post("/api/v1/projects", json={"name": "Notes", "description": "test project"})
    assert r.status_code == 201, r.text
    return r.json()
