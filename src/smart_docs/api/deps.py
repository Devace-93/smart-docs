"""Request-scoped dependencies: the database session and the authenticated account."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from smart_docs import security
from smart_docs.db import get_session
from smart_docs.errors import Forbidden, Unauthorized
from smart_docs.models import Account
from smart_docs.services import accounts as accounts_svc

ALL_SCOPES = list(security.SCOPES)


@dataclass
class Principal:
    account: Account
    scopes: list[str] = field(default_factory=lambda: list(ALL_SCOPES))
    via: str = "session"

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise Forbidden(
                f"This API key lacks the {scope!r} scope.", hint="Create a key with that scope under /app/keys."
            )


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def resolve_principal(session: AsyncSession, token: str | None) -> Principal | None:
    if not token:
        return None
    if token.startswith(security.API_KEY_PREFIX):
        found = await accounts_svc.resolve_api_key(session, token)
        if found is None:
            return None
        account, scopes = found
        return Principal(account=account, scopes=scopes, via="api_key")
    account_id = security.read_session_token(token)
    if account_id is None:
        return None
    try:
        account = await accounts_svc.get_account(session, account_id)
    except Exception:  # noqa: BLE001
        return None
    return Principal(account=account)


async def current_principal(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    token = _bearer(request) or request.cookies.get("sd_session")
    principal = await resolve_principal(session, token)
    if principal is None:
        raise Unauthorized("Not authenticated.")
    return principal


async def optional_principal(request: Request, session: AsyncSession = Depends(get_session)) -> Principal | None:
    token = _bearer(request) or request.cookies.get("sd_session")
    return await resolve_principal(session, token)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"
