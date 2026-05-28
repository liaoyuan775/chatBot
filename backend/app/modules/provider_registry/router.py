from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.provider_gateway import ProviderError, decrypt_api_key, encrypt_api_key, list_models_remote
from app.models import ModelCatalogEntity, ProviderConfigEntity
from app.modules.provider_registry.service import infer_model_capabilities, infer_model_type, test_connectivity
from app.schemas.common import ProviderUpsert

router = APIRouter(prefix="/api/providers", tags=["providers"])

PROVIDER_TEMPLATES = [
    {"provider_name": "dashscope", "base_url": "https://dashscope.aliyuncs.com"},
    {"provider_name": "deepseek", "base_url": "https://api.deepseek.com"},
    {"provider_name": "volcengine", "base_url": "https://ark.cn-beijing.volces.com/api/v3"},
    {"provider_name": "siliconflow", "base_url": "https://api.siliconflow.cn"},
    {"provider_name": "openai", "base_url": "https://api.openai.com/v1"},
    {"provider_name": "glm", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
    {"provider_name": "kimi", "base_url": "https://api.moonshot.cn/v1"},
    {"provider_name": "minimax", "base_url": "https://api.minimax.chat/v1"},
]


def _mask_api_key(raw: str | None) -> str | None:
    if not raw:
        return None
    clean = raw.strip()
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:6]}{'*' * max(4, len(clean) - 10)}{clean[-4:]}"


@router.get("/templates")
async def list_provider_templates():
    return PROVIDER_TEMPLATES


@router.get("")
async def list_providers(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(ProviderConfigEntity).order_by(ProviderConfigEntity.provider_name.asc()))).all()
    result = []
    for r in rows:
        try:
            key_raw = await decrypt_api_key(db, r.id)
        except Exception:  # noqa: BLE001
            key_raw = None
        result.append(
            {
                "id": str(r.id),
                "provider_name": r.provider_name,
                "base_url": r.base_url,
                "timeout_seconds": r.timeout_seconds,
                "status": r.status,
                "api_key_masked": _mask_api_key(key_raw),
                "has_api_key": bool(key_raw),
                "updated_at": r.updated_at,
            }
        )
    return result


@router.put("/{provider_name}")
async def upsert_provider(provider_name: str, payload: ProviderUpsert, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name))
    if not row:
        row = ProviderConfigEntity(
            provider_name=provider_name,
            api_key_enc=None,
            base_url=payload.base_url,
            timeout_seconds=payload.timeout_seconds,
            status="configured",
        )
        db.add(row)
        await db.flush()
    else:
        row.base_url = payload.base_url or row.base_url
        row.timeout_seconds = payload.timeout_seconds
        row.status = "configured"

    if payload.api_key:
        await encrypt_api_key(db, row.id, payload.api_key)
    await db.commit()
    return {"message": "Provider config saved."}


@router.post("/{provider_name}/test")
async def test_provider(provider_name: str, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name))
    if not row:
        raise HTTPException(status_code=404, detail="Provider is not configured.")
    ok, msg = await test_connectivity(db, provider_name)
    row.status = "connected" if ok else "error"
    await db.commit()
    return {"success": ok, "message": msg}


@router.post("/{provider_name}/sync-models")
async def sync_models(provider_name: str, db: AsyncSession = Depends(get_db)):
    provider = await db.scalar(select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider is not configured.")
    if provider.status != "connected":
        raise HTTPException(status_code=400, detail="Provider is not connected.")

    try:
        remote_models = await list_models_remote(db, provider_name)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    synced = 0
    for item in remote_models:
        model_name = str(item.get("id") or item.get("model") or "")
        if not model_name:
            continue
        exists = await db.scalar(
            select(ModelCatalogEntity).where(
                ModelCatalogEntity.provider_id == provider.id,
                ModelCatalogEntity.model_name == model_name,
            )
        )
        model_type = infer_model_type(model_name)
        capabilities = infer_model_capabilities(model_name, item)
        metadata = dict(item)
        metadata["capabilities"] = capabilities
        if not exists:
            db.add(
                ModelCatalogEntity(
                    provider_id=provider.id,
                    model_name=model_name,
                    model_type=model_type,
                    is_enabled=False,
                    is_available=True,
                    metadata_json=metadata,
                )
            )
            synced += 1
        else:
            exists.is_available = True
            exists.model_type = model_type
            exists.metadata_json = metadata
    await db.commit()
    return {"message": "Models synced.", "synced_count": synced}


@router.delete("/{provider_name}")
async def delete_provider(provider_name: str, db: AsyncSession = Depends(get_db)):
    provider = await db.scalar(select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider is not configured.")
    await db.execute(
        update(ModelCatalogEntity)
        .where(ModelCatalogEntity.provider_id == provider.id)
        .values(is_enabled=False, is_available=False)
    )
    await db.delete(provider)
    await db.commit()
    return {"message": "Provider removed and related models disabled."}


@router.post("/{provider_name}/disable")
async def disable_provider(provider_name: str, db: AsyncSession = Depends(get_db)):
    provider = await db.scalar(select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider is not configured.")
    await db.execute(
        update(ModelCatalogEntity)
        .where(ModelCatalogEntity.provider_id == provider.id)
        .values(is_enabled=False)
    )
    provider.status = "disabled"
    await db.commit()
    return {"message": "Provider disabled and models are disabled."}
