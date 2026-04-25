from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.database import SessionLocal
from app.modules.admin_auth.service import (
    EXEMPT_PATHS,
    MANAGEMENT_PREFIXES,
    get_admin_principal,
    log_admin_action,
    request_requires_admin,
    require_admin_user,
    settings,
    enforce_rate_limit,
)


class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path not in EXEMPT_PATHS and request.method.upper() != "OPTIONS" and request.url.path.startswith(("/api/messages", "/ws/realtime-chat")):
            enforce_rate_limit(
                scope="chat-api",
                request=request,
                window_seconds=settings.chat_rate_limit_window_seconds,
                max_requests=settings.chat_rate_limit_max_requests,
            )

        principal = None
        if request_requires_admin(request):
            async with SessionLocal() as db:
                await require_admin_user(request, db)
                principal = await get_admin_principal(db, raw_token=request.cookies.get(settings.auth_cookie_name))

        response = await call_next(request)

        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and any(request.url.path.startswith(prefix) for prefix in MANAGEMENT_PREFIXES):
            async with SessionLocal() as db:
                if principal is None:
                    principal = await get_admin_principal(db, raw_token=request.cookies.get(settings.auth_cookie_name))
                await log_admin_action(
                    db,
                    principal=principal,
                    action="config_mutation",
                    target=request.url.path.split("/")[3] if len(request.url.path.split("/")) > 3 else request.url.path,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    detail_json={"query": dict(request.query_params)},
                    request=request,
                )
        return response
