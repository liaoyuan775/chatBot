from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AdminAuditLogEntity, AdminSessionEntity, AdminUserEntity
from app.modules.admin_auth.security import (
    hash_password,
    hash_session_token,
    issue_session_token,
    session_expiry,
    utc_now,
    verify_password,
)

settings = get_settings()
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
MANAGEMENT_PREFIXES = (
    "/api/providers",
    "/api/models",
    "/api/chains",
    "/api/personas",
    "/api/voices",
    "/api/knowledge",
    "/api/settings",
    "/api/call-config",
    "/api/context",
    "/api/admin",
)
EXEMPT_PATHS = {
    "/api/admin/auth/login",
    "/api/admin/auth/logout",
    "/api/admin/auth/me",
    "/healthz",
    "/readyz",
}


@dataclass
class AdminPrincipal:
    user_id: str
    username: str
    session_id: str


def _client_ip(request: Request | None) -> str:
    if not request:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _rate_limit_key(scope: str, request: Request | None) -> str:
    return f"{scope}:{_client_ip(request)}"


def enforce_rate_limit(*, scope: str, request: Request | None, window_seconds: int, max_requests: int) -> None:
    key = _rate_limit_key(scope, request)
    now = monotonic()
    bucket = _RATE_LIMIT_BUCKETS[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试。")
    bucket.append(now)


async def ensure_default_admin(db: AsyncSession) -> AdminUserEntity:
    row = await db.scalar(select(AdminUserEntity).where(AdminUserEntity.username == settings.admin_username))
    if row:
        return row
    row = AdminUserEntity(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password),
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def authenticate_admin(db: AsyncSession, *, username: str, password: str) -> AdminUserEntity | None:
    user = await db.scalar(select(AdminUserEntity).where(AdminUserEntity.username == username.strip()))
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def create_admin_session(db: AsyncSession, *, user: AdminUserEntity, request: Request | None) -> tuple[str, AdminSessionEntity]:
    raw_token = issue_session_token()
    row = AdminSessionEntity(
        user_id=user.id,
        session_token_hash=hash_session_token(raw_token),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
        expires_at=session_expiry(),
    )
    user.last_login_at = utc_now()
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return raw_token, row


async def revoke_session(db: AsyncSession, *, raw_token: str | None) -> None:
    if not raw_token:
        return
    hashed = hash_session_token(raw_token)
    row = await db.scalar(select(AdminSessionEntity).where(AdminSessionEntity.session_token_hash == hashed))
    if not row:
        return
    row.revoked_at = utc_now()
    await db.commit()


async def get_admin_principal(db: AsyncSession, *, raw_token: str | None) -> AdminPrincipal | None:
    if not raw_token:
        return None
    hashed = hash_session_token(raw_token)
    row = await db.scalar(select(AdminSessionEntity).where(AdminSessionEntity.session_token_hash == hashed))
    if not row or row.revoked_at is not None or row.expires_at <= utc_now():
        return None
    user = await db.get(AdminUserEntity, row.user_id)
    if not user or not user.is_active:
        return None
    return AdminPrincipal(user_id=str(user.id), username=user.username, session_id=str(row.id))


def attach_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite=settings.auth_cookie_samesite,
        max_age=max(3600, int(settings.admin_session_ttl_hours) * 3600),
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


def request_requires_admin(request: Request) -> bool:
    if request.url.path in EXEMPT_PATHS:
        return False
    if request.method.upper() == "OPTIONS":
        return False
    if "/preview" in request.url.path or "/copy" in request.url.path:
        return False
    return any(request.url.path.startswith(prefix) for prefix in MANAGEMENT_PREFIXES)


async def require_admin_user(request: Request, db: AsyncSession) -> AdminPrincipal:
    raw_token = request.cookies.get(settings.auth_cookie_name)
    principal = await get_admin_principal(db, raw_token=raw_token)
    if not principal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员登录已失效，请重新登录。")
    return principal


async def log_admin_action(
    db: AsyncSession,
    *,
    principal: AdminPrincipal | None,
    action: str,
    target: str,
    method: str,
    path: str,
    status_code: int,
    detail_json: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    db.add(
        AdminAuditLogEntity(
            user_id=principal.user_id if principal else None,
            username=principal.username if principal else None,
            action=action[:80],
            target=target[:160],
            method=method[:16],
            path=path,
            status_code=status_code,
            detail_json=detail_json or {},
            ip_address=_client_ip(request),
        )
    )
    await db.commit()


async def list_recent_audit_logs(db: AsyncSession, *, limit: int = 50) -> list[AdminAuditLogEntity]:
    rows = (
        await db.scalars(select(AdminAuditLogEntity).order_by(AdminAuditLogEntity.created_at.desc()).limit(max(1, limit)))
    ).all()
    return list(rows)


async def cleanup_expired_admin_sessions(db: AsyncSession) -> None:
    await db.execute(delete(AdminSessionEntity).where(AdminSessionEntity.expires_at < utc_now()))
    await db.commit()


def serialize_audit_log(row: AdminAuditLogEntity) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "username": row.username,
        "admin_username": row.username,
        "action": row.action,
        "target": row.target,
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
        "detail_json": row.detail_json or {},
        "ip_address": row.ip_address,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else None,
    }
