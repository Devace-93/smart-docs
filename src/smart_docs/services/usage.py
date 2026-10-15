"""Model usage counters and per-tier limits (SD-005)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs.config import get_settings
from smart_docs.errors import Invalid, RateLimited
from smart_docs.models import Account, UsageEvent


async def _count_since(session: AsyncSession, account: Account, tier: str, since: datetime) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(UsageEvent.account_id == account.id, UsageEvent.tier == tier, UsageEvent.at >= since)
        )
        or 0
    )


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def usage_report(session: AsyncSession, account: Account) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    hosted_today = await _count_since(session, account, "hosted", _day_start(now))
    local_hour = await _count_since(session, account, "local", now - timedelta(hours=1))
    local_10s = await _count_since(session, account, "local", now - timedelta(seconds=10))
    return {
        "tier": account.tier,
        "tiers_available": s.tiers_available(),
        "hosted": {
            "enabled": "hosted" in s.tiers_available(),
            "used_today": hosted_today,
            "daily_limit": s.hosted_daily_limit,
            "resets_at": (_day_start(now) + timedelta(days=1)).isoformat(),
        },
        "local": {
            "enabled": "local" in s.tiers_available(),
            "used_last_hour": local_hour,
            "hourly_limit": s.local_per_hour,
            "per_10s_limit": s.local_per_10s,
            "used_last_10s": local_10s,
        },
        "byok": {"enabled": "byok" in s.tiers_available(), "configured": bool(account.byok_key_enc)},
        "agent": {"enabled": True, "note": "Pass summary and tags on create or update; no model is called."},
    }


async def reserve_model_call(session: AsyncSession, account: Account, tier: str) -> None:
    """Raise RateLimited when the account is over its cap, else record one usage event."""
    s = get_settings()
    now = datetime.now(UTC)
    if tier == "hosted":
        used = await _count_since(session, account, "hosted", _day_start(now))
        if used >= s.hosted_daily_limit:
            reset = int((_day_start(now) + timedelta(days=1) - now).total_seconds())
            raise RateLimited(
                "Hosted tier daily limit reached.",
                retry_after=reset,
                limit=s.hosted_daily_limit,
                remaining=0,
                reset=reset,
            )
    elif tier == "local":
        recent = await _count_since(session, account, "local", now - timedelta(seconds=10))
        if recent >= s.local_per_10s:
            raise RateLimited(
                "Local tier allows one request every 10 seconds.",
                retry_after=10,
                limit=s.local_per_10s,
                remaining=0,
                reset=10,
            )
        hour = await _count_since(session, account, "local", now - timedelta(hours=1))
        if hour >= s.local_per_hour:
            raise RateLimited(
                "Local tier hourly limit reached.", retry_after=3600, limit=s.local_per_hour, remaining=0, reset=3600
            )
    elif tier in ("byok", "agent"):
        pass
    else:
        raise Invalid(f"Unknown tier {tier!r}.")
    session.add(UsageEvent(account_id=account.id, tier=tier, at=now))
    await session.flush()
