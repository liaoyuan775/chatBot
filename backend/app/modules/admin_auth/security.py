from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str, *, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        actual_salt.encode("utf-8"),
        120_000,
    )
    return f"{actual_salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, _digest = str(password_hash or "").split("$", 1)
    except ValueError:
        return False
    candidate = hash_password(password, salt=salt)
    return hmac.compare_digest(candidate, str(password_hash or ""))


def issue_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_expiry() -> datetime:
    return utc_now() + timedelta(hours=max(1, int(settings.admin_session_ttl_hours)))
