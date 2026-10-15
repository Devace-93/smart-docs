"""Tests run against a real Postgres (DATABASE_URL), the same engine as production.

Model calls never happen: jobs queue in Postgres and no worker runs.
"""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LOCAL_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

from smart_docs.db import dispose_engine  # noqa: E402
from smart_docs.main import create_app  # noqa: E402


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
    handle = "u" + uuid.uuid4().hex[:8]
    r = await client.post("/api/v1/auth/register", json={"email": f"{handle}@example.com", "password": "password123", "handle": handle})
    assert r.status_code == 201, r.text
    data = r.json()
    client.headers["Authorization"] = "Bearer " + data["token"]
    return data["account"]


@pytest.fixture
async def project(client, user):
    r = await client.post("/api/v1/projects", json={"name": "Notes", "description": "test project"})
    assert r.status_code == 201, r.text
    return r.json()
