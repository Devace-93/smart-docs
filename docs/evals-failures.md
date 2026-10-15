# Eval failures

One line per failure, newest first. The failures are the interesting part.

- 2026-10-15 search, local tier (nomic-embed-text), 7 pages / 15 queries: hit@1 0.80, hit@3 0.87, MRR 0.83, below the 0.9 hit@3 bar. Misses: "what does agent mode mean for summaries and tags" ranked docs/for-agents.md and SD-007 above SD-005 (all three describe agent mode, the label is debatable); "what does a 429 response contain" ranked SD-007, SD-008, SD-006 above docs/for-agents.md (the headers are spelled out in SD-005 too). Next: more specific queries and the 15 pages SD-010 asks for.

- 2026-10-15: the search eval covers 7 pages and 15 queries, not the 15 pages and 30 queries SD-010 asks for, and the README table is not regenerated yet. Summary and tag evals (LLM judge, Jaccard) are not automated.
