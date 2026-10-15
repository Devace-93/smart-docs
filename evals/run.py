"""`uv run sd-evals`: the search eval from SD-010, against a running instance.

Seeds the pages listed in evals/data/pages.txt into a project, waits for their embeddings, runs
the queries in evals/data/search_queries.json and writes evals/results/<timestamp>-<provider>.json.
Summary and tag evals need a model judge and are not automated yet (see docs/evals-failures.md).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
ROOT = HERE.parent


def first_heading(markdown: str) -> str | None:
    m = re.search(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", markdown, re.MULTILINE)
    return m.group(1).strip() if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("SD_URL", "http://localhost:8000"))
    ap.add_argument("--key", default=os.environ.get("SD_API_KEY"))
    ap.add_argument("--project", default="sd-evals")
    ap.add_argument("--wait", type=int, default=600, help="seconds to wait for embeddings")
    args = ap.parse_args()
    if not args.key:
        sys.exit("SD_API_KEY (or --key) is required")

    c = httpx.Client(base_url=args.base + "/api/v1", headers={"Authorization": f"Bearer {args.key}"}, timeout=60)

    def get(path: str, **params) -> dict | list:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()

    me = get("/me")
    provider = me["tier"]  # the column name in the results is the tier that wrote the summaries

    r = c.get(f"/projects/{args.project}")
    if r.status_code == 404:
        c.post("/projects", json={"name": "SD evals", "slug": args.project}).raise_for_status()
    else:
        r.raise_for_status()
    existing = {n["path"] for n in get(f"/projects/{args.project}/tree")}
    pages = [
        ln.strip()
        for ln in (HERE / "data" / "pages.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    seeded = []
    for rel in pages:
        md = ROOT / rel
        slug = md.stem
        seeded.append(slug)
        if slug in existing:
            continue
        text = md.read_text()
        body = {"title": first_heading(text) or slug, "slug": slug, "markdown": text}
        c.post(f"/projects/{args.project}/nodes", json=body).raise_for_status()
        print("seeded", slug)

    pending = set(seeded)
    deadline = time.time() + args.wait
    while pending and time.time() < deadline:
        for path in sorted(pending):
            node = get(f"/projects/{args.project}/nodes/{path}")
            if node.get("embedded"):
                pending.discard(path)
        if pending:
            print("waiting for", len(pending), "pages")
            time.sleep(10)
    if pending:
        sys.exit(f"gave up: {len(pending)} pages still unembedded after {args.wait}s: {sorted(pending)}")

    queries = json.loads((HERE / "data" / "search_queries.json").read_text())
    hits1 = hits3 = 0
    rr = 0.0
    latencies = []
    failures = []
    for q in queries:
        t = time.time()
        res = get(f"/projects/{args.project}/search", q=q["query"], k=5)
        latencies.append(time.time() - t)
        paths = [x["path"] for x in res]
        if paths[:1] == [q["expected"]]:
            hits1 += 1
        if q["expected"] in paths[:3]:
            hits3 += 1
        if q["expected"] in paths:
            rr += 1 / (paths.index(q["expected"]) + 1)
        else:
            failures.append({"query": q["query"], "expected": q["expected"], "got": paths[:3]})
    n = len(queries)
    latencies.sort()
    now = datetime.now(UTC)
    out = {
        "eval": "search",
        "provider": provider,
        "date": now.isoformat(),
        "pages": len(seeded),
        "n": n,
        "hit@1": round(hits1 / n, 3),
        "hit@3": round(hits3 / n, 3),
        "mrr": round(rr / n, 3),
        "p50_latency_s": round(latencies[len(latencies) // 2], 3),
        "failures": failures,
        "passes": hits3 / n >= 0.9,
    }
    results = HERE / "results"
    results.mkdir(parents=True, exist_ok=True)
    path = results / f"{now.strftime('%Y-%m-%dT%H%M%SZ')}-{provider}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
