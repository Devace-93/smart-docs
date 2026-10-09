# Smart Docs

Smart Docs is an open-source knowledge base where people and AI agents are equal users. A person writes Markdown pages in a tree of projects and folders. An agent does the same through a REST API and an MCP (Model Context Protocol) server. Any page can be made public, and every public page is served as HTML for people, as raw Markdown for tools, and as `llms.txt` per project for models.

Status: planning, no code yet. Owner: Enrique.

The whole project on one page: [Smart Docs one-pager](pre-release-decisions/Smart-Docs--One-pager.md).

## Repository layout

| Path | What it holds |
| --- | --- |
| `pre-release-decisions/` | Decision records (SD-001 onward), mirrored from the live decision log until launch |
| `README.md` | This file: what the project is and how to contribute |
| `AGENTS.md` | Rules for AI agents working in this repo. People follow them too |
| `CLAUDE.md` | One line that points Claude Code at `AGENTS.md` |

Code lands here starting with epic EP-01 (Foundation).

## How decisions are made

One decision per cycle, one numbered record per decision (`SD-001` onward), never deleted. An agent drafts context, options, a recommendation and consequences. Enrique edits or comments, then sets the status: Proposed, Agreed, Edited or Rejected. Nothing is built before its record says Agreed or Edited. A change of mind later is a new record. The current list of records is in the one-pager under "How decisions are made".

## How to propose a change

1. Find the decision record and the ClickUp ticket the change implements. If there is none, propose a decision record first.
2. Branch from `main`. Name the branch `<type>/<ticket-id>-<short-slug>`, where type is one of `feat`, `fix`, `docs`, `chore` or `decision` and ticket id is the id of the related ClickUp ticket.
3. Commit in small steps. The subject line is imperative, capitalised, without a type prefix, and under 72 characters. Example: `Add Smart Docs one-pager`. Add a body when the subject does not explain why.
4. Run the automated review pass on your branch and fix or justify every finding (see Review conventions).
5. Open a pull request against `main` using the body template below.
6. After approval, the pull request is merged with a merge commit. Do not squash or rebase from the GitHub interface. Delete the branch after merge.

Nobody pushes directly to `main`. Branch protection is the intended setting for `main`; until it is enabled, treat it as if it were.

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

MIT is the proposed license (SD-009). The `LICENSE` file lands with EP-01.
