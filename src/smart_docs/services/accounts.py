"""Accounts and API keys. Identity (password, e-mail, handle, avatar) lives at accounts.3m4.net (SD-014)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs import security
from smart_docs.config import get_settings
from smart_docs.errors import Forbidden, Invalid, NotFound
from smart_docs.models import Account, ApiKey

log = logging.getLogger("smart_docs.accounts")


def default_tier() -> str:
    s = get_settings()
    return s.default_tier if s.default_tier in s.tiers_available() else "agent"


async def provision(session: AsyncSession, claims: dict) -> Account:
    """The account behind a verified session, created on first sight and kept in sync with the claims.

    `email` and `handle` mirror accounts.3m4.net. The handle drives the public
    URLs, so a rename there renames them here (the accounts profile page warns
    about that). Creating is subject to `SIGNUPS_OPEN`; refreshing never is.
    The row is committed right away so a later rollback in the request cannot
    undo the provisioning.
    """
    identity_id = uuid.UUID(str(claims["sub"]))
    email = str(claims.get("email") or "").strip().lower()
    handle = str(claims.get("handle") or "").strip().lower()
    if not email or not handle:
        raise Invalid("The session is missing the e-mail or the handle.")

    account = await session.scalar(select(Account).where(Account.identity_id == identity_id))
    if account is None:
        if not get_settings().signups_open:
            raise Forbidden("Signups are closed on this instance.", hint="Ask the operator for an account.")
        account = Account(identity_id=identity_id, email=email, handle=handle, tier=default_tier())
        session.add(account)
        try:
            await session.commit()
        except IntegrityError:
            # Two first requests raced, or the handle/e-mail is still held by a stale mirror.
            await session.rollback()
            account = await session.scalar(select(Account).where(Account.identity_id == identity_id))
            if account is None:
                raise
        return account

    if account.email != email or account.handle != handle:
        account.email = email
        account.handle = handle
        try:
            await session.commit()
        except IntegrityError:
            # Another local row still holds that handle or e-mail; it catches up on its own next request.
            await session.rollback()
            log.warning("could not sync handle/e-mail for account %s yet", account.id)
            account = await session.scalar(select(Account).where(Account.identity_id == identity_id))
    return account


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
