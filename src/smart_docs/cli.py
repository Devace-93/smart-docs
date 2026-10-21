"""`sd` command line: migrations, worker, server and seeding. Accounts are created by logging in (SD-014)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from smart_docs.config import get_settings


def cmd_migrate(_args) -> None:
    """Alembic upgrade head, then the procrastinate job tables if they are missing."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    command.upgrade(cfg, "head")
    asyncio.run(_apply_queue_schema())
    print("migrations applied")


async def _apply_queue_schema() -> None:
    from smart_docs.worker.app import app

    async with app.open_async():
        exists = await app.connector.execute_query_one_async(
            "SELECT to_regclass('procrastinate_jobs') IS NOT NULL AS present"
        )
        if not exists["present"]:
            await app.schema_manager.apply_schema_async()
            print("procrastinate schema applied")


def cmd_worker(args) -> None:
    from smart_docs.worker.app import app

    app.run_worker(concurrency=args.concurrency, queues=["enrich"])


def cmd_serve(args) -> None:
    import uvicorn

    uvicorn.run(
        "smart_docs.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def cmd_seed(args) -> None:
    """Import a folder of Markdown files as pages of one project (folders become folders)."""
    from smart_docs.db import session_factory
    from smart_docs.services import projects as projects_svc
    from smart_docs.services import tree as tree_svc
    from smart_docs.services.accounts import get_account_by_handle
    from smart_docs.services.render import first_heading
    from smart_docs.worker.app import app, enqueue_enrich

    folder = Path(args.folder)

    async def run():
        async with app.open_async(), session_factory()() as session:
            account = await get_account_by_handle(session, args.handle)
            if account is None:
                sys.exit(f"no account with handle {args.handle}")
            try:
                project = await projects_svc.get_project(session, account, args.project)
            except Exception:  # noqa: BLE001
                project = await projects_svc.create_project(
                    session, account, name=args.name or args.project, slug=args.project
                )
            created = 0
            for md in sorted(folder.rglob("*.md")):
                rel = md.relative_to(folder)
                parent = None
                for part in rel.parts[:-1]:
                    path = f"{parent}/{part}" if parent else part
                    try:
                        await tree_svc.get_node(session, project, path)
                    except Exception:  # noqa: BLE001
                        await tree_svc.create_node(
                            session,
                            project,
                            kind="folder",
                            title=part.replace("-", " ").title(),
                            parent_path=parent,
                            slug=part,
                        )
                    parent = path
                text = md.read_text(encoding="utf-8")
                title = first_heading(text) or md.stem.replace("-", " ")
                node = await tree_svc.create_node(
                    session,
                    project,
                    kind="page",
                    title=title,
                    parent_path=parent,
                    slug=md.stem.lower(),
                    markdown=text,
                    is_public=args.public,
                )
                await session.commit()
                await enqueue_enrich(node.id)
                created += 1
            print(f"imported {created} pages into {account.handle}/{project.slug}")

    asyncio.run(run())


def cmd_enrich_pending(_args) -> None:
    """Queue an enrichment job for every page whose metadata or embedding is missing."""
    from sqlalchemy import select

    from smart_docs.db import session_factory
    from smart_docs.models import Node, Page
    from smart_docs.worker.app import app, enqueue_enrich

    async def run():
        async with app.open_async(), session_factory()() as session:
            rows = await session.scalars(
                select(Page.node_id)
                .join(Node, Node.id == Page.node_id)
                .where(
                    Node.deleted_at.is_(None),
                    (Page.enrich_status.in_(["pending", "failed", "rate_limited"])) | Page.embedding.is_(None),
                )
            )
            ids = list(rows)
            for node_id in ids:
                await enqueue_enrich(node_id)
            print(f"queued {len(ids)} pages")

    asyncio.run(run())


def main() -> None:
    parser = argparse.ArgumentParser(prog="sd", description=f"{get_settings().instance_name} admin commands")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="apply database migrations and the job queue schema").set_defaults(fn=cmd_migrate)
    sub.add_parser("enrich-pending", help="queue enrichment for pages missing metadata or embeddings").set_defaults(
        fn=cmd_enrich_pending
    )

    p = sub.add_parser("worker", help="run the enrichment worker")
    p.add_argument("--concurrency", type=int, default=1)
    p.set_defaults(fn=cmd_worker)

    p = sub.add_parser("serve", help="run the API and web server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("seed", help="import a folder of Markdown files into a project")
    p.add_argument("folder")
    p.add_argument("--handle", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--name")
    p.add_argument("--public", action="store_true")
    p.set_defaults(fn=cmd_seed)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
