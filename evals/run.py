"""`uv run sd-evals`: the search eval from SD-010, against a running instance.

Seeds the pages in evals/data/pages into a project, waits for embeddings, runs the queries and
writes evals/results/<date>-<provider>.json. Summary and tag evals need a model judge and are
listed in docs/evals-failures.md as not yet automated.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("SD_URL", "http://localhost:8000"))
    ap.add_argument("--key", default=os.environ.get("SD_API_KEY"))
    ap.add_argument("--project", default="sd-evals")
    ap.add_argument("--provider", default=os.environ.get("SD_EVAL_PROVIDER", "local"))
    ap.add_argument("--wait", type=int, default=600, help="seconds to wait for embeddings")
    args = ap.parse_args()
    if not args.key:
        sys.exit("SD_API_KEY (or --key) is required")

    c = httpx.Client(base_url=args.base + "/api/v1", headers={"Authorization": f"Bearer {args.key}"}, timeout=60)
    r = c.get(f"/projects/{args.project}")
    if r.status_code == 404:
        c.post("/projects", json={"name": "SD evals", "slug": args.project}).raise_for_status()
    tree = {n["path"]: n for n in c.get(f"/projects/{args.project}/tree").json()}
    for md in sorted((HERE / "data" / "pages").glob("*.md")):
        if md.stem in tree:
            continue
        c.post(f"/projects/{args.project}/nodes", json={"title": md.stem, "slug": md.stem, "markdown": md.read_text()}).raise_for_status()
        print("seeded", md.stem)

    deadline = time.time() + args.wait
    while time.time() < deadline:
        nodes = c.get(f"/projects/{args.project}/tree").json()
        pending = [n["path"] for n in nodes if (c.get(f"/projects/{args.project}/nodes/{n['path']}").json().get("enrich_status") == "pending")]
        if not pending:
            break
        print("waiting for", len(pending), "pages")
        time.sleep(10)

    queries = json.loads((HERE / "data" / "search_queries.json").read_text())
    hits1 = hits3 = 0
    rr = 0.0
    latencies = []
    failures = []
    for q in queries:
        t = time.time()
        res = c.get(f"/projects/{args.project}/search", params={"q": q["query"], "k": 5}).json()
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
    out = {
        "eval": "search",
        "provider": args.provider,
        "date": datetime.now(UTC).isoformat(),
        "n": n,
        "hit@1": round(hits1 / n, 3),
        "hit@3": round(hits3 / n, 3),
        "mrr": round(rr / n, 3),
        "p50_latency_s": round(latencies[len(latencies) // 2], 3),
        "failures": failures,
        "passes": hits3 / n >= 0.9,
    }
    path = HERE / "results" / f"{datetime.now(UTC).date()}-{args.provider}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
