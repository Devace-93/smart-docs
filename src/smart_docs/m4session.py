"""Verify 3m4 accounts sessions (the `3m4_session` cookie or a bearer JWT).

Vendored from `accounts/packages/relying-party/python/m4session.py` (SD-013).
Two deliberate differences from the upstream file: the JWKS is fetched with
httpx instead of requests (already a dependency here), and the fetch is a
module-level function, `fetch_jwks`, so tests can replace it with a stub and
run without the network. Keep the verification rules in sync with
`accounts/CONTRACT.md`: EdDSA, audience `3m4`, issuer = the accounts origin,
one minute of leeway, keys cached for ten minutes and refetched once when a
token names an unknown `kid`.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import jwt

COOKIE_NAME = "3m4_session"
ALGORITHMS = ["EdDSA"]
LEEWAY_SECONDS = 60
CACHE_TTL_SECONDS = 600


class SessionError(Exception):
    """`code` is `no_session`, `session_expired` or `invalid_session`."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


def fetch_jwks(jwks_url: str) -> dict:
    """GET the key set. Tests replace this function; production never should."""
    response = httpx.get(jwks_url, timeout=5)
    response.raise_for_status()
    return response.json()


class _JwksCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}  # jwks_url -> {"fetched": ts, "keys": {kid: key}}

    def get(self, jwks_url: str, kid: str | None):
        with self._lock:
            entry = self._entries.get(jwks_url)
            now = time.time()
            stale = entry is None or now - entry["fetched"] > CACHE_TTL_SECONDS
            unknown_kid = (
                entry is not None and kid is not None and kid not in entry["keys"] and now - entry["fetched"] > 5
            )
            if stale or unknown_kid:
                try:
                    data = fetch_jwks(jwks_url)
                    keys = {}
                    for jwk in data.get("keys", []):
                        try:
                            keys[jwk.get("kid")] = jwt.PyJWK(jwk).key
                        except Exception:  # noqa: BLE001  (skip a malformed key, keep the rest)
                            continue
                    entry = {"fetched": now, "keys": keys}
                    self._entries[jwks_url] = entry
                except Exception:
                    if entry is None:
                        raise
            return entry["keys"].get(kid)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_cache = _JwksCache()


def clear_cache() -> None:
    _cache.clear()


def verify(token: str, *, jwks_url: str, issuer: str, audience: str = "3m4") -> dict:
    """Verify a 3m4 session JWT and return its claims (sub, sid, email, email_verified, handle, name, avatar_url)."""
    if not token:
        raise SessionError("no_session", "Not signed in.")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as err:
        raise SessionError("invalid_session", "Invalid session.") from err
    try:
        key = _cache.get(jwks_url, header.get("kid"))
    except Exception as err:  # noqa: BLE001
        raise SessionError("invalid_session", "Could not fetch the signing keys.") from err
    if key is None:
        raise SessionError("invalid_session", "Unknown signing key.")
    try:
        return jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=audience,
            issuer=issuer.rstrip("/"),
            leeway=LEEWAY_SECONDS,
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as err:
        raise SessionError("session_expired", "Session expired.") from err
    except jwt.PyJWTError as err:
        raise SessionError("invalid_session", "Invalid session.") from err
