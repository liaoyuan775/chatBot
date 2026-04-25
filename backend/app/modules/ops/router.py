from __future__ import annotations

from collections import Counter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request

from app.core.database import get_db
from app.models import MessageEntity, ProviderConfigEntity, SessionChainAuditEntity, SystemSettingEntity
from app.modules.admin_auth.service import require_admin_user

router = APIRouter(prefix="/api/admin/ops", tags=["ops"])


@router.get("/diagnostics")
async def diagnostics(request: Request, db: AsyncSession = Depends(get_db)):
    await require_admin_user(request, db)
    providers = (await db.scalars(select(ProviderConfigEntity).order_by(ProviderConfigEntity.provider_name.asc()))).all()
    settings_rows = (await db.scalars(select(SystemSettingEntity))).all()
    recent_audits = (
        await db.scalars(
            select(SessionChainAuditEntity).order_by(SessionChainAuditEntity.created_at.desc()).limit(50)
        )
    ).all()
    message_total = await db.scalar(select(func.count()).select_from(MessageEntity)) or 0
    failures = [row for row in recent_audits if not row.success]
    failure_reasons = Counter((row.fail_reason or "unknown")[:80] for row in failures)
    latency_values = [
        int((row.trace_json or {}).get("latency_ms", 0) or 0)
        for row in recent_audits
        if int((row.trace_json or {}).get("latency_ms", 0) or 0) > 0
    ]
    avg_latency = int(sum(latency_values) / len(latency_values)) if latency_values else 0

    return {
        "service": {
            "status": "ok",
            "message_total": int(message_total),
            "settings_count": len(settings_rows),
        },
        "providers": [
            {
                "provider_name": row.provider_name,
                "status": row.status,
                "base_url": row.base_url,
                "timeout_seconds": row.timeout_seconds,
                "has_api_key": bool(row.api_key_enc),
            }
            for row in providers
        ],
        "recent_chain_audits": {
            "count": len(recent_audits),
            "failure_count": len(failures),
            "avg_latency_ms": avg_latency,
            "top_failures": [{"reason": reason, "count": count} for reason, count in failure_reasons.most_common(10)],
        },
        "required_settings": {
            "knowledge_global": any(row.setting_key == "knowledge_global" for row in settings_rows),
            "knowledge_retrieval_config": any(row.setting_key == "knowledge_retrieval_config" for row in settings_rows),
        },
    }
