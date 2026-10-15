"""Password hashing, session tokens, API keys and secret encryption."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from smart_docs.config import get_settings

_hasher = PasswordHasher()

API_KEY_PREFIX = "sd_"
SCOPES = ("read", "write", "publish")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def issue_session_token(account_id: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": account_id, "iat": now, "exp": now + timedelta(hours=s.session_ttl_hours)}
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def read_session_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


def new_api_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, sha256 hash). The plaintext is shown once and never stored."""
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, plaintext[:10], hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def hash_ip(ip: str) -> str:
    """Daily-salted hash. Raw IPs are never stored."""
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return hmac.new(get_settings().ip_hash_salt.encode(), f"{day}:{ip}".encode(), hashlib.sha256).hexdigest()[:32]


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
