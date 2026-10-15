"""The enrichment job: summary and tags from the account's tier, embedding from the local model."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from smart_docs.db import session_factory
from smart_docs.errors import RateLimited
from smart_docs.llm.client import embed, provider_for, summarize
from smart_docs.models import Account, Node, Project
from smart_docs.services.render import plain_excerpt
from smart_docs.services.tree import _clean_tags
from smart_docs.services.usage import reserve_model_call
from smart_docs.worker.app import enqueue_enrich

log = logging.getLogger("smart_docs.worker")


def usable_summary(summary: str, title: str) -> bool:
    """Small models sometimes echo the title or a label instead of a sentence."""
    s = summary.strip().strip('"')
    if len(s.split()) < 4:
        return False
    if s.lower().startswith(("title:", "summary:")):
        return False
    return s.lower().rstrip(".") != title.strip().lower()


async def enrich(node_id: uuid.UUID) -> None:
    async with session_factory()() as session:
        node = await session.get(Node, node_id)
        if node is None or node.page is None or node.deleted_at is not None:
            return
        page = node.page
        project = await session.get(Project, node.project_id)
        account = await session.get(Account, project.account_id) if project else None
        if account is None:
            return

        # 1. Summary and tags, unless an agent already supplied them.
        if page.enrich_status != "agent":
            provider = provider_for(account)
            if provider is None:
                page.summary = page.summary or plain_excerpt(page.markdown, 160)
                page.enrich_status = "skipped"
                page.enriched_by = "none"
            else:
                try:
                    await reserve_model_call(session, account, provider.tier)
                    summary, tags = await summarize(provider, node.title, page.markdown)
                    if not usable_summary(summary, node.title):
                        summary = ""
                    page.summary = summary or plain_excerpt(page.markdown, 160)
                    page.tags = _clean_tags(tags)
                    page.enrich_status = "done"
                    page.enriched_by = f"{provider.tier}:{provider.model}"
                    page.enrich_error = None
                except RateLimited as e:
                    # Over the tier's cap: keep the page pending and try again when the window opens.
                    page.enrich_status = "pending"
                    page.enrich_error = e.message
                    await session.commit()
                    await enqueue_enrich(node.id, delay_seconds=max(5, min(e.retry_after, 3600)))
                    return
                except Exception as e:  # noqa: BLE001
                    log.warning("summary failed for %s: %s", node.path, e)
                    page.enrich_status = "failed"
                    page.enrich_error = str(e)[:500]
                    page.summary = page.summary or plain_excerpt(page.markdown, 160)
            page.enriched_at = datetime.now(UTC)

        # 2. Embedding, always local.
        try:
            text = f"{node.title}\n\n{page.summary}\n\n{page.markdown}"
            [vector] = await embed([text])
            page.embedding = vector
        except Exception as e:  # noqa: BLE001
            log.warning("embedding failed for %s: %s", node.path, e)
            page.enrich_error = (page.enrich_error or "") + f" | embedding: {str(e)[:200]}"
            await session.commit()
            raise
        await session.commit()
