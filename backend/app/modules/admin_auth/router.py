from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.admin_auth.service import (
    attach_auth_cookie,
    authenticate_admin,
    clear_auth_cookie,
    create_admin_session,
    enforce_rate_limit,
    ensure_default_admin,
    get_admin_principal,
    list_recent_audit_logs,
    log_admin_action,
    require_admin_user,
    revoke_session,
    serialize_audit_log,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


class AdminLoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


@router.post("/auth/login")
async def admin_login(payload: AdminLoginPayload, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    enforce_rate_limit(
        scope="admin-login",
        request=request,
        window_seconds=settings.login_rate_limit_window_seconds,
        max_requests=settings.login_rate_limit_max_attempts,
    )
    await ensure_default_admin(db)
    user = await authenticate_admin(db, username=payload.username, password=payload.password)
    if not user:
        await log_admin_action(
            db,
            principal=None,
            action="admin_login_failed",
            target="auth",
            method=request.method,
            path=request.url.path,
            status_code=401,
            detail_json={"username": payload.username},
            request=request,
        )
        response.status_code = 401
        return {"message": "用户名或密码错误。"}
    token, session = await create_admin_session(db, user=user, request=request)
    attach_auth_cookie(response, token)
    principal = await get_admin_principal(db, raw_token=token)
    await log_admin_action(
        db,
        principal=principal,
        action="admin_login",
        target="auth",
        method=request.method,
        path=request.url.path,
        status_code=200,
        detail_json={"session_id": str(session.id)},
        request=request,
    )
    return {"message": "登录成功。", "user": {"username": user.username}}


@router.post("/auth/logout")
async def admin_logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(settings.auth_cookie_name)
    principal = await get_admin_principal(db, raw_token=raw_token)
    await revoke_session(db, raw_token=raw_token)
    clear_auth_cookie(response)
    await log_admin_action(
        db,
        principal=principal,
        action="admin_logout",
        target="auth",
        method=request.method,
        path=request.url.path,
        status_code=200,
        request=request,
    )
    return {"message": "已退出登录。"}


@router.get("/auth/me")
async def admin_me(request: Request, db: AsyncSession = Depends(get_db)):
    principal = await get_admin_principal(db, raw_token=request.cookies.get(settings.auth_cookie_name))
    if not principal:
        return {"authenticated": False}
    return {"authenticated": True, "user": {"id": principal.user_id, "username": principal.username}}


@router.get("/audit-logs")
async def recent_audit_logs(request: Request, db: AsyncSession = Depends(get_db)):
    await require_admin_user(request, db)
    rows = await list_recent_audit_logs(db, limit=50)
    return [serialize_audit_log(row) for row in rows]
