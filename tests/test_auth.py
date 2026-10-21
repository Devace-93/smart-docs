"""SD-014 shared identity (sessions from accounts.3m4.net) and SD-008 API keys with scopes."""

from __future__ import annotations

import uuid

from smart_docs.config import get_settings
from tests.sessions import mint


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
    r = await client.get("/api/v1/projects", headers=ro)
    assert r.status_code == 401 and r.json()["code"] == "invalid_session"


async def test_session_provisions_account_once(client):
    session = mint(name="Ana López")
    bearer = {"Authorization": "Bearer " + session["token"]}
    r = await client.get("/api/v1/me", headers=bearer)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["email"] == session["email"] and me["handle"] == session["handle"]
    assert me["email_verified"] is True and me["name"] == "Ana López"
    assert me["avatar_url"].endswith(f"/avatars/{session['sub']}?v=0")
    # The same person again (a new session id, same sub) is the same account.
    again = mint(sub=session["sub"], handle=session["handle"], email=session["email"])
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + again["token"]})
    assert r.json()["id"] == me["id"]
    # The cookie works like the bearer header.
    client.cookies.set("3m4_session", session["token"])
    assert (await client.get("/api/v1/me")).json()["id"] == me["id"]
    client.cookies.clear()


async def test_handle_and_email_follow_the_claims(client, user, project):
    session = user["session"]
    anon = {"Authorization": ""}
    await client.post(f"/api/v1/projects/{project['slug']}/nodes", json={"title": "Hello", "markdown": "# Hello"})
    await client.post(f"/api/v1/projects/{project['slug']}/nodes/hello/publish", json={"public": True})
    assert (await client.get(f"/{user['handle']}/{project['slug']}/hello", headers=anon)).status_code == 200

    renamed = mint(sub=session["sub"], handle=session["handle"] + "-new", email="new-" + session["email"])
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + renamed["token"]})
    assert r.status_code == 200 and r.json()["id"] == user["id"]
    assert r.json()["handle"] == session["handle"] + "-new" and r.json()["email"] == "new-" + session["email"]
    # Public URLs moved with the handle (the accounts profile page warns about that).
    assert (await client.get(f"/{session['handle']}-new/{project['slug']}/hello", headers=anon)).status_code == 200
    assert (await client.get(f"/{session['handle']}/{project['slug']}/hello", headers=anon)).status_code == 404


async def test_unverified_email_is_gated(client):
    session = mint(verified=False)
    bearer = {"Authorization": "Bearer " + session["token"]}
    r = await client.get("/api/v1/me", headers=bearer)
    assert r.status_code == 200 and r.json()["email_verified"] is False
    r = await client.post("/api/v1/projects", json={"name": "Nope"}, headers=bearer)
    assert r.status_code == 403 and r.json()["code"] == "email_unverified"
    r = await client.get("/api/v1/projects", headers=bearer)
    assert r.status_code == 403 and r.json()["code"] == "email_unverified"


async def test_session_errors(client):
    r = await client.get("/api/v1/me")
    assert r.status_code == 401 and r.json()["code"] == "no_session"
    expired = mint(ttl=-120)
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + expired["token"]})
    assert r.status_code == 401 and r.json()["code"] == "session_expired"
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_session"
    forged = mint()
    tail = "AAAA" if not forged["token"].endswith("AAAA") else "BBBB"
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + forged["token"][:-4] + tail})
    assert r.status_code == 401 and r.json()["code"] == "invalid_session"


async def test_closed_signups_refuse_new_identities(client, user, monkeypatch):
    monkeypatch.setattr(get_settings(), "signups_open", False)
    # Known account: still fine.
    assert (await client.get("/api/v1/me")).status_code == 200
    # Unknown 3m4 user: no row gets created.
    stranger = mint()
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + stranger["token"]})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"


async def test_login_and_signup_redirect_to_accounts(client):
    r = await client.get("/login", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "http://accounts.test/login?return_to=http%3A%2F%2Ftestserver%2Fapp"
    r = await client.get("/signup", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("http://accounts.test/signup?return_to=")
    assert (await client.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "x"})).status_code in (404, 405)


async def test_usage_and_tier_validation(client, user):
    r = await client.get("/api/v1/me/usage")
    assert r.status_code == 200 and r.json()["agent"]["enabled"]
    r = await client.patch("/api/v1/me", json={"tier": "hosted"})
    assert r.status_code == 422
    r = await client.patch("/api/v1/me", json={"tier": "agent"})
    assert r.status_code == 200 and r.json()["tier"] == "agent"
    assert uuid.UUID(r.json()["id"])
