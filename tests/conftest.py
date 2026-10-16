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
# Without DATABASE_URL the tests use the db container from docker-compose.dev.yml (port 5433) and their own database.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://sd:sd@localhost:5433/sd_test")

from smart_docs.config import get_settings  # noqa: E402
from smart_docs.db import dispose_engine  # noqa: E402
from smart_docs.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    """Create the test database if it is missing, then apply migrations (a no-op when already current)."""
    import psycopg
    from psycopg import sql

    from smart_docs.cli import cmd_migrate

    url = psycopg.conninfo.conninfo_to_dict(get_settings().sync_database_url)
    name = url.pop("dbname")
    with psycopg.connect(**url, dbname="postgres", autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    cmd_migrate(None)


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
