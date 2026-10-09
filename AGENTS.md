# Rules for agents

These rules apply to every AI agent that reads, writes or reviews anything in this repository, whatever harness runs it. People follow the same rules. `README.md` explains the project and the contribution flow; this file tells you how to behave inside it.

## Who you are working with

- Enrique owns the project and is the only person who approves and merges.
- Agents are first-class users of Smart Docs and first-class contributors to this repo. Same rules, same bar.
- You never approve, merge, or push to `main`.

## Before you change anything

1. Read `pre-release-decisions/Smart-Docs--One-pager.md`.
2. Find the decision record (`SD-NNN`) and the ClickUp ticket your work implements. The record must say Agreed or Edited.
3. If no record covers the work, do not write code. Propose a decision record instead and stop.
4. Stay inside the ticket. Anything else you notice goes in a comment or a new ticket, not in the diff.

## Voice and tense

- Use second person ("you") in how-tos, guides and instructions.
- Use third person ("Smart Docs", "the API", "the worker") in descriptions and reference material.
- Never write "we", "our", "us", "I" or "let's" in repo docs. Chat with Enrique is not repo docs.
- Write in present tense and active voice.
- Name things by their real names. Do not invent labels for files, services or steps.

## Formatting rules for docs

- No em dashes and no en dashes, anywhere. Use a comma, a colon, parentheses, or start a new sentence. The plain hyphen is only for compound words and command flags.
- One idea per sentence. Keep sentences short and words plain.
- Expand an acronym the first time it appears in a file.
- Headings use sentence case. One `#` title per file. Do not skip heading levels.
- Use a list for parallel items, prose for an argument, and a table for three or more columns of facts.
- Put code, paths, flags and commands in backticks. Put commands in fenced blocks with a language tag.
- Link inside the repo with relative paths. No bare URLs.
- Markdown only. No inline HTML.
- Keep docs short. Update an existing doc before adding a new one.

## Harness rules

- `AGENTS.md` is the single source of rules. Harness-specific files (`CLAUDE.md`, `.cursorrules`, `.mcp.json`, `.claude/`) only point here or hold configuration. They never hold rules.
- Do not commit harness state: `.claude/worktrees/`, `.claude/plans/`, local settings, caches. `.gitignore` already excludes them; extend it rather than committing around it.
- When a rule names a harness command (such as `/code-review`), the command is an example. The rule is the behaviour. Use the equivalent in your harness.

## Git and pull requests

- Branch from `main` as `<type>/<ticket-id>-<short-slug>`, with type `feat`, `fix`, `docs`, `chore` or `decision`, and ticket id the id of the related ClickUp ticket.
- Commit subjects are imperative, capitalised, without a type prefix, under 72 characters. Example: `Add Smart Docs one-pager`. Add a body when the subject does not explain why.
- Never push to `main`. Never force push a branch once review has started.
- Before asking for review, run your harness's automated review pass over the branch and fix every finding. If a finding stays, say why in the pull request.
- Open the pull request with the body template from `README.md`: What, Why, Decision record and ticket, How it was verified.
- Update any doc that describes the behaviour you changed, in the same pull request.
- Reply to every review comment and push fix commits on top. Then re-request review and wait. Enrique merges.

## Decision records

- One record per decision, numbered `SD-NNN`, with a title, a status, context, options, a recommendation and consequences.
- Statuses are Proposed, Agreed, Edited and Rejected. Only Enrique sets a status.
- Never delete or rewrite an existing record. A change of mind is a new record that references the old one.

## When unsure

Stop and ask Enrique in the pull request or the ticket. Do not guess scope, do not pick between two readings on your own, and do not fill a gap with an assumption that changes the work.
