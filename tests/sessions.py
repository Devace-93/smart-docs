"""Mint 3m4 accounts sessions for tests (SD-014).

One throwaway Ed25519 key per test process. `conftest.py` points the verifier
at `JWKS`, so every token from `mint()` verifies without the accounts service.
Both the fixtures and the tests import from here, never from `conftest`, so
there is exactly one key.
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ACCOUNTS_URL = os.environ.setdefault("ACCOUNTS_URL", "http://accounts.test")
_PRIVATE_KEY = Ed25519PrivateKey.generate()
_PUBLIC_RAW = _PRIVATE_KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
KID = hashlib.sha256(_PUBLIC_RAW).hexdigest()[:8]
JWKS = {
    "keys": [
        {
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": KID,
            "alg": "EdDSA",
            "use": "sig",
            "x": base64.urlsafe_b64encode(_PUBLIC_RAW).rstrip(b"=").decode(),
        }
    ]
}


def mint(
    *,
    sub: str | None = None,
    email: str | None = None,
    handle: str | None = None,
    name: str | None = "Test Person",
    verified: bool = True,
    ttl: int = 900,
) -> dict:
    """A session JWT like accounts.3m4.net issues, plus the claims it carries (under `token` and the claim names)."""
    uid = sub or str(uuid.uuid4())
    handle = handle or "u" + uuid.uuid4().hex[:8]
    now = int(time.time())
    claims = {
        "iss": ACCOUNTS_URL,
        "aud": "3m4",
        "sub": uid,
        "sid": str(uuid.uuid4()),
        "email": email or f"{handle}@example.com",
        "email_verified": verified,
        "handle": handle,
        "name": name,
        "avatar_url": f"{ACCOUNTS_URL}/avatars/{uid}?v=0",
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(claims, _PRIVATE_KEY, algorithm="EdDSA", headers={"kid": KID})
    return {"token": token, **claims}
