"""SD-007: the MCP tools through the MCP client, over the in-process streamable HTTP transport."""

from __future__ import annotations

import json

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent


async def _mcp_session(client, key):
    """A real MCP client talking to the ASGI app through httpx."""
    import httpx

    http = httpx.AsyncClient(transport=client._transport, base_url="http://testserver", headers={"Authorization": "Bearer " + key})
    return streamable_http_client("http://testserver/mcp", http_client=http)


def _text(result) -> dict | list:
    assert not result.is_error, result
    block = result.content[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)


async def test_tools_roundtrip(client, user, project):
    key = (await client.post("/api/v1/me/keys", json={"name": "mcp"})).json()["key"]
    async with await _mcp_session(client, key) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = {t.name for t in (await session.list_tools()).tools}
        assert {"list_tree", "create_page", "update_page", "move_node", "publish_page", "search", "get_page", "get_usage"} <= names
        projects = _text(await session.call_tool("list_projects", {}))
        assert projects[0]["slug"] == project["slug"]
        created = _text(await session.call_tool("create_page", {"project": project["slug"], "title": "From MCP", "markdown": "# Hi", "summary": "s", "tags": ["t"]}))
        assert created["path"] == "from-mcp"
        updated = _text(await session.call_tool("update_page", {"project": project["slug"], "path": "from-mcp", "markdown": "more", "content_edit_mode": "append", "expected_version": 1}))
        assert updated["version"] == 2
        page = _text(await session.call_tool("get_page", {"project": project["slug"], "path": "from-mcp"}))
        assert page["markdown"] == "# Hi\n\nmore"
        err = _text(await session.call_tool("get_page", {"project": project["slug"], "path": "missing"}))
        assert err["error"]["code"] == "not_found" and err["error"]["hint"]
        pub = _text(await session.call_tool("publish_page", {"project": project["slug"], "path": "from-mcp", "public": True}))
        assert pub["public_url"].endswith("/from-mcp")
        res = await session.read_resource(f"sd://{user['handle']}/{project['slug']}/llms.txt")
        assert "[From MCP]" in res.contents[0].text


async def test_mcp_requires_key(client):
    r = await client.post("/mcp", json={}, headers={"Authorization": ""})
    assert r.status_code == 401
