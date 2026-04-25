from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.models import CallConfigEntity
from app.modules.chat.engine import ensure_default_call_config
from app.schemas.common import CallConfigUpsert

router = APIRouter(prefix="/api/call-config", tags=["call-config"])
settings = get_settings()


def _to_dict(row: CallConfigEntity) -> dict:
    return {
        "id": str(row.id),
        "main_provider": row.main_provider,
        "main_model": row.main_model,
        "omni_mode": row.omni_mode,
        "fallback_asr_provider": row.fallback_asr_provider,
        "fallback_asr_model": row.fallback_asr_model,
        "fallback_llm_provider": row.fallback_llm_provider,
        "fallback_llm_model": row.fallback_llm_model,
        "fallback_tts_provider": row.fallback_tts_provider,
        "fallback_tts_model": row.fallback_tts_model,
        "fallback_tts_voice": row.fallback_tts_voice,
        "updated_at": row.updated_at,
    }


@router.post("/init-defaults")
async def init_defaults(db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(CallConfigEntity).order_by(CallConfigEntity.updated_at.desc()))
    if not row:
        row = await ensure_default_call_config(db)
    else:
        row.main_provider = "dashscope"
        row.main_model = settings.dashscope_realtime_model
        row.omni_mode = "auto"
        row.fallback_asr_provider = "siliconflow"
        row.fallback_asr_model = settings.siliconflow_asr_model
        row.fallback_llm_provider = "volcengine"
        row.fallback_llm_model = settings.volcengine_text_model
        row.fallback_tts_provider = "siliconflow"
        row.fallback_tts_model = settings.siliconflow_tts_model
        row.fallback_tts_voice = settings.siliconflow_tts_voice
        await db.commit()
        await db.refresh(row)
    return {"message": "Default call config initialized.", "config": _to_dict(row)}


@router.get("")
async def get_call_config(db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(CallConfigEntity).order_by(CallConfigEntity.updated_at.desc()))
    if not row:
        row = await ensure_default_call_config(db)
    return _to_dict(row)


@router.put("")
async def update_call_config(payload: CallConfigUpsert, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(CallConfigEntity).order_by(CallConfigEntity.updated_at.desc()))
    if not row:
        row = CallConfigEntity(**payload.model_dump())
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return {"message": "Call config updated.", "config": _to_dict(row)}
