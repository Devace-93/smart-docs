# Smart Docs for agents

Smart Docs treats an agent as a user. Everything below works with one API key.

## Get a key

A person creates the key at `/app#/keys` (scopes: `read`, `write`, `publish`). It starts with `sd_` and is shown once.

## MCP (Model Context Protocol)

Remote, over Streamable HTTP, for any MCP client:

```sh
claude mcp add --transport http smart-docs https://smart-docs.3m4.net/mcp \
  --header "Authorization: Bearer sd_your_key"
```

Local, over stdio, on a machine that can reach the database (a self-hosted instance or the dev box):

```json
{
  "mcpServers": {
    "smart-docs": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/smart-docs", "sd-mcp"],
      "env": { "SD_API_KEY": "sd_your_key", "DATABASE_URL": "postgresql+psycopg://sd:sd@localhost:5433/sd" }
    }
  }
}
```

Tools: `list_projects`, `create_project`, `list_tree`, `get_page`, `create_page`, `update_page`, `move_node`, `publish_page`, `delete_node`, `search`, `get_usage`. Resource: `sd://{handle}/{project}/llms.txt`.

Conventions the tools follow:

- Structure and content are separate calls. `list_tree` returns paths and titles only; `get_page` returns one body.
- `update_page` takes `content_edit_mode`: `replace`, `append` or `prepend`, so you can add to a page without reading it.
- Every write returns `version`. Send it back as `expected_version` to avoid clobbering another writer; a `conflict` error means re-read and retry.
- Errors are JSON with `code`, `message` and `hint`. The hint names the tool to call next.
- Pass `summary` and `tags` on create or update and no model is called (agent mode, zero cost).

## REST

Same powers, same key, `Authorization: Bearer sd_...`. The spec is at `/openapi.json` and the interactive reference at `/docs`.

```sh
curl -s -H "Authorization: Bearer $SD_API_KEY" https://smart-docs.3m4.net/api/v1/projects
curl -s -X POST -H "Authorization: Bearer $SD_API_KEY" -H 'content-type: application/json' \
  https://smart-docs.3m4.net/api/v1/projects/notes/nodes \
  -d '{"title":"Hello","markdown":"# Hello","parent_path":null,"public":true}'
```

## Reading public projects without a key

| URL | Returns |
| --- | --- |
| `/{handle}/{project}/llms.txt` | Project name, description, one line per public page with its `.md` link |
| `/{handle}/{project}/llms-full.txt` | Every public page concatenated |
| `/{handle}/{project}/{path}.md` | One page as Markdown with YAML front matter |
| `/{handle}/{project}/{path}` | The same page as HTML |

Private pages return 404, never 403.

## Limits

`GET /api/v1/me/usage` (or the `get_usage` tool) shows today's counts. A 429 carries `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`. Agent mode has no limit.
