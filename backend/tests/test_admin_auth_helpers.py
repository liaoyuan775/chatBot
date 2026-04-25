from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.models import AdminAuditLogEntity
from app.modules.admin_auth.security import hash_password, hash_session_token, issue_session_token, verify_password
from app.modules.admin_auth.service import (
    _RATE_LIMIT_BUCKETS,
    enforce_rate_limit,
    request_requires_admin,
    serialize_audit_log,
)


def _build_request(path: str, method: str = "GET", client_host: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": (client_host, 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def test_password_hash_roundtrip() -> None:
    password_hash = hash_password("secret-123")
    assert password_hash != "secret-123"
    assert verify_password("secret-123", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_session_token_is_hashed_deterministically() -> None:
    token = issue_session_token()
    assert token
    assert hash_session_token(token) == hash_session_token(token)
    assert hash_session_token(token) != hash_session_token(f"{token}-other")


def test_request_requires_admin_respects_exempt_paths() -> None:
    assert request_requires_admin(_build_request("/api/providers")) is True
    assert request_requires_admin(_build_request("/api/settings/database/status")) is True
    assert request_requires_admin(_build_request("/api/admin/auth/login", method="POST")) is False
    assert request_requires_admin(_build_request("/healthz")) is False


def test_rate_limit_blocks_when_bucket_is_full() -> None:
    _RATE_LIMIT_BUCKETS.clear()
    request = _build_request("/api/admin/auth/login")
    enforce_rate_limit(scope="admin-login-test", request=request, window_seconds=60, max_requests=1)
    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(scope="admin-login-test", request=request, window_seconds=60, max_requests=1)
    assert exc.value.status_code == 429


def test_serialize_audit_log_includes_admin_alias() -> None:
    created_at = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    row = AdminAuditLogEntity(
        id=uuid4(),
        username="admin",
        action="config_mutation",
        target="providers",
        method="PUT",
        path="/api/providers/dashscope",
        status_code=200,
        detail_json={"field": "timeout_seconds"},
        ip_address="127.0.0.1",
        created_at=created_at,
    )
    payload = serialize_audit_log(row)
    assert payload["username"] == "admin"
    assert payload["admin_username"] == "admin"
    assert payload["created_at"] == created_at.isoformat()
