from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import KnowledgeChunkEntity, KnowledgeDocumentEntity, LongTermMemoryEntity, SessionEntity, SystemSettingEntity
from app.schemas.common import SettingUpsert

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "voice_params": {"tts_rate": 1.0, "play_mode": "auto"},
    "exception_rules": {"retry_count": 2, "display_mode": "text"},
    "knowledge_retrieval_config": {
        "top_k": 3,
        "similarity_threshold": 0.0,
        "rag_timeout_ms": 1500,
        "no_result_message": "未查询到相关知识，我将为您进行通用解答。",
    },
    "knowledge_global": {"enabled": True},
}


@router.get("")
async def list_settings(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(SystemSettingEntity).order_by(SystemSettingEntity.setting_key.asc()))).all()
    return [{"setting_key": r.setting_key, "setting_value": r.setting_value, "updated_at": r.updated_at} for r in rows]


@router.put("/{setting_key}")
async def upsert_setting(setting_key: str, payload: SettingUpsert, db: AsyncSession = Depends(get_db)):
    row = await db.get(SystemSettingEntity, setting_key)
    if not row:
        row = SystemSettingEntity(setting_key=setting_key, setting_value=payload.setting_value)
        db.add(row)
    else:
        row.setting_value = payload.setting_value
    await db.commit()
    return {"message": "Setting saved."}


@router.get("/database/status")
async def database_status(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "connected"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "disconnected", "reason": str(exc)}


@router.post("/data/clear-history")
async def clear_history(confirm: bool = Query(default=False), db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Dangerous operation requires confirm=true.")
    await db.execute(delete(SessionEntity))
    await db.commit()
    return {"message": "All chat history cleared."}


@router.post("/data/clear-long-memory")
async def clear_long_memory(confirm: bool = Query(default=False), db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Dangerous operation requires confirm=true.")
    await db.execute(delete(LongTermMemoryEntity))
    await db.commit()
    return {"message": "All long-term memory cleared."}


@router.post("/data/clear-knowledge-vectors")
async def clear_knowledge_vectors(confirm: bool = Query(default=False), db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Dangerous operation requires confirm=true.")
    await db.execute(delete(KnowledgeChunkEntity))
    await db.execute(delete(KnowledgeDocumentEntity))
    await db.commit()
    return {"message": "All knowledge vectors cleared."}


@router.post("/restore-defaults")
async def restore_defaults(db: AsyncSession = Depends(get_db)):
    for setting_key, setting_value in DEFAULT_SETTINGS.items():
        row = await db.get(SystemSettingEntity, setting_key)
        if not row:
            row = SystemSettingEntity(setting_key=setting_key, setting_value=setting_value)
            db.add(row)
        else:
            row.setting_value = setting_value
    await db.commit()
    return {"message": "System defaults restored.", "keys": list(DEFAULT_SETTINGS.keys())}
