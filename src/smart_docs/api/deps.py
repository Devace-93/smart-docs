"""Request-scoped dependencies: the database session and the authenticated principal.

Two credentials open the API (SD-013):

- A 3m4 accounts session: the `3m4_session` cookie set by accounts.3m4.net, or
  the same JWT as `Authorization: Bearer <jwt>`. It is verified locally against
  the accounts JWKS and the account row is created or refreshed from the claims.
- An API key (`Authorization: Bearer sd_...`), unchanged: it maps to an account
  and carries scopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from smart_docs import m4session, security
from smart_docs.config import get_settings
from smart_docs.db import get_session
from smart_docs.errors import EmailUnverified, Forbidden, InvalidSession, NoSession, SDError, SessionExpired
from smart_docs.models import Account
from smart_docs.services import accounts as accounts_svc

ALL_SCOPES = list(security.SCOPES)


@dataclass
class Principal:
    account: Account
    scopes: list[str] = field(default_factory=lambda: list(ALL_SCOPES))
    via: str = "session"
    identity: dict | None = None  # the session claims; None for API keys

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise Forbidden(
                f"This API key lacks the {scope!r} scope.", hint="Create a key with that scope under /app/keys."
            )

    @property
    def email_verified(self) -> bool:
        """API keys can only be created from a verified session, so they count as verified."""
        return True if self.identity is None else bool(self.identity.get("email_verified"))


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _session_token(request: Request) -> str | None:
    # An explicit bearer header wins over the ambient cookie, so a client that
    # holds a cookie for one identity can still act as another on purpose.
    bearer = _bearer(request)
    if bearer and not bearer.startswith(security.API_KEY_PREFIX):
        return bearer
    return request.cookies.get(m4session.COOKIE_NAME) or None


async def verify_session_token(token: str) -> dict:
    """Verify the JWT off the event loop (the first call per key set fetches the JWKS)."""
    s = get_settings()
    try:
        return await run_in_threadpool(
            m4session.verify, token, jwks_url=s.accounts_jwks_url, issuer=s.accounts_url, audience="3m4"
        )
    except m4session.SessionError as err:
        if err.code == "session_expired":
            raise SessionExpired(str(err)) from err
        if err.code == "no_session":
            raise NoSession(str(err)) from err
        raise InvalidSession(str(err)) from err


async def principal_from_api_key(session: AsyncSession, api_key: str | None) -> Principal | None:
    """An API-key principal, or None. The MCP transport only ever accepts keys, never sessions."""
    if not api_key or not api_key.startswith(security.API_KEY_PREFIX):
        return None
    found = await accounts_svc.resolve_api_key(session, api_key)
    if found is None:
        return None
    account, scopes = found
    return Principal(account=account, scopes=scopes, via="api_key")


async def resolve_principal(session: AsyncSession, request: Request) -> Principal | None:
    """The caller behind this request, or None when nothing was presented."""
    bearer = _bearer(request)
    if bearer and bearer.startswith(security.API_KEY_PREFIX):
        found = await accounts_svc.resolve_api_key(session, bearer)
        if found is None:
            raise InvalidSession("Unknown or revoked API key.", hint="Create a key under /app/keys.")
        account, scopes = found
        return Principal(account=account, scopes=scopes, via="api_key")
    token = _session_token(request)
    if not token:
        return None
    claims = await verify_session_token(token)
    account = await accounts_svc.provision(session, claims)
    return Principal(account=account, identity=claims)


async def current_principal_unverified(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    """A signed-in caller, verified e-mail or not. Only `GET /me` uses this, so the editor can show the banner."""
    principal = await resolve_principal(session, request)
    if principal is None:
        raise NoSession()
    return principal


async def current_principal(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    """A signed-in caller with a verified e-mail (or an API key)."""
    principal = await current_principal_unverified(request, session)
    if not principal.email_verified:
        raise EmailUnverified()
    return principal


async def optional_principal(request: Request, session: AsyncSession = Depends(get_session)) -> Principal | None:
    """For pages that render either way: never raises."""
    try:
        return await resolve_principal(session, request)
    except SDError:
        return None


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"
