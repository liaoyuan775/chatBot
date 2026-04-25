from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ChainConfigEntity, ModelCatalogEntity, SessionEntity
from app.schemas.common import ChainUpsert


CHAIN_MODEL_LABELS = {
    "llm_model": "主对话模型",
    "asr_model": "ASR 模块",
    "tts_model": "TTS 模块",
    "embedding_model": "Embedding 模块",
    "rerank_model": "Rerank 模块",
    "image_model": "Image 扩展模型",
}


def derive_chain_mode(mapping_json: dict | None) -> str:
    mapping = mapping_json or {}
    explicit_mode = str(mapping.get("voice_runtime_mode") or "").strip().lower()
    if explicit_mode in {"split-chain", "split"}:
        return "split"
    if explicit_mode in {"integrated-realtime", "integrated"}:
        return "integrated"
    has_split_stage = bool(str(mapping.get("asr_model") or "").strip() or str(mapping.get("tts_model") or "").strip())
    return "split" if has_split_stage else "integrated"


def describe_chain_mode(mapping_json: dict | None) -> str:
    mode = derive_chain_mode(mapping_json)
    if mode == "split":
        return "可拆分链路：ASR / LLM / TTS 可按阶段配置，检索继续结合 Embedding / Rerank。"
    return "一体化链路：主模型承担实时语音主流程，检索继续结合 Embedding / Rerank。"

router = APIRouter(prefix="/api/chains", tags=["chains"])


def validate_chain_mapping(mapping_json: dict, enabled_models: set[str]) -> tuple[bool, list[str]]:
    required = ["llm_model"]
    optional = ["asr_model", "tts_model", "image_model", "embedding_model", "rerank_model"]
    present_keys = required + optional
    missing = [CHAIN_MODEL_LABELS.get(k, k) for k in required if not mapping_json.get(k)]
    disabled = [
        (CHAIN_MODEL_LABELS.get(k, k), str(mapping_json.get(k)))
        for k in present_keys
        if mapping_json.get(k) and str(mapping_json.get(k)) not in enabled_models
    ]
    errors: list[str] = []
    if missing:
        errors.append(f"缺少模型配置：{', '.join(missing)}")
    if disabled:
        disabled_text = ", ".join(f"{key}={model_name}" for key, model_name in disabled)
        errors.append(f"以下模型未启用：{disabled_text}")
    return len(errors) == 0, errors


async def get_chain_validation_result(db: AsyncSession, row: ChainConfigEntity | None) -> tuple[bool, list[str]]:
    if not row:
        return False, ["Chain not found."]
    enabled_models = {
        m.model_name for m in (await db.scalars(select(ModelCatalogEntity).where(ModelCatalogEntity.is_enabled.is_(True)))).all()
    }
    return validate_chain_mapping(row.mapping_json or {}, enabled_models)


async def _next_chain_copy_name(db: AsyncSession, base_name: str) -> str:
    candidate = f"{base_name}-copy"
    exists = await db.scalar(select(ChainConfigEntity).where(ChainConfigEntity.name == candidate))
    if not exists:
        return candidate
    idx = 2
    while True:
        candidate = f"{base_name}-copy-{idx}"
        exists = await db.scalar(select(ChainConfigEntity).where(ChainConfigEntity.name == candidate))
        if not exists:
            return candidate
        idx += 1


@router.get("")
async def list_chains(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(ChainConfigEntity).order_by(ChainConfigEntity.created_at.desc()))).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "is_default": r.is_default,
            "persona_id": str(r.persona_id) if r.persona_id else None,
            "voice_id": str(r.voice_id) if r.voice_id else None,
            "mapping_json": r.mapping_json,
            "is_valid": r.is_valid,
            "chain_mode": derive_chain_mode(r.mapping_json),
            "chain_summary": describe_chain_mode(r.mapping_json),
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.post("")
async def create_chain(payload: ChainUpsert, db: AsyncSession = Depends(get_db)):
    enabled_models = {
        m.model_name for m in (await db.scalars(select(ModelCatalogEntity).where(ModelCatalogEntity.is_enabled.is_(True)))).all()
    }
    is_valid, errors = validate_chain_mapping(payload.mapping_json, enabled_models)
    if payload.is_default:
        await db.execute(update(ChainConfigEntity).values(is_default=False))
    row = ChainConfigEntity(
        name=payload.name,
        is_default=payload.is_default,
        persona_id=payload.persona_id,
        voice_id=payload.voice_id,
        mapping_json=payload.mapping_json,
        is_valid=is_valid,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="链路名称已存在，请更换后重试。") from exc
    await db.refresh(row)
    return {"id": str(row.id), "is_valid": is_valid, "errors": errors, "message": "链路保存成功。"}


@router.post("/{chain_id}/validate")
async def validate_chain(chain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ChainConfigEntity, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chain not found.")
    is_valid, errors = await get_chain_validation_result(db, row)
    row.is_valid = is_valid
    await db.commit()
    return {"is_valid": is_valid, "errors": errors}


@router.get("/{chain_id}/validate")
async def get_chain_validation(chain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ChainConfigEntity, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chain not found.")
    is_valid, errors = await get_chain_validation_result(db, row)
    return {"is_valid": is_valid, "errors": errors}


@router.put("/{chain_id}")
async def update_chain(chain_id: uuid.UUID, payload: ChainUpsert, db: AsyncSession = Depends(get_db)):
    row = await db.get(ChainConfigEntity, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chain not found.")
    enabled_models = {
        m.model_name for m in (await db.scalars(select(ModelCatalogEntity).where(ModelCatalogEntity.is_enabled.is_(True)))).all()
    }
    is_valid, errors = validate_chain_mapping(payload.mapping_json, enabled_models)
    if payload.is_default:
        await db.execute(update(ChainConfigEntity).values(is_default=False))
    row.name = payload.name
    row.is_default = payload.is_default
    row.persona_id = payload.persona_id
    row.voice_id = payload.voice_id
    row.mapping_json = payload.mapping_json
    row.is_valid = is_valid
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="链路名称已存在，请更换后重试。") from exc
    return {"message": "链路修改成功。", "is_valid": is_valid, "errors": errors}


@router.delete("/{chain_id}")
async def delete_chain(chain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ChainConfigEntity, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chain not found.")
    default_chain = await db.scalar(
        select(ChainConfigEntity).where(ChainConfigEntity.is_default.is_(True), ChainConfigEntity.id != chain_id)
    )
    if default_chain:
        await db.execute(update(SessionEntity).where(SessionEntity.chain_id == chain_id).values(chain_id=default_chain.id))
    else:
        await db.execute(update(SessionEntity).where(SessionEntity.chain_id == chain_id).values(chain_id=None))
    await db.delete(row)
    await db.commit()
    return {"message": "链路删除成功。"}


@router.post("/{chain_id}/copy")
async def copy_chain(chain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ChainConfigEntity, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chain not found.")
    clone = ChainConfigEntity(
        name=await _next_chain_copy_name(db, row.name),
        is_default=False,
        persona_id=row.persona_id,
        voice_id=row.voice_id,
        mapping_json=row.mapping_json,
        is_valid=row.is_valid,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return {"id": str(clone.id), "message": "链路复制成功。"}
