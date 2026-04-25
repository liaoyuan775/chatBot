from __future__ import annotations

import asyncio
import json
import re
import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.provider_gateway import tts_synthesize
from app.models import ChainConfigEntity, MessageEntity, PersonaEntity, SessionEntity, VoiceProfileEntity
from app.modules.chat.engine import resolve_session_runtime, run_single_asr_with_trace
from app.modules.chat.langchain_pipeline import stream_text_chain_lcel
from app.modules.chat.service import (
    DEFAULT_SESSION_TITLE,
    build_retrieval_metrics_payload,
    build_turn_metrics_payload,
    build_assistant_reply,
    build_assistant_reply_from_prepared,
    prepare_assistant_turn,
    summarize_session_title,
    sync_memory_after_chat,
)
from app.schemas.common import MessageCreate, MessageEdit, SessionCreate, SessionUpdate

router = APIRouter(tags=["chat"])
settings = get_settings()

LEGACY_GARBLED_TITLES = {"鏂板缓浼氳瘽", "New Session"}


async def _session_summary_map(db: AsyncSession) -> dict[str, str]:
    sessions = (await db.scalars(select(SessionEntity))).all()
    session_ids = [row.id for row in sessions]
    if not session_ids:
        return {}
    messages = (
        await db.scalars(
            select(MessageEntity)
            .where(MessageEntity.session_id.in_(session_ids), MessageEntity.role == "user")
            .order_by(MessageEntity.created_at.asc())
        )
    ).all()
    summary_map: dict[str, str] = {}
    for item in messages:
        key = str(item.session_id)
        if key in summary_map:
            continue
        text = (item.text_content or "").strip()
        if text:
            summary_map[key] = text[:40]
    return summary_map


def _normalize_session_title(title: str | None) -> str:
    text = (title or "").strip()
    if text in LEGACY_GARBLED_TITLES or not text:
        return DEFAULT_SESSION_TITLE
    return text


def _normalize_audio_mime(audio_base64: str, audio_mime: str) -> str:
    if audio_mime == "audio/mpeg" and audio_base64.startswith("UklGR"):
        return "audio/wav"
    return audio_mime


def _normalize_provider_voice(provider_name: str, voice_name: str | None) -> str:
    provider = (provider_name or "").strip().lower()
    voice = (voice_name or "").strip()
    if provider == "dashscope":
        if not voice or "/" in voice or ":" in voice:
            return settings.dashscope_tts_voice
        return voice
    if provider == "siliconflow":
        return voice or settings.siliconflow_tts_voice
    return voice or settings.siliconflow_tts_voice


async def _synthesize_assistant_audio(
    db: AsyncSession,
    session_id: uuid.UUID,
    text: str,
) -> tuple[str | None, dict[str, Any], list[str]]:
    runtime = await resolve_session_runtime(db, session_id)
    main_voice = _normalize_provider_voice(runtime.realtime_main_provider, runtime.tts_voice)
    default_voice = _normalize_provider_voice(runtime.tts_provider, runtime.tts_voice)
    candidate_tts = [
        (
            runtime.realtime_main_provider,
            runtime.realtime_main_model,
            main_voice,
            "main_omni_model",
        )
        if runtime.use_main_for_tts
        else (runtime.tts_provider, runtime.tts_model, default_voice, "fallback_tts"),
        (runtime.tts_provider, runtime.tts_model, default_voice, "fallback_tts"),
        ("dashscope", settings.dashscope_tts_model, settings.dashscope_tts_voice, "fallback_tts"),
        ("siliconflow", settings.siliconflow_tts_model, settings.siliconflow_tts_voice, "fallback_tts"),
    ]
    seen: set[tuple[str, str, str, str]] = set()
    errors: list[str] = []
    for provider, model, voice, source in candidate_tts:
        key = (str(provider or "").strip(), str(model or "").strip(), str(voice or "").strip(), str(source or "").strip())
        if not all(key[:3]) or key in seen:
            continue
        seen.add(key)
        try:
            audio_base64, audio_mime = await tts_synthesize(
                db,
                key[0],
                key[1],
                key[2],
                text,
                response_format="mp3",
                stream=False,
            )
            if not audio_base64:
                errors.append(f"{key[0]}/{key[1]} returned empty audio.")
                continue
            normalized_mime = _normalize_audio_mime(audio_base64, audio_mime)
            return (
                f"data:{normalized_mime};base64,{audio_base64}",
                {
                    "audio_mime": normalized_mime,
                    "voice_used": key[2],
                    "tts_provider": key[0],
                    "tts_model": key[1],
                    "tts_source": key[3],
                },
                errors,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key[0]}/{key[1]}: {exc}")
            continue
    return None, {}, errors


