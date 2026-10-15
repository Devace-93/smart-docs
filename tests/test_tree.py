"""SD-004 tree rules: unique sibling slugs, materialized paths, moves, versions, soft delete."""

from __future__ import annotations


async def test_create_and_nest(client, project):
    slug = project["slug"]
    r = await client.post(f"/api/v1/projects/{slug}/nodes", json={"kind": "folder", "title": "Docs"})
    assert r.status_code == 201 and r.json()["path"] == "docs"
    r = await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "API Auth", "parent_path": "docs", "markdown": "# Auth\n\nTokens."})
    assert r.status_code == 201
    node = r.json()
    assert node["path"] == "docs/api-auth" and node["version"] == 1 and node["html"].startswith("<h1>")
    # Same title under the same parent gets a suffix.
    r = await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "API Auth", "parent_path": "docs"})
    assert r.json()["path"] == "docs/api-auth-2"
    tree = (await client.get(f"/api/v1/projects/{slug}/tree")).json()
    assert tree[0]["path"] == "docs" and [c["path"] for c in tree[0]["children"]] == ["docs/api-auth", "docs/api-auth-2"]


async def test_update_versions_and_conflict(client, project):
    slug = project["slug"]
    node = (await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "Page", "markdown": "one"})).json()
    r = await client.patch(f"/api/v1/projects/{slug}/nodes/{node['path']}", json={"markdown": "two", "expected_version": 1})
    assert r.status_code == 200 and r.json()["version"] == 2
    r = await client.patch(f"/api/v1/projects/{slug}/nodes/{node['path']}", json={"markdown": "three", "expected_version": 1})
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    r = await client.patch(f"/api/v1/projects/{slug}/nodes/{node['path']}", json={"markdown": "## More", "content_edit_mode": "append"})
    assert r.json()["markdown"] == "two\n\n## More"


async def test_move_rewrites_subtree(client, project):
    slug = project["slug"]
    await client.post(f"/api/v1/projects/{slug}/nodes", json={"kind": "folder", "title": "drafts"})
    await client.post(f"/api/v1/projects/{slug}/nodes", json={"kind": "folder", "title": "docs"})
    await client.post(f"/api/v1/projects/{slug}/nodes", json={"kind": "folder", "title": "api", "parent_path": "drafts"})
    await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "auth", "parent_path": "drafts/api"})
    r = await client.post(f"/api/v1/projects/{slug}/nodes/drafts/api/move", json={"new_parent_path": "docs"})
    assert r.status_code == 200 and r.json()["path"] == "docs/api"
    r = await client.get(f"/api/v1/projects/{slug}/nodes/docs/api/auth")
    assert r.status_code == 200
    assert (await client.get(f"/api/v1/projects/{slug}/nodes/drafts/api/auth")).status_code == 404
    r = await client.post(f"/api/v1/projects/{slug}/nodes/docs/move", json={"new_parent_path": "docs/api"})
    assert r.status_code == 422


async def test_soft_delete_and_reuse_path(client, project):
    slug = project["slug"]
    await client.post(f"/api/v1/projects/{slug}/nodes", json={"kind": "folder", "title": "f"})
    await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "p", "parent_path": "f"})
    assert (await client.delete(f"/api/v1/projects/{slug}/nodes/f")).status_code == 204
    assert (await client.get(f"/api/v1/projects/{slug}/nodes/f/p")).status_code == 404
    r = await client.post(f"/api/v1/projects/{slug}/nodes", json={"kind": "folder", "title": "f"})
    assert r.status_code == 201 and r.json()["path"] == "f"


async def test_agent_mode_skips_model(client, project):
    slug = project["slug"]
    r = await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "Agent page", "markdown": "body", "summary": "A page written by an agent.", "tags": ["Agent", "MCP test"]})
    node = r.json()
    assert node["enrich_status"] == "agent" and node["tags"] == ["agent", "mcp-test"]
