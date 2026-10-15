"""Accounts, sessions and API keys."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs import security
from smart_docs.config import get_settings
from smart_docs.errors import Forbidden, Invalid, NotFound, RateLimited, Unauthorized
from smart_docs.models import Account, ApiKey, LoginAttempt
from smart_docs.slug import is_valid_slug, slugify


async def register(session: AsyncSession, *, email: str, password: str, handle: str | None) -> Account:
    s = get_settings()
    if not s.signups_open:
        raise Forbidden("Signups are closed on this instance.")
    email = email.strip().lower()
    if "@" not in email or len(email) > 320:
        raise Invalid("Enter a valid email address.")
    if len(password) < 8:
        raise Invalid("Password must be at least 8 characters.")
    handle = slugify(handle) if handle else slugify(email.split("@")[0])
    if not is_valid_slug(handle) or handle in s.reserved_handles:
        raise Invalid("That handle is reserved or invalid.")
    existing = await session.scalar(select(Account).where((Account.email == email) | (Account.handle == handle)))
    if existing is not None:
        raise Invalid("Email or handle already taken.")
    tier = s.default_tier if s.default_tier in s.tiers_available() else "agent"
    account = Account(email=email, handle=handle, password_hash=security.hash_password(password), tier=tier)
    session.add(account)
    await session.flush()
    return account


async def _check_login_rate(session: AsyncSession, key: str) -> None:
    s = get_settings()
    window_start = datetime.now(UTC) - timedelta(minutes=15)
    count = await session.scalar(
        select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.at >= window_start)
    )
    if count is not None and count >= s.login_attempts_per_15min:
        raise RateLimited(
            "Too many login attempts. Try again later.",
            retry_after=900,
            limit=s.login_attempts_per_15min,
            remaining=0,
            reset=900,
        )


async def login(session: AsyncSession, *, email: str, password: str, ip: str) -> tuple[Account, str]:
    email = email.strip().lower()
    ip_key = "ip:" + security.hash_ip(ip)
    email_key = "email:" + email
    await _check_login_rate(session, ip_key)
    await _check_login_rate(session, email_key)
    account = await session.scalar(select(Account).where(Account.email == email))
    if account is None or not security.verify_password(account.password_hash, password):
        session.add_all([LoginAttempt(key=ip_key), LoginAttempt(key=email_key)])
        await session.commit()  # the request fails, but the attempt must be counted
        raise Unauthorized("Wrong email or password.", hint="")
    return account, security.issue_session_token(str(account.id))


async def get_account(session: AsyncSession, account_id: uuid.UUID | str) -> Account:
    account = await session.get(Account, uuid.UUID(str(account_id)))
    if account is None:
        raise NotFound("Account not found.")
    return account


async def get_account_by_handle(session: AsyncSession, handle: str) -> Account | None:
    return await session.scalar(select(Account).where(Account.handle == handle))


async def update_settings(
    session: AsyncSession,
    account: Account,
    *,
    tier: str | None = None,
    byok_base_url: str | None = None,
    byok_model: str | None = None,
    byok_key: str | None = None,
) -> Account:
    s = get_settings()
    if tier is not None:
        if tier not in s.tiers_available():
            raise Invalid(
                f"Tier {tier!r} is not enabled on this instance.", hint=f"Available: {', '.join(s.tiers_available())}."
            )
        account.tier = tier
    if byok_base_url is not None:
        account.byok_base_url = byok_base_url.strip() or None
    if byok_model is not None:
        account.byok_model = byok_model.strip() or None
    if byok_key is not None:
        account.byok_key_enc = security.encrypt_secret(byok_key) if byok_key else None
    await session.flush()
    return account


# API keys


async def create_api_key(
    session: AsyncSession, account: Account, *, name: str, scopes: list[str]
) -> tuple[ApiKey, str]:
    scopes = sorted(set(scopes))
    if not scopes or any(sc not in security.SCOPES for sc in scopes):
        raise Invalid("Scopes must be a non-empty subset of read, write, publish.")
    plaintext, prefix, key_hash = security.new_api_key()
    key = ApiKey(account_id=account.id, name=name.strip() or "key", prefix=prefix, key_hash=key_hash, scopes=scopes)
    session.add(key)
    await session.flush()
    return key, plaintext


async def list_api_keys(session: AsyncSession, account: Account) -> list[ApiKey]:
    rows = await session.scalars(
        select(ApiKey).where(ApiKey.account_id == account.id, ApiKey.revoked_at.is_(None)).order_by(ApiKey.created_at)
    )
    return list(rows)


async def revoke_api_key(session: AsyncSession, account: Account, key_id: uuid.UUID) -> None:
    key = await session.get(ApiKey, key_id)
    if key is None or key.account_id != account.id or key.revoked_at is not None:
        raise NotFound("API key not found.")
    key.revoked_at = datetime.now(UTC)
    await session.flush()


async def resolve_api_key(session: AsyncSession, plaintext: str) -> tuple[Account, list[str]] | None:
    key = await session.scalar(
        select(ApiKey).where(ApiKey.key_hash == security.hash_api_key(plaintext), ApiKey.revoked_at.is_(None))
    )
    if key is None:
        return None
    key.last_used_at = datetime.now(UTC)
    account = await session.get(Account, key.account_id)
    if account is None:
        return None
    return account, list(key.scopes)
