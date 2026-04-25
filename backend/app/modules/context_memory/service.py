from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.provider_gateway import embedding
from app.models import LongTermMemoryEntity, MessageEntity, SessionMemoryEntity, SystemSettingEntity

settings = get_settings()
DEFAULT_MEMORY_CONFIG = {"short_turns": 6, "mid_turns": 8, "long_turns": 12}


@dataclass
class MemorySnapshot:
    short_term: list[dict]
    mid_summary: list[dict]
    long_count: int


def deterministic_embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()[:8]
    return [round((b / 255.0) * 2 - 1, 6) for b in digest]


def summarize_text(text: str, max_len: int = 100) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= max_len else compact[:max_len] + "..."


async def get_memory_config(db: AsyncSession) -> dict:
    row = await db.get(SystemSettingEntity, "memory_config")
    if not row:
        row = SystemSettingEntity(setting_key="memory_config", setting_value=DEFAULT_MEMORY_CONFIG)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row.setting_value


async def upsert_memory_config(db: AsyncSession, config: dict) -> dict:
    row = await db.get(SystemSettingEntity, "memory_config")
    if not row:
        row = SystemSettingEntity(setting_key="memory_config", setting_value=config)
        db.add(row)
    else:
        row.setting_value = config
    await db.commit()
    return config


async def ensure_session_memory(db: AsyncSession, session_id) -> SessionMemoryEntity:
    memory = await db.scalar(select(SessionMemoryEntity).where(SessionMemoryEntity.session_id == session_id))
    if memory:
        return memory
    cfg = await get_memory_config(db)
    memory = SessionMemoryEntity(
        session_id=session_id,
        short_turns=cfg["short_turns"],
        mid_turns=cfg["mid_turns"],
        long_turns=cfg["long_turns"],
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory


async def _embed_summary(db: AsyncSession, text: str) -> list[float]:
    try:
        vectors = await embedding(db, "siliconflow", settings.siliconflow_embedding_model, text)
        return vectors[0][:8]
    except Exception:  # noqa: BLE001
        if settings.simulation_enabled:
            return deterministic_embedding(text)
        raise


async def recompute_session_memory(db: AsyncSession, session_id) -> MemorySnapshot:
    memory = await ensure_session_memory(db, session_id)
    rows = (
        await db.scalars(
            select(MessageEntity).where(MessageEntity.session_id == session_id).order_by(MessageEntity.created_at.asc())
        )
    ).all()
    payload = [{"role": m.role, "text": m.text_content or "", "message_id": str(m.id)} for m in rows if m.text_content]
    short = payload[-memory.short_turns :]
    older = payload[: max(0, len(payload) - memory.short_turns)]
    mid_raw = older[-memory.mid_turns :]
    long_raw = older[: max(0, len(older) - memory.mid_turns)]

    memory.short_term = short
    memory.mid_summary = [{"summary": summarize_text(x["text"]), "message_id": x["message_id"]} for x in mid_raw]

    await db.execute(delete(LongTermMemoryEntity).where(LongTermMemoryEntity.session_id == session_id))
    for item in long_raw[-memory.long_turns :]:
        summary = summarize_text(item["text"])
        vec = await _embed_summary(db, summary)
        db.add(LongTermMemoryEntity(session_id=session_id, summary_text=summary, embedding=vec))
    await db.commit()
    long_count = len(long_raw[-memory.long_turns :])
    return MemorySnapshot(short_term=memory.short_term, mid_summary=memory.mid_summary, long_count=long_count)


async def clear_session_memory(db: AsyncSession, session_id) -> None:
    memory = await ensure_session_memory(db, session_id)
    memory.short_term = []
    memory.mid_summary = []
    await db.execute(delete(LongTermMemoryEntity).where(LongTermMemoryEntity.session_id == session_id))
    await db.commit()
