from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.provider_gateway import chat_completion
from app.models import ChainConfigEntity, PersonaEntity, SessionEntity
from app.modules.chat.engine import ensure_default_call_config
from app.schemas.common import PersonaPreviewRequest, PersonaUpsert

router = APIRouter(prefix="/api/personas", tags=["personas"])


async def _next_persona_copy_name(db: AsyncSession, base_name: str) -> str:
    candidate = f"{base_name}-copy"
    exists = await db.scalar(select(PersonaEntity).where(PersonaEntity.name == candidate))
    if not exists:
        return candidate
    idx = 2
    while True:
        candidate = f"{base_name}-copy-{idx}"
        exists = await db.scalar(select(PersonaEntity).where(PersonaEntity.name == candidate))
        if not exists:
            return candidate
        idx += 1


@router.get("")
async def list_personas(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(PersonaEntity).order_by(PersonaEntity.created_at.desc()))).all()
    return [
        {"id": str(r.id), "name": r.name, "is_default": r.is_default, "config_json": r.config_json, "created_at": r.created_at}
        for r in rows
    ]


@router.post("")
async def create_persona(payload: PersonaUpsert, db: AsyncSession = Depends(get_db)):
    if payload.is_default:
        await db.execute(update(PersonaEntity).values(is_default=False))
    row = PersonaEntity(name=payload.name, is_default=payload.is_default, config_json=payload.config_json)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="人格名称已存在，请更换后重试。") from exc
    await db.refresh(row)
    return {"id": str(row.id), "message": "人格创建成功。"}


@router.post("/{persona_id}/copy")
async def copy_persona(persona_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(PersonaEntity, persona_id)
    if not row:
        raise HTTPException(status_code=404, detail="Persona not found.")
    clone = PersonaEntity(name=await _next_persona_copy_name(db, row.name), is_default=False, config_json=row.config_json)
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return {"id": str(clone.id), "message": "人格复制成功。"}


@router.post("/{persona_id}/preview")
async def preview_persona(persona_id: uuid.UUID, payload: PersonaPreviewRequest, db: AsyncSession = Depends(get_db)):
    row = await db.get(PersonaEntity, persona_id)
    if not row:
        raise HTTPException(status_code=404, detail="Persona not found.")
    config = row.config_json or {}
    system_prompt = (
        f"Role: {config.get('role', 'assistant')}\n"
        f"Style: {config.get('style', 'professional')}\n"
        f"Tone: {config.get('tone', 'calm')}\n"
        f"Strictness: {config.get('strictness', 'medium')}\n"
        f"Allow question back: {config.get('allow_question_back', False)}\n"
        f"Unknown answer: {config.get('unknown_answer', 'I will verify first.')}"
    )
    cfg = await ensure_default_call_config(db)
    try:
        reply = await chat_completion(
            db,
            cfg.fallback_llm_provider,
            cfg.fallback_llm_model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": payload.prompt},
            ],
        )
    except Exception:
        fallback_unknown = str(config.get("unknown_answer") if config.get("unknown_answer") is not None else "这个问题我暂时没有可靠依据。")
        reply = f"{fallback_unknown}（预览降级响应）"
    return {"reply": reply}


@router.put("/{persona_id}")
async def update_persona(persona_id: uuid.UUID, payload: PersonaUpsert, db: AsyncSession = Depends(get_db)):
    row = await db.get(PersonaEntity, persona_id)
    if not row:
        raise HTTPException(status_code=404, detail="Persona not found.")
    if payload.is_default:
        await db.execute(update(PersonaEntity).values(is_default=False))
    row.name = payload.name
    row.is_default = payload.is_default
    row.config_json = payload.config_json
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="人格名称已存在，请更换后重试。") from exc
    return {"message": "人格更新成功。"}


@router.delete("/{persona_id}")
async def delete_persona(persona_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(PersonaEntity, persona_id)
    if not row:
        raise HTTPException(status_code=404, detail="Persona not found.")
    default_persona = await db.scalar(select(PersonaEntity).where(PersonaEntity.is_default.is_(True), PersonaEntity.id != persona_id))
    replacement = default_persona.id if default_persona else None
    await db.execute(update(ChainConfigEntity).where(ChainConfigEntity.persona_id == persona_id).values(persona_id=replacement))
    await db.execute(update(SessionEntity).where(SessionEntity.persona_id == persona_id).values(persona_id=replacement))
    await db.delete(row)
    await db.commit()
    return {"message": "人格删除成功。"}
