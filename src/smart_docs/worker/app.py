"""procrastinate app: Postgres-backed jobs, one queue per tier so the local model runs serially."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import procrastinate
from procrastinate import RetryStrategy

from smart_docs.config import get_settings


def make_app() -> procrastinate.App:
    return procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=get_settings().sync_database_url),
        import_paths=["smart_docs.worker.app"],
    )


app = make_app()


@app.task(
    name="enrich_page",
    queue="enrich",
    retry=RetryStrategy(max_attempts=3, exponential_wait=10),
)
async def enrich_page(node_id: str) -> None:
    """Summary, tags and embedding for one page. Runs in the worker, never in the request."""
    from smart_docs.worker.enrich import enrich

    await enrich(uuid.UUID(node_id))


async def enqueue_enrich(node_id: uuid.UUID) -> None:
    """Defer the job. The queueing lock collapses repeated saves of one page into one job."""
    try:
        await enrich_page.configure(lock=str(node_id), queueing_lock=f"enrich-{node_id}").defer_async(
            node_id=str(node_id)
        )
    except procrastinate.exceptions.AlreadyEnqueued:
        pass


def now() -> datetime:
    return datetime.now(UTC)
