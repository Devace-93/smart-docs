"""SD-006 public surface: three forms per page, 404 for private, generated llms.txt."""

from __future__ import annotations


async def test_public_forms(client, user, project):
    slug, handle = project["slug"], user["handle"]
    node = (await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": "Hello", "markdown": "# Hello\n\nWorld <script>alert(1)</script>", "summary": "A greeting.", "tags": ["hi"]})).json()
    anon = {"Authorization": ""}
    assert (await client.get(f"/{handle}/{slug}/hello", headers=anon)).status_code == 404
    assert (await client.get(f"/{handle}/{slug}/hello.md", headers=anon)).status_code == 404
    r = await client.post(f"/api/v1/projects/{slug}/nodes/hello/publish", json={"public": True})
    assert r.status_code == 200 and r.json()["public_url"] == f"http://testserver/{handle}/{slug}/hello"
    html = await client.get(f"/{handle}/{slug}/hello", headers=anon)
    assert html.status_code == 200 and "<script>" not in html.text and "World" in html.text
    assert html.headers["etag"] and "max-age" in html.headers["cache-control"]
    md = await client.get(f"/{handle}/{slug}/hello.md", headers=anon)
    assert md.status_code == 200 and md.text.startswith("---\ntitle: \"Hello\"") and "canonical: http://testserver" in md.text
    llms = await client.get(f"/{handle}/{slug}/llms.txt", headers=anon)
    assert llms.status_code == 200 and f"- [Hello](http://testserver/{handle}/{slug}/hello.md): A greeting." in llms.text
    full = await client.get(f"/{handle}/{slug}/llms-full.txt", headers=anon)
    assert "# Hello" in full.text
    assert (await client.get(f"/{handle}/{slug}", headers=anon)).status_code == 200
    assert (await client.get(f"/{handle}/nope/llms.txt", headers=anon)).status_code == 404
    assert node["version"] == 1


async def test_sitemap_lists_only_public_pages(client, user, project):
    slug, handle = project["slug"], user["handle"]
    for title in ("Shown", "Hidden"):
        r = await client.post(f"/api/v1/projects/{slug}/nodes", json={"title": title, "markdown": f"# {title}"})
        assert r.status_code == 201, r.text
    assert (await client.post(f"/api/v1/projects/{slug}/nodes/shown/publish", json={"public": True})).status_code == 200
    anon = {"Authorization": ""}
    res = await client.get("/sitemap.xml", headers=anon)
    assert res.status_code == 200 and "xml" in res.headers["content-type"]
    assert "<loc>http://testserver/</loc>" in res.text
    assert f"<loc>http://testserver/{handle}/{slug}</loc>" in res.text
    assert f"<loc>http://testserver/{handle}/{slug}/shown</loc>" in res.text
    assert "hidden" not in res.text
    robots = await client.get("/robots.txt", headers=anon)
    assert "Sitemap: http://testserver/sitemap.xml" in robots.text


async def test_reserved_handle_is_404(client):
    assert (await client.get("/api/x/llms.txt")).status_code == 404
