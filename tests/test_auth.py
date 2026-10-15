"""SD-008: sessions, API keys with scopes, login rate limit."""

from __future__ import annotations


async def test_api_key_scopes(client, user, project):
    r = await client.post("/api/v1/me/keys", json={"name": "ro", "scopes": ["read"]})
    assert r.status_code == 201
    key = r.json()["key"]
    assert key.startswith("sd_")
    ro = {"Authorization": "Bearer " + key}
    assert (await client.get("/api/v1/projects", headers=ro)).status_code == 200
    r = await client.post(f"/api/v1/projects/{project['slug']}/nodes", json={"title": "x"}, headers=ro)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = await client.post("/api/v1/me/keys", json={"name": "nested"}, headers=ro)
    assert r.status_code == 403
    keys = (await client.get("/api/v1/me/keys")).json()
    assert keys[0]["prefix"] == key[:10] and "key" not in keys[0]
    assert (await client.delete(f"/api/v1/me/keys/{keys[0]['id']}")).status_code == 204
    assert (await client.get("/api/v1/projects", headers=ro)).status_code == 401


async def test_wrong_password_and_rate_limit(client, user):
    import uuid

    ip = {"X-Forwarded-For": f"10.0.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}  # a fresh IP per run
    for _ in range(10):
        r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrong-password"}, headers=ip)
        assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "password123"}, headers=ip)
    assert r.status_code == 429 and r.headers["retry-after"]


async def test_usage_and_tier_validation(client, user):
    r = await client.get("/api/v1/me/usage")
    assert r.status_code == 200 and r.json()["agent"]["enabled"]
    r = await client.patch("/api/v1/me", json={"tier": "hosted"})
    assert r.status_code == 422
    r = await client.patch("/api/v1/me", json={"tier": "agent"})
    assert r.status_code == 200 and r.json()["tier"] == "agent"
