# Decision records

One record per decision, numbered SD-001 onward, never deleted. The live log is a Claude doc; these files mirror it at the time the MVP was built (2026-10-15). A change of mind is a new record.

| Record | Topic |
|---|---|
| [SD-001](sd-001.md) | Goals and MVP scope |
| [SD-002](sd-002.md) | Architecture at a glance |
| [SD-003](sd-003.md) | Stack |
| [SD-004](sd-004.md) | Data model |
| [SD-005](sd-005.md) | LLM tiers and rate limits |
| [SD-006](sd-006.md) | Public surface and machine docs |
| [SD-007](sd-007.md) | MCP server |
| [SD-008](sd-008.md) | Auth and security |
| [SD-009](sd-009.md) | License and self-hosting |
| [SD-010](sd-010.md) | Evals |
| [SD-011](sd-011.md) | Build night plan |
| [SD-012](sd-012.md) | File storage |
| [SD-013](sd-013.md) | Shared 3m4 chrome |

Built on 2026-10-15 with the rule changed to "build first, revisit the decisions after": everything in SD-003 to SD-010 is implemented except BYOK key storage (built), Jev reranking (not built), file uploads (SD-012, not built) and sharing (EP-11, not built).
