# Smart Docs

Smart Docs is an open-source knowledge base where people and AI agents are equal users. A person writes Markdown pages in a tree of projects and folders. An agent does the same through a REST API and an MCP (Model Context Protocol) server. Any page can be made public, and every public page is served as HTML for people, as raw Markdown for tools, and as `llms.txt` per project for models.

Status: minimum viable product (MVP) running at [smart-docs.3m4.net](https://smart-docs.3m4.net). Owner: Enrique.

The whole project on one page: [Smart Docs one-pager](pre-release-decisions/Smart-Docs--One-pager.md). How agents use it: [docs/for-agents.md](docs/for-agents.md). Why it is built this way: [docs/decisions/](docs/decisions/README.md).

## Run it

```sh
git clone https://github.com/Devace-93/smart-docs.git && cd smart-docs
cp .env.example .env            # defaults work locally; change the secrets before exposing it
docker compose --profile local up -d
open http://localhost:8000
```

`--profile local` adds Ollama and pulls `qwen2.5:3b` (summaries, tags) and `nomic-embed-text` (search). Without it, set `LOCAL_ENABLED=false` and new accounts use agent mode, where the agent supplies summary and tags. Hosted (DeepSeek) and bring-your-own-key tiers are env flags, see `.env.example`.

Four containers: `api` (FastAPI, the editor, public pages, `/mcp`), `worker` (summaries, tags, embeddings), `db` (Postgres 16 + pgvector), `ollama` (optional). No Redis, no cloud account, no telemetry.

## Use it

| Door | Where |
| --- | --- |
| Editor | `/app` (projects, tree, Markdown editor with preview, publish, search, API keys, usage, tier) |
| REST API | `/api/v1`, spec at `/openapi.json`, reference at `/docs` |
| MCP over HTTP | `/mcp` with `Authorization: Bearer sd_...` |
| MCP over stdio | `uv run sd-mcp` with `SD_API_KEY` and `DATABASE_URL` |
| Public page | `/{handle}/{project}/{path}`, plus `.md`, and `/{handle}/{project}/llms.txt` |

Connect Claude Code to the public instance:

```sh
claude mcp add --transport http smart-docs https://smart-docs.3m4.net/mcp \
  --header "Authorization: Bearer sd_your_key"
```

Tools: `list_projects`, `create_project`, `list_tree`, `get_page`, `create_page`, `update_page` (replace, append or prepend), `move_node`, `publish_page`, `delete_node`, `search`, `get_usage`. Resource: `sd://{handle}/{project}/llms.txt`.

## Develop

```sh
uv sync --all-groups
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile local up -d db ollama ollama-pull
sed -i 's#@db:5432#@localhost:5433#; s#http://ollama:#http://localhost:#' .env
uv run sd migrate
uv run sd serve --reload        # http://localhost:8000
uv run sd worker                # in a second terminal
uv run pytest                   # tests hit the real Postgres
uv run sd-evals --key sd_...    # search eval, writes evals/results/
```

`sd` also has `create-user`, `reset-password` and `seed <folder> --handle h --project p --public` (imports a folder of Markdown files as pages).

## Repository layout

| Path | What it holds |
| --- | --- |
| `src/smart_docs/` | The application: `api/` (REST), `services/` (domain logic), `worker/` (jobs), `llm/` (providers), `mcp/` (server), `public/` (HTML, Markdown, llms.txt), `web/` (editor templates and static files) |
| `migrations/` | Alembic migrations; no table is created outside one |
| `tests/` | pytest against a real Postgres, including the MCP tools through the MCP client |
| `evals/` | Eval data, the `sd-evals` runner and committed results |
| `docs/decisions/` | Decision records SD-001 onward, mirrored from the live decision log |
| `docs/for-agents.md` | How to point an agent at an instance |
| `deploy/` | Production overlay, Caddy snippet, runbook, backup script |
| `pre-release-decisions/` | The one-pager written before any code |
| `AGENTS.md` | Rules for AI agents working in this repo. People follow them too |
| `CLAUDE.md` | One line that points Claude Code at `AGENTS.md` |

## Evals

`uv run sd-evals` seeds the docs listed in `evals/data/pages.txt`, waits for embeddings and runs the search queries in `evals/data/search_queries.json`. Results land in `evals/results/<timestamp>-<tier>.json`. Failures go to [docs/evals-failures.md](docs/evals-failures.md). Summary and tag evals (SD-010) are not automated yet.

## How decisions are made

One decision per cycle, one numbered record per decision (`SD-001` onward), never deleted. An agent drafts context, options, a recommendation and consequences. Enrique edits or comments, then sets the status: Proposed, Agreed, Edited or Rejected. A change of mind later is a new record. On 2026-10-15 the rule changed to "build first, then revisit": the MVP was built in one pass against SD-001 to SD-011 and the records get revisited against the running code.

## How to propose a change

1. Find the decision record and the ClickUp ticket the change implements. If there is none, propose a decision record first.
2. Branch from `main`. Name the branch `<type>/<ticket-id>-<short-slug>`, where type is one of `feat`, `fix`, `docs`, `chore` or `decision` and ticket id is the id of the related ClickUp ticket.
3. Commit in small steps. The subject line is imperative, capitalised, without a type prefix, and under 72 characters. Add a body when the subject does not explain why.
4. Run the automated review pass on your branch and fix or justify every finding (see Review conventions).
5. Open a pull request against `main` using the body template below.
6. After approval, the pull request is merged with a merge commit. Do not squash or rebase from the GitHub interface. GitHub deletes the branch after merge.

Nobody pushes directly to `main`. A GitHub ruleset on `main` enforces this. Every change arrives through a pull request. Merges use a merge commit. Every review thread is resolved before merging. Force pushes and branch deletion are blocked. Nobody can bypass the ruleset, not even the owner.

### Pull request body template

```markdown
## What

One or two sentences on what changes.

## Why

The problem this solves, in plain words.

## Decision record and ticket

SD-NNN, ClickUp ticket link.

## How it was verified

Commands run, tests added, pages checked by hand.
```

## Review conventions

**Before asking for review.** The author runs an automated review pass over the branch and resolves every finding or explains in the pull request why it stays. In Claude Code this is `/code-review`; another harness uses its equivalent. The rule is the review, not the command.

**Who approves.** Enrique is the only approver. Agents open pull requests and respond to review, but never approve and never merge.

**What a reviewer checks.**

- The change implements a record whose status is Agreed or Edited, and stays inside the ticket's scope.
- Docs that describe the changed behaviour are updated in the same pull request.
- No secrets, tokens or personal data in the diff.
- Writing follows the rules in `AGENTS.md`.
- Tests or a manual check cover the change, and the pull request says which.

**Responding to review.** Reply to every comment. Push fix commits on top; do not force push once review has started. Re-request review when all threads are addressed.

## Writing conventions

Every document in this repo follows the voice and formatting rules in [AGENTS.md](AGENTS.md). The rules were written for agents, and they apply to people too.

## Work tracking

Work is tracked in the ClickUp space "Smart Docs", with one list per epic. A ticket exists only for work whose decision record is Agreed or Edited. Every pull request links its ticket.

## License

MIT, see [LICENSE](LICENSE). The "Built with Smart Docs" footer on public pages is a polite ask: set `FOOTER_TEXT=` to remove it.
