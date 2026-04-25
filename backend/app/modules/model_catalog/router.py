from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ModelCatalogEntity, ProviderConfigEntity
from app.schemas.common import ModelBatchStatusUpdate, ModelRename, ModelStatusUpdate

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models(
    model_type: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    provider_name: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    query = select(ModelCatalogEntity)
    if model_type:
        query = query.where(ModelCatalogEntity.model_type == model_type)
    if enabled is not None:
        query = query.where(ModelCatalogEntity.is_enabled == enabled)
    rows = (await db.scalars(query.order_by(ModelCatalogEntity.model_type.asc(), ModelCatalogEntity.model_name.asc()))).all()

    provider_map = {
        str(p.id): p.provider_name
        for p in (await db.scalars(select(ProviderConfigEntity).order_by(ProviderConfigEntity.provider_name.asc()))).all()
    }
    result = []
    for row in rows:
        p_name = provider_map.get(str(row.provider_id), "unknown")
        if provider_name and p_name != provider_name:
            continue
        result.append(
            {
                "id": str(row.id),
                "provider_name": p_name,
                "model_name": row.model_name,
                "model_type": row.model_type,
                "is_enabled": row.is_enabled,
                "is_available": row.is_available,
                "alias": row.alias,
                "metadata_json": row.metadata_json,
            }
        )
    return result


@router.get("/{model_id}")
async def get_model_detail(model_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ModelCatalogEntity, model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model not found.")
    provider = await db.get(ProviderConfigEntity, row.provider_id)
    return {
        "id": str(row.id),
        "provider_name": provider.provider_name if provider else "unknown",
        "model_name": row.model_name,
        "model_type": row.model_type,
        "is_enabled": row.is_enabled,
        "is_available": row.is_available,
        "alias": row.alias,
        "metadata_json": row.metadata_json,
    }


@router.patch("/{model_id}/status")
async def update_model_status(model_id: uuid.UUID, payload: ModelStatusUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(ModelCatalogEntity, model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model not found.")
    row.is_enabled = payload.is_enabled
    await db.commit()
    return {"message": "Model status updated."}


@router.patch("/{model_id}/rename")
async def rename_model(model_id: uuid.UUID, payload: ModelRename, db: AsyncSession = Depends(get_db)):
    row = await db.get(ModelCatalogEntity, model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model not found.")
    row.alias = payload.alias
    await db.commit()
    return {"message": "Model alias updated."}


@router.post("/batch-status")
async def batch_update_model_status(payload: ModelBatchStatusUpdate, db: AsyncSession = Depends(get_db)):
    if not payload.model_ids:
        return {"message": "No models selected.", "updated_count": 0}
    await db.execute(
        update(ModelCatalogEntity)
        .where(ModelCatalogEntity.id.in_(payload.model_ids))
        .values(is_enabled=payload.is_enabled)
    )
    await db.commit()
    return {"message": "Batch model status updated.", "updated_count": len(payload.model_ids)}
