from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.context_memory.service import (
    clear_session_memory,
    get_memory_config,
    recompute_session_memory,
    upsert_memory_config,
)
from app.schemas.common import MemoryConfigUpdate

router = APIRouter(prefix="/api/context", tags=["context"])


@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db)):
    return await get_memory_config(db)


@router.put("/config")
async def update_config(payload: MemoryConfigUpdate, db: AsyncSession = Depends(get_db)):
    return await upsert_memory_config(db, payload.model_dump())


@router.get("/sessions/{session_id}")
async def get_session_memory_snapshot(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    snapshot = await recompute_session_memory(db, session_id)
    return {
        "short_term": snapshot.short_term,
        "mid_summary": snapshot.mid_summary,
        "long_count": snapshot.long_count,
    }


@router.post("/sessions/{session_id}/compress")
async def compress_session_context(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    snapshot = await recompute_session_memory(db, session_id)
    return {"message": "Context compressed.", "snapshot": snapshot.__dict__}


@router.post("/sessions/{session_id}/clear")
async def clear_context(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await clear_session_memory(db, session_id)
    return {"message": "Current session context cleared."}


@router.get("/sessions/{session_id}/export")
async def export_session_context(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    snapshot = await recompute_session_memory(db, session_id)
    lines = ["# Session Context Export", "", "## Short-Term Context"]
    for item in snapshot.short_term:
        lines.append(f"- {item.get('role')}: {item.get('text')}")
    lines.extend(["", "## Mid-Term Summaries"])
    for item in snapshot.mid_summary:
        lines.append(f"- {item.get('summary')}")
    lines.extend(["", "## Long-Term Memory Count", f"- {snapshot.long_count}"])
    return {"file_name": f"session_{session_id}_context.txt", "content": "\n".join(lines)}
