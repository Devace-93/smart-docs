# Smart Docs: the project on one page

Smart Docs (SD) is an open-source knowledge base where people and AI agents are equal users. A person writes Markdown pages in a tree of projects and folders; an agent does the same through an API and an MCP server. Any page can be made public, and every public page is served for humans (HTML), for tools (raw Markdown) and for models (`llms.txt` per project).

Started 2026-09-29. Owner: Enrique. Status: planning, no code yet.

## Why it exists

1. **Prove, from the repo alone, that agents are first-class users.** An API an agent can drive, an MCP server, an eval suite, and docs written for machines, all verifiable by cloning the repo.
2. **Be Enrique's own publishing tool** for 3m4.net (`/blog`, `/projects`), and anyone else's: clone, run, self-host, with nothing owed beyond a copyright line.

## Who uses it


| User          | Enters through                                       | Can do                                      |
| ------------- | ---------------------------------------------------- | ------------------------------------------- |
| Person        | Visual editor, any Markdown editor + API             | Write, organize, publish, share, upload     |
| Agent         | MCP server (stdio or HTTP), REST API with an API key | Create, update, move, publish, search pages |
| Public reader | Three read-only routes, no auth                      | Read HTML or Markdown, fetch`llms.txt`      |

## Requirements: the whole project

Everything SD is meant to do by the end, regardless of phase.

**Content**

- Accounts, each owning projects; a project holds one tree of folders and pages, with move and reorder.
- Page body is Markdown. Images and attachments can be added to a page.
- A public toggle per page. Public pages exist in three forms at predictable URLs: HTML, raw `.md`, and a generated (never hand-written) `llms.txt` per project. Private pages return 404.
- Sharing: a page or project by link, and per-person access.
- Page versions with diff and restore; comments on pages; several people editing one page at once.

**Intelligence**

- On every save a model produces a summary and tags; the save never waits for the model.
- Semantic search inside a project, backed by one shared local embedding model.
- Four selectable model tiers per account: hosted (capped), local via Ollama (capped), bring-your-own-key, and agent mode (the calling agent's own model supplies summary and tags, zero cost).

**Agents and machines**

- A REST API that covers everything the editor can do.
- An MCP server exposing the core tools (create, update, move, publish, search) and a resource, authenticated with an SD API key, runnable over stdio for local agents and over HTTP for remote ones.
- A machine-readable description of the API and of every public project.
- An eval suite that runs with one command and whose results are committed to the repo and rendered in the README.

**Operations and trust**

- Self-hostable with one `docker compose up`: api, worker, Postgres, optional Ollama. No cloud account required; file storage defaults to local disk and switches to any S3-compatible bucket by config.
- Email and password for people (argon2), scoped long-lived API keys for agents, short-lived session tokens. A short, written list of what SD never stores.
- Rate limits on login and on model usage per tier.
- Open source under a permissive license (MIT proposed) with a removable "Built with Smart Docs" link on public pages.
- Paid plans and a custom domain per project, for the hosted instance only.
- The decision log that produced SD ships in the repo and becomes the first project in the owner's SD account at launch.

## Phases

**Phase 1: MVP backend (ship as soon as possible)**
Everything an agent or a Markdown-editor user needs, with the public HTML render as the only UI.


| Epic                          | Delivers                                                            |
| ----------------------------- | ------------------------------------------------------------------- |
| EP-01 Foundation              | uv project, FastAPI, Compose with Postgres and Ollama, health check |
| EP-02 Accounts and auth       | Register, login, API keys, rate limits on login                     |
| EP-03 Projects and page tree  | Projects CRUD, folder and page tree, move and reorder               |
| EP-04 Public surface          | Public HTML,`.md`, `llms.txt`, 404 for private pages                |
| EP-05 AI worker and tiers     | Summaries, tags, embeddings, semantic search, usage limits          |
| EP-06 MCP server              | Tools, resource,`.mcp.json` for Claude Code                         |
| EP-07 Evals and docs          | Eval suite, results in the README, decision log in the repo         |
| EP-11 Sharing and permissions | Share by link, per-person access                                    |
| EP-13 File uploads            | Images and attachments on pages                                     |

**Phase 2: Visual editor**
EP-08: a web editor on top of the API. Its tickets are planned with the backend and start once the backend tickets they depend on are done.

**Phase 3: Future**
EP-09 real-time collaboration, EP-10 versions and history, EP-12 comments, EP-14 billing and custom domains. Each gets its own decision record when it comes up.

## Architecture in one sentence

One FastAPI service owns the domain logic; the MCP server imports that same service layer in-process; every model call runs in a background worker, so a slow or dead model never blocks a save.

## How decisions are made

One decision per cycle, one numbered record per decision (SD-001 onward), never deleted. Claude drafts context, options, a recommendation and consequences; Enrique edits or comments, then sets the status: Agreed, Edited, Rejected or Proposed. Nothing is built before its record says Agreed or Edited. A change of mind later is a new record.


| Record | Topic                           | Status   |
| ------ | ------------------------------- | -------- |
| SD-001 | Goals and MVP scope             | Agreed   |
| SD-002 | Architecture at a glance        | Agreed   |
| SD-003 | Stack                           | Agreed   |
| SD-004 | Data model                      | Agreed   |
| SD-005 | LLM tiers and rate limits       | Agreed   |
| SD-006 | Public surface and machine docs | Agreed   |
| SD-007 | MCP server                      | Agreed   |
| SD-008 | Auth and security               | Agreed   |
| SD-009 | License and self-hosting        | Agreed   |
| SD-010 | Evals                           | Agreed   |
| SD-011 | Build night plan                | Agreed   |
| SD-012 | File storage                    | Agreed   |

## Where things live

- Decisions: this folder (`pre-release-decisions/`), mirrored from the live decision log until launch.
- Work tracking: ClickUp space "Smart Docs", one list per epic; a ticket exists only for agreed work.
- Code: this repository.