@router.get("/api/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(SessionEntity).order_by(SessionEntity.created_at.desc()))).all()
    chains = {str(row.id): row.name for row in (await db.scalars(select(ChainConfigEntity))).all()}
    personas = {str(row.id): row.name for row in (await db.scalars(select(PersonaEntity))).all()}
    voices = {str(row.id): row.name for row in (await db.scalars(select(VoiceProfileEntity))).all()}
    summary_map = await _session_summary_map(db)
    return [
        {
            "id": str(r.id),
            "title": _normalize_session_title(r.title),
            "status": r.status,
            "knowledge_enabled": r.knowledge_enabled,
            "chain_id": str(r.chain_id) if r.chain_id else None,
            "persona_id": str(r.persona_id) if r.persona_id else None,
            "voice_id": str(r.voice_id) if r.voice_id else None,
            "chain_name": chains.get(str(r.chain_id), "未绑定链路") if r.chain_id else "未绑定链路",
            "persona_name": personas.get(str(r.persona_id), "未绑定人格") if r.persona_id else "未绑定人格",
            "voice_name": voices.get(str(r.voice_id), "未绑定音色") if r.voice_id else "未绑定音色",
            "summary": summary_map.get(str(r.id), ""),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.post("/api/sessions")
async def create_session(payload: SessionCreate, db: AsyncSession = Depends(get_db)):
    default_chain = await db.scalar(select(ChainConfigEntity).where(ChainConfigEntity.is_default.is_(True)))
    default_persona = await db.scalar(select(PersonaEntity).where(PersonaEntity.is_default.is_(True)))
    default_voice = await db.scalar(select(VoiceProfileEntity).where(VoiceProfileEntity.is_default.is_(True)))
    row = SessionEntity(
        title=_normalize_session_title(payload.title),
        chain_id=default_chain.id if default_chain else None,
        persona_id=default_persona.id if default_persona else None,
        voice_id=default_voice.id if default_voice else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": str(row.id), "message": "会话创建成功。"}


@router.patch("/api/sessions/{session_id}")
async def update_session(session_id: uuid.UUID, payload: SessionUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(SessionEntity, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Session updated."}


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(SessionEntity, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")
    chain = await db.get(ChainConfigEntity, row.chain_id) if row.chain_id else None
    persona = await db.get(PersonaEntity, row.persona_id) if row.persona_id else None
    voice = await db.get(VoiceProfileEntity, row.voice_id) if row.voice_id else None
    summary_map = await _session_summary_map(db)
    return {
        "id": str(row.id),
        "title": _normalize_session_title(row.title),
        "status": row.status,
        "knowledge_enabled": row.knowledge_enabled,
        "chain_id": str(row.chain_id) if row.chain_id else None,
        "persona_id": str(row.persona_id) if row.persona_id else None,
        "voice_id": str(row.voice_id) if row.voice_id else None,
        "chain_name": chain.name if chain else "未绑定链路",
        "persona_name": persona.name if persona else "未绑定人格",
        "voice_name": voice.name if voice else "未绑定音色",
        "summary": summary_map.get(str(row.id), ""),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: uuid.UUID, confirm: bool = Query(default=False), db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Dangerous operation requires confirm=true.")
    row = await db.get(SessionEntity, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")
    await db.delete(row)
    await db.commit()
    return {"message": "Session deleted."}


@router.post("/api/sessions/batch-delete")
async def batch_delete_sessions(
    session_ids: list[uuid.UUID], confirm: bool = Query(default=False), db: AsyncSession = Depends(get_db)
):
    if not confirm:
        raise HTTPException(status_code=400, detail="Dangerous operation requires confirm=true.")
    await db.execute(delete(SessionEntity).where(SessionEntity.id.in_(session_ids)))
    await db.commit()
    return {"message": "Batch delete completed.", "deleted_count": len(session_ids)}


@router.get("/api/messages")
async def list_messages(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(select(MessageEntity).where(MessageEntity.session_id == session_id).order_by(MessageEntity.created_at.asc()))
    ).all()
    return [
        {
            "id": str(r.id),
            "session_id": str(r.session_id),
            "role": r.role,
            "content_type": r.content_type,
            "text_content": r.text_content,
            "image_url": r.image_url,
            "audio_url": r.audio_url,
            "metadata_json": r.metadata_json,
            "replaced": r.replaced,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/api/messages/stream")
async def create_message_stream(payload: MessageCreate, db: AsyncSession = Depends(get_db)):
    session = await db.get(SessionEntity, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    async def event_stream():
        def _extract_sentences(buffer: str) -> tuple[list[str], str]:
            if not buffer:
                return [], ""
            parts: list[str] = []
            start = 0
            for idx, char in enumerate(buffer):
                if char in "。！？!?；;\n":
                    sentence = buffer[start : idx + 1].strip()
                    if sentence:
                        parts.append(sentence)
                    start = idx + 1
            return parts, buffer[start:]

        turn_started = perf_counter()
        user_msg = MessageEntity(
            session_id=payload.session_id,
            role="user",
            content_type=payload.content_type,
            text_content=payload.text_content,
            image_url=payload.image_url,
        )
        db.add(user_msg)
        await db.flush()

        prepared = await prepare_assistant_turn(db, session, payload.text_content)
        if prepared.retrieval_latency_ms is not None:
            yield json.dumps(
                {
                    "event": "metrics.retrieval",
                    "retrieval": build_retrieval_metrics_payload(prepared),
                },
                ensure_ascii=False,
            ) + "\n"

        if prepared.image_prompt:
            reply = await build_assistant_reply_from_prepared(db, session, payload.text_content, prepared=prepared)
            assistant_metadata = {
                "chain_name": reply.chain_name,
                "pipeline": reply.pipeline,
                "fallback_reason": reply.fallback_reason,
                "voice_used": reply.voice_used,
                "provider_trace": reply.provider_trace,
                "retrieval_gate": {
                    "decision": prepared.retrieval_decision,
                    "gate_reason": prepared.retrieval_gate_reason,
                    "reason": prepared.retrieval_reason,
                    "timed_out": prepared.retrieval_timed_out,
                },
            }
            db.add(
                MessageEntity(
                    session_id=payload.session_id,
                    role="assistant",
                    content_type=reply.content_type,
                    text_content=reply.text,
                    image_url=reply.image_url,
                    audio_url=None,
                    metadata_json=assistant_metadata,
                )
            )
            if (session.title or "").strip() in {"", DEFAULT_SESSION_TITLE, "New Session"} and (payload.text_content or "").strip():
                session.title = DEFAULT_SESSION_TITLE
                await summarize_session_title(db, session, payload.text_content or "")
            await db.commit()
            await sync_memory_after_chat(db, payload.session_id)
            yield json.dumps(
                {
                    "text": reply.text,
                    "image_url": reply.image_url,
                    "done": True,
                    "metrics": {
                        "context_latency_ms": prepared.context_latency_ms,
                        "retrieval_latency_ms": prepared.retrieval_latency_ms,
                        "total_latency_ms": int((perf_counter() - turn_started) * 1000),
                    },
                },
                ensure_ascii=False,
            ) + "\n"
            return

        runtime = prepared.runtime
        accumulated_text = ""
        llm_started = perf_counter()
        tts_sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
        event_queue: asyncio.Queue[str | None] = asyncio.Queue()
        sentence_buffer = ""
        first_text_latency_ms: int | None = None
        first_audio_latency_ms: int | None = None
        llm_error: str | None = None

        async def produce_stream() -> None:
            nonlocal accumulated_text, first_text_latency_ms, sentence_buffer, llm_error
            try:
                async for delta in stream_text_chain_lcel(
                    db=db,
                    provider_name=runtime.text_llm_provider,
                    model_name=runtime.text_llm_model,
                    user_text=(payload.text_content or "").strip(),
                    context_text=prepared.context_hint,
                    knowledge_text=prepared.knowledge_text,
                    system_prompt=runtime.persona_system_prompt,
                ):
                    if not delta:
                        continue
                    accumulated_text = f"{accumulated_text}{delta}"
                    sentence_buffer = f"{sentence_buffer}{delta}"
                    if first_text_latency_ms is None:
                        first_text_latency_ms = int((perf_counter() - turn_started) * 1000)
                    await event_queue.put(json.dumps({"text": accumulated_text, "done": False}, ensure_ascii=False) + "\n")
                    ready_sentences, sentence_buffer = _extract_sentences(sentence_buffer)
                    for sentence in ready_sentences:
                        await tts_sentence_queue.put(sentence)
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
            finally:
                if sentence_buffer.strip():
                    await tts_sentence_queue.put(sentence_buffer.strip())
                await tts_sentence_queue.put(None)

        async def tts_worker() -> None:
            nonlocal first_audio_latency_ms
            while True:
                sentence = await tts_sentence_queue.get()
                if sentence is None:
                    await event_queue.put(None)
                    return
                try:
                    audio_url, _audio_meta, _tts_errors = await _synthesize_assistant_audio(db, payload.session_id, sentence)
                    if not audio_url:
                        continue
                    match = re.match(r"^data:([^;]+);base64,(.+)$", str(audio_url))
                    if not match:
                        continue
                    if first_audio_latency_ms is None:
                        first_audio_latency_ms = int((perf_counter() - turn_started) * 1000)
                    await event_queue.put(
                        json.dumps(
                            {
                                "event": "assistant.audio.delta",
                                "audio_mime": match.group(1),
                                "audio_base64": match.group(2),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                except Exception:
                    continue

        producer_task = asyncio.create_task(produce_stream())
        tts_task = asyncio.create_task(tts_worker())
        while True:
            item = await event_queue.get()
            if item is None:
                break
            yield item
        await producer_task
        await tts_task

        reply = None
        if not accumulated_text.strip():
            reply = await build_assistant_reply_from_prepared(db, session, payload.text_content, prepared=prepared)
            accumulated_text = reply.text

        assistant_metadata = {
            "chain_name": runtime.chain_name,
            "pipeline": "rag_chain->text_chain(stream)",
            "fallback_reason": llm_error,
            "voice_used": runtime.tts_voice,
            "retrieval_gate": {
                "decision": prepared.retrieval_decision,
                "gate_reason": prepared.retrieval_gate_reason,
                "reason": prepared.retrieval_reason,
                "timed_out": prepared.retrieval_timed_out,
            },
            "provider_trace": {
                "llm": {"provider": runtime.text_llm_provider, "model": runtime.text_llm_model},
                "llm_fallback": False,
                "rag": prepared.rag_trace,
                "rag_error": prepared.rag_reason,
                "stage_metrics": {
                    "context_latency_ms": prepared.context_latency_ms,
                    "retrieval_latency_ms": prepared.retrieval_latency_ms,
                },
            },
        }
        if reply:
            assistant_metadata["chain_name"] = reply.chain_name
            assistant_metadata["pipeline"] = reply.pipeline
            assistant_metadata["fallback_reason"] = reply.fallback_reason or llm_error
            assistant_metadata["voice_used"] = reply.voice_used or runtime.tts_voice
            assistant_metadata["provider_trace"] = dict(reply.provider_trace or {})
            assistant_metadata["provider_trace"].setdefault(
                "stage_metrics",
                {
                    "context_latency_ms": prepared.context_latency_ms,
                    "retrieval_latency_ms": prepared.retrieval_latency_ms,
                },
            )
        assistant_audio_url = None
        audio_meta: dict[str, Any] = {}
        tts_errors: list[str] = []
        tts_started = perf_counter()
        if accumulated_text.strip():
            audio_url, audio_meta, tts_errors = await _synthesize_assistant_audio(db, payload.session_id, accumulated_text)
            assistant_audio_url = audio_url
            assistant_metadata.update(audio_meta)
            if audio_meta.get("voice_used"):
                assistant_metadata["voice_used"] = audio_meta["voice_used"]
            if tts_errors:
                assistant_metadata["tts_error"] = " | ".join(tts_errors[:3])
        assistant_metadata["provider_trace"]["tts_fallback"] = bool(tts_errors) or (
            bool(audio_meta.get("tts_source")) and audio_meta.get("tts_source") != "main_omni_model"
        )
        llm_latency_ms = int((perf_counter() - llm_started) * 1000)
        tts_latency_ms = int((perf_counter() - tts_started) * 1000) if accumulated_text.strip() else 0
        assistant_metadata["provider_trace"]["stage_metrics"].update(
            {
                "llm_latency_ms": llm_latency_ms,
                "tts_latency_ms": tts_latency_ms,
                "total_latency_ms": int((perf_counter() - turn_started) * 1000),
            }
        )
        if first_audio_latency_ms is None and assistant_audio_url:
            first_audio_latency_ms = int((perf_counter() - turn_started) * 1000)

        db.add(
            MessageEntity(
                session_id=payload.session_id,
                role="assistant",
                content_type=reply.content_type if reply else "text",
                text_content=accumulated_text,
                image_url=reply.image_url if reply else None,
                audio_url=assistant_audio_url,
                metadata_json=assistant_metadata,
            )
        )

        if (session.title or "").strip() in {"", DEFAULT_SESSION_TITLE, "New Session"} and (payload.text_content or "").strip():
            session.title = DEFAULT_SESSION_TITLE
            await summarize_session_title(db, session, payload.text_content or "")

        await db.commit()
        await sync_memory_after_chat(db, payload.session_id)
        tts_failed = bool(accumulated_text.strip()) and not assistant_audio_url
        yield json.dumps(
            {
                "text": accumulated_text,
                "image_url": reply.image_url if reply else None,
                "audio_url": assistant_audio_url,
                "done": True,
                "error": "语音合成失败" if tts_failed else None,
                "metrics": build_turn_metrics_payload(
                    turn_id=str(payload.session_id),
                    context_latency_ms=prepared.context_latency_ms,
                    first_text_latency_ms=first_text_latency_ms,
                    first_audio_latency_ms=first_audio_latency_ms,
                    retrieval_latency_ms=prepared.retrieval_latency_ms,
                    llm_latency_ms=llm_latency_ms,
                    tts_latency_ms=tts_latency_ms,
                    total_latency_ms=int((perf_counter() - turn_started) * 1000),
                ),
            },
            ensure_ascii=False,
        ) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/api/messages")
async def create_message(payload: MessageCreate, db: AsyncSession = Depends(get_db)):
    session = await db.get(SessionEntity, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    user_msg = MessageEntity(
        session_id=payload.session_id,
        role="user",
        content_type=payload.content_type,
        text_content=payload.text_content,
        image_url=payload.image_url,
    )
    db.add(user_msg)
    await db.flush()

    reply = await build_assistant_reply(db, session, payload.text_content)
    assistant_metadata = {
        "chain_name": reply.chain_name,
        "pipeline": reply.pipeline,
        "fallback_reason": reply.fallback_reason,
        "voice_used": reply.voice_used,
        "provider_trace": reply.provider_trace,
    }
    assistant_audio_url = None
    if (reply.text or "").strip():
        audio_url, audio_meta, tts_errors = await _synthesize_assistant_audio(db, payload.session_id, reply.text)
        assistant_audio_url = audio_url
        assistant_metadata.update(audio_meta)
        if audio_meta.get("voice_used"):
            assistant_metadata["voice_used"] = audio_meta["voice_used"]
        if tts_errors:
            assistant_metadata["tts_error"] = " | ".join(tts_errors[:3])
    db.add(
        MessageEntity(
            session_id=payload.session_id,
            role="assistant",
            content_type=reply.content_type,
            text_content=reply.text,
            image_url=reply.image_url,
            audio_url=assistant_audio_url,
            metadata_json=assistant_metadata,
        )
    )

    if (session.title or "").strip() in {"", DEFAULT_SESSION_TITLE, "New Session"} and (payload.text_content or "").strip():
        session.title = DEFAULT_SESSION_TITLE
        await summarize_session_title(db, session, payload.text_content or "")

    await db.commit()

    snapshot = await sync_memory_after_chat(db, payload.session_id)
    return {
        "message": "Message sent.",
        "assistant_reply": reply.text,
        "assistant_image_url": reply.image_url,
        "assistant_audio_url": assistant_audio_url,
        "memory_snapshot": snapshot,
        "pipeline": reply.pipeline,
        "fallback_reason": reply.fallback_reason,
        "voice_used": reply.voice_used,
        "provider_trace": reply.provider_trace,
    }


@router.post("/api/messages/audio")
async def create_message_from_audio(
    session_id: str = Form(...), file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    try:
        sid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id.") from exc

    session = await db.get(SessionEntity, sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    runtime = await resolve_session_runtime(db, sid)
    transcribed, asr_trace = await run_single_asr_with_trace(
        db,
        audio_bytes=audio_bytes,
        filename=file.filename or "audio.wav",
        asr_provider=runtime.asr_provider,
        asr_model=runtime.asr_model,
    )
    message_payload = MessageCreate(session_id=sid, content_type="audio", text_content=transcribed)
    response = await create_message(message_payload, db)
    merged_trace = {"asr": asr_trace, "chat": response.get("provider_trace", {})}
    fallback_reason = str(asr_trace.get("fallback_reason") or "") if isinstance(asr_trace, dict) else ""
    asr_text_clean = transcribed.strip()
    asr_success = bool(asr_text_clean and asr_text_clean != "语音未识别，请用户重试")
    return {
        **response,
        "assistant_audio_url": response.get("assistant_audio_url"),
        "asr_text": transcribed,
        "asr_success": asr_success,
        "asr_error": None if asr_success else (fallback_reason or "语音未识别，请用户重试"),
        "provider_trace": merged_trace,
        "pipeline": response.get("pipeline") or "single_voice_chain->rag_chain->text_chain",
        "fallback_reason": response.get("fallback_reason") or fallback_reason or None,
    }


@router.post("/api/messages/audio/transcribe")
async def transcribe_audio_only(
    session_id: str = Form(...), file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    try:
        sid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id.") from exc

    session = await db.get(SessionEntity, sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    runtime = await resolve_session_runtime(db, sid)
    transcribed, asr_trace = await run_single_asr_with_trace(
        db,
        audio_bytes=audio_bytes,
        filename=file.filename or "audio.wav",
        asr_provider=runtime.asr_provider,
        asr_model=runtime.asr_model,
    )
    text_clean = transcribed.strip()
    asr_success = bool(text_clean and text_clean != "语音未识别，请用户重试")
    fallback_reason = str(asr_trace.get("fallback_reason") or "") if isinstance(asr_trace, dict) else ""
    return {
        "asr_text": transcribed,
        "asr_success": asr_success,
        "asr_error": None if asr_success else (fallback_reason or "语音未识别，请用户重试"),
        "provider_trace": {"asr": asr_trace},
    }


@router.patch("/api/messages/{message_id}")
async def edit_message(message_id: uuid.UUID, payload: MessageEdit, db: AsyncSession = Depends(get_db)):
    row = await db.get(MessageEntity, message_id)
    if not row:
        raise HTTPException(status_code=404, detail="Message not found.")
    row.text_content = payload.text_content
    row.replaced = False
    next_assistant = await db.scalar(
        select(MessageEntity)
        .where(
            MessageEntity.session_id == row.session_id,
            MessageEntity.role == "assistant",
            MessageEntity.created_at >= row.created_at,
        )
        .order_by(MessageEntity.created_at.asc())
    )
    if next_assistant:
        next_assistant.replaced = True
    await db.commit()

    session = await db.get(SessionEntity, row.session_id)
    reply = await build_assistant_reply(db, session, payload.text_content)
    db.add(
        MessageEntity(
            session_id=row.session_id,
            role="assistant",
            content_type=reply.content_type,
            text_content=reply.text,
            image_url=reply.image_url,
            audio_url=None,
            metadata_json={
                "chain_name": reply.chain_name,
                "pipeline": reply.pipeline,
                "fallback_reason": reply.fallback_reason,
                "voice_used": reply.voice_used,
                "provider_trace": reply.provider_trace,
            },
        )
    )
    await db.flush()
    assistant_row = await db.scalar(
        select(MessageEntity)
        .where(MessageEntity.session_id == row.session_id, MessageEntity.role == "assistant")
        .order_by(MessageEntity.created_at.desc())
    )
    if assistant_row and (reply.text or "").strip():
        audio_url, audio_meta, tts_errors = await _synthesize_assistant_audio(db, row.session_id, reply.text)
        assistant_row.audio_url = audio_url
        meta = dict(assistant_row.metadata_json or {})
        meta.update(audio_meta)
        if audio_meta.get("voice_used"):
            meta["voice_used"] = audio_meta["voice_used"]
        if tts_errors:
            meta["tts_error"] = " | ".join(tts_errors[:3])
        assistant_row.metadata_json = meta
    await db.commit()
    snapshot = await sync_memory_after_chat(db, row.session_id)
    return {
        "message": "Message edited and response regenerated.",
        "assistant_reply": reply.text,
        "assistant_image_url": reply.image_url,
        "memory_snapshot": snapshot,
        "pipeline": reply.pipeline,
        "fallback_reason": reply.fallback_reason,
        "voice_used": reply.voice_used,
        "provider_trace": reply.provider_trace,
    }


@router.delete("/api/messages/{message_id}")
async def delete_message(message_id: uuid.UUID, confirm: bool = Query(default=False), db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Dangerous operation requires confirm=true.")
    row = await db.get(MessageEntity, message_id)
    if not row:
        raise HTTPException(status_code=404, detail="Message not found.")
    session_id = row.session_id
    if row.role == "user":
        next_user = await db.scalar(
            select(MessageEntity)
            .where(
                MessageEntity.session_id == session_id,
                MessageEntity.role == "user",
                MessageEntity.created_at > row.created_at,
            )
            .order_by(MessageEntity.created_at.asc())
        )
        if next_user:
            await db.execute(
                delete(MessageEntity).where(
                    MessageEntity.session_id == session_id,
                    MessageEntity.created_at >= row.created_at,
                    MessageEntity.created_at < next_user.created_at,
                )
            )
        else:
            await db.execute(
                delete(MessageEntity).where(
                    MessageEntity.session_id == session_id,
                    MessageEntity.created_at >= row.created_at,
                )
            )
    else:
        await db.execute(delete(MessageEntity).where(MessageEntity.id == message_id))
    await db.commit()
    snapshot = await sync_memory_after_chat(db, session_id)
    return {"message": "Message deleted.", "memory_snapshot": snapshot}


@router.post("/api/messages/{message_id}/regenerate")
async def regenerate_message(message_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    source = await db.get(MessageEntity, message_id)
    if not source or source.role != "assistant":
        raise HTTPException(status_code=404, detail="Assistant message not found.")
    user_row = await db.scalar(
        select(MessageEntity)
        .where(MessageEntity.session_id == source.session_id, MessageEntity.role == "user")
        .order_by(MessageEntity.created_at.desc())
    )
    session = await db.get(SessionEntity, source.session_id)
    source.replaced = True
    reply = await build_assistant_reply(db, session, user_row.text_content if user_row else "")
    db.add(
        MessageEntity(
            session_id=source.session_id,
            role="assistant",
            content_type=reply.content_type,
            text_content=reply.text,
            image_url=reply.image_url,
            audio_url=None,
            metadata_json={
                "chain_name": reply.chain_name,
                "pipeline": reply.pipeline,
                "fallback_reason": reply.fallback_reason,
                "voice_used": reply.voice_used,
                "provider_trace": reply.provider_trace,
            },
        )
    )
    await db.flush()
    assistant_row = await db.scalar(
        select(MessageEntity)
        .where(MessageEntity.session_id == source.session_id, MessageEntity.role == "assistant")
        .order_by(MessageEntity.created_at.desc())
    )
    if assistant_row and (reply.text or "").strip():
        audio_url, audio_meta, tts_errors = await _synthesize_assistant_audio(db, source.session_id, reply.text)
        assistant_row.audio_url = audio_url
        meta = dict(assistant_row.metadata_json or {})
        meta.update(audio_meta)
        if audio_meta.get("voice_used"):
            meta["voice_used"] = audio_meta["voice_used"]
        if tts_errors:
            meta["tts_error"] = " | ".join(tts_errors[:3])
        assistant_row.metadata_json = meta
    await db.commit()
    snapshot = await sync_memory_after_chat(db, source.session_id)
    return {
        "message": "Response regenerated.",
        "assistant_reply": reply.text,
        "assistant_image_url": reply.image_url,
        "memory_snapshot": snapshot,
        "pipeline": reply.pipeline,
        "fallback_reason": reply.fallback_reason,
        "voice_used": reply.voice_used,
        "provider_trace": reply.provider_trace,
    }
