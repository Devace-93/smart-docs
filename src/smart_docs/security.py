"""API keys and secret encryption. Sessions belong to accounts.3m4.net (see `m4session.py`, SD-013)."""

from __future__ import annotations

import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from smart_docs.config import get_settings

API_KEY_PREFIX = "sd_"
SCOPES = ("read", "write", "publish")


def new_api_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, sha256 hash). The plaintext is shown once and never stored."""
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, plaintext[:10], hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _fernet() -> Fernet | None:
    key = get_settings().fernet_key
    return Fernet(key.encode()) if key else None


def encrypt_secret(value: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("FERNET_KEY is not set; cannot store BYOK keys")
    return f.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str | None:
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        return None
