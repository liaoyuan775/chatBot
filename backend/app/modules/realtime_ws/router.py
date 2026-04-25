from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime
from time import monotonic
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.models import MessageEntity, SessionEntity
from app.modules.chat.engine import prepare_realtime_chain, resolve_session_runtime, run_single_asr_with_trace
from app.modules.chat.service import build_retrieval_metrics_payload, build_turn_metrics_payload, prepare_assistant_turn
from app.modules.context_memory.service import recompute_session_memory
from app.modules.realtime_ws.omni_bridge import run_dashscope_omni_bridge

router = APIRouter(tags=["realtime"])

PARTIAL_PLACEHOLDER_TEXTS = {"语音未识别，请用户重试"}


def _ext_from_audio_mime(audio_mime: str) -> str:
    mime = (audio_mime or "").lower()
    if "wav" in mime:
        return "wav"
    if "mp3" in mime or "mpeg" in mime:
        return "mp3"
    if "ogg" in mime:
        return "ogg"
    if "aac" in mime:
        return "aac"
    if "m4a" in mime or "mp4" in mime:
        return "m4a"
    return "webm"


def _is_usable_partial_text(text: str) -> bool:
    normalized = (text or "").strip()
    return bool(normalized and normalized not in PARTIAL_PLACEHOLDER_TEXTS)


def _should_use_native_omni(runtime) -> bool:
    provider = str(getattr(runtime, "realtime_main_provider", "") or "").strip().lower()
    model = str(getattr(runtime, "realtime_main_model", "") or "").strip().lower()
    omni_mode = str(getattr(runtime, "omni_mode", "") or "").strip().lower()
    if provider != "dashscope":
        return False
    if "omni" not in model and "realtime" not in model:
        return False
    return omni_mode not in {"legacy", "force_legacy"}


async def _persist_realtime_turn(
    session_id: uuid.UUID,
    text_input: str,
    prepared,
    audio_url: str | None,
    audio_mime: str,
) -> None:
    async with SessionLocal() as db:
        user_row = MessageEntity(session_id=session_id, role="user", content_type="audio", text_content=text_input)
        db.add(user_row)
        await db.flush()
        db.add(
            MessageEntity(
                session_id=session_id,
                role="assistant",
                content_type="audio",
                text_content=prepared.text,
                audio_url=audio_url,
                metadata_json={
                    "chain_name": prepared.chain_name,
                    "used_fallback": prepared.used_fallback,
                    "pipeline": "realtime_voice_chain",
                    "fallback_reason": prepared.fallback_reason,
                    "voice_used": prepared.voice_used,
                    "audio_mime": audio_mime,
                    "provider_trace": prepared.provider_trace,
                },
            )
        )
        await db.commit()
        await recompute_session_memory(db, session_id)


@router.websocket("/ws/realtime-chat")
async def realtime_chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    params = websocket.query_params
    session_id_text = params.get("session_id")
    if not session_id_text:
        await websocket.send_json({"event": "session.error", "message": "session_id is required"})
        await websocket.close()
        return
    try:
        session_id = uuid.UUID(session_id_text)
    except ValueError:
        await websocket.send_json({"event": "session.error", "message": "invalid session_id"})
        await websocket.close()
        return

    try:
        async with SessionLocal() as db:
            runtime = await resolve_session_runtime(db, session_id)
        if _should_use_native_omni(runtime):
            await run_dashscope_omni_bridge(websocket, session_id=session_id, runtime=runtime)
            return
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"event": "session.error", "message": f"native omni setup failed: {exc}"})
        await websocket.send_json({"event": "session.state.changed", "state": "error", "reason": "native-omni-setup-failed"})
        await websocket.close()
        return

    audio_chunks: list[bytes] = []
    last_partial_text = ""
    last_partial_trace: dict[str, Any] = {}
    last_partial_at = 0.0
    partial_interval = 0.6
    partial_window_chunks = 6
    partial_min_bytes = 6_000
    last_audio_mime = "audio/webm"
    partial_asr_task: asyncio.Task | None = None

    current_turn_task: asyncio.Task | None = None
    current_turn_id = ""
    turn_started_at = 0.0
    last_committed_text = ""
    last_committed_at = 0.0
    duplicate_input_window = 2.5

    await websocket.send_json({"event": "session.ready", "session_id": str(session_id), "mode": "integrated-realtime"})
    await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "connected"})

    async def run_partial_asr(candidate_audio: bytes, audio_mime: str):
        nonlocal last_partial_text, last_partial_trace, last_partial_at, partial_asr_task
        try:
            async with SessionLocal() as db:
                runtime = await resolve_session_runtime(db, session_id)
                partial_text, partial_trace = await run_single_asr_with_trace(
                    db,
                    candidate_audio,
                    f"realtime_partial.{_ext_from_audio_mime(audio_mime)}",
                    asr_provider=runtime.asr_provider,
                    asr_model=runtime.asr_model,
                )
            normalized = (partial_text or "").strip()
            if _is_usable_partial_text(normalized) and normalized != last_partial_text:
                last_partial_text = normalized
                last_partial_trace = partial_trace
                await websocket.send_json(
                    {
                        "event": "user.transcript.partial",
                        "text": normalized,
                        "provider_trace": {**partial_trace, "text_source": "partial_asr"},
                    }
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            last_partial_at = monotonic()
            partial_asr_task = None

    async def run_turn(turn_id: str, text_input: str, text_source: str, asr_trace: dict[str, Any]):
        nonlocal current_turn_task
        first_text_latency_ms: int | None = None
        first_audio_latency_ms: int | None = None
        llm_latency_ms: int | None = None
        tts_latency_ms: int | None = None
        await websocket.send_json({"event": "user.transcript.final", "turn_id": turn_id, "text": text_input})
        await websocket.send_json({"event": "session.state.changed", "state": "thinking", "reason": "turn-start"})
        try:
            try:
                async with SessionLocal() as db:
                    session = await db.get(SessionEntity, session_id)
                    if not session:
                        await websocket.send_json({"event": "session.error", "message": "session not found"})
                        await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "session-not-found"})
                        return
                    prepared_turn = await prepare_assistant_turn(db, session, text_input)
                    await websocket.send_json(
                        {
                            "event": "metrics.retrieval",
                            **build_retrieval_metrics_payload(prepared_turn, turn_id=turn_id),
                        }
                    )
                    llm_started = monotonic()
                    prepared = await prepare_realtime_chain(
                        db,
                        session_id=session_id,
                        text_input=text_input,
                        context_text=prepared_turn.context_hint,
                        knowledge_text=prepared_turn.knowledge_text,
                    )
                    llm_latency_ms = int((monotonic() - llm_started) * 1000)
                    prepared.provider_trace["retrieval_gate"] = {
                        "decision": prepared_turn.retrieval_decision,
                        "gate_reason": prepared_turn.retrieval_gate_reason,
                        "reason": prepared_turn.retrieval_reason,
                        "timed_out": prepared_turn.retrieval_timed_out,
                        "hit_count": prepared_turn.retrieval_hit_count,
                    }
                    prepared.provider_trace["llm_fallback"] = bool(prepared.used_fallback)
                    if prepared_turn.rag_trace:
                        prepared.provider_trace["rag"] = prepared_turn.rag_trace
                    if prepared_turn.rag_reason:
                        prepared.provider_trace["rag_error"] = prepared_turn.rag_reason
                    prepared.provider_trace["stage_metrics"] = {
                        "context_latency_ms": prepared_turn.context_latency_ms,
                        "retrieval_latency_ms": prepared_turn.retrieval_latency_ms,
                        "llm_latency_ms": llm_latency_ms,
                    }
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json({"event": "session.error", "message": str(exc)})
                await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "prepare-failed"})
                return

            first_text_latency_ms = int((monotonic() - turn_started_at) * 1000)
            await websocket.send_json(
                {
                    "event": "assistant.text.delta",
                    "turn_id": turn_id,
                    "text": prepared.text,
                    "provider_trace": {**prepared.provider_trace, "text_source": text_source, "asr": asr_trace},
                }
            )
            await websocket.send_json(
                {
                    "event": "assistant.text.final",
                    "turn_id": turn_id,
                    "text": prepared.text,
                    "provider_trace": {**prepared.provider_trace, "text_source": text_source, "asr": asr_trace},
                }
            )

            audio_base64 = ""
            audio_mime = "audio/mpeg"
            audio_url: str | None = None
            tts_error: str | None = None
            try:
                tts_started = monotonic()
                audio_base64, audio_mime = await prepared.synthesize_audio()
                tts_latency_ms = int((monotonic() - tts_started) * 1000)
                prepared.provider_trace["tts"] = {
                    "provider": prepared.tts_provider,
                    "model": prepared.tts_model,
                    "source": prepared.tts_source,
                }
                prepared.provider_trace["tts_fallback"] = prepared.tts_source != "main_omni_model"
                if audio_base64:
                    if audio_mime == "audio/mpeg" and audio_base64.startswith("UklGR"):
                        audio_mime = "audio/wav"
                    audio_url = f"data:{audio_mime};base64,{audio_base64}"
            except Exception as exc:  # noqa: BLE001
                tts_error = str(exc)
                tts_latency_ms = tts_latency_ms or 0
                prepared.provider_trace["tts_error"] = tts_error
                prepared.provider_trace["tts_fallback"] = True
                await websocket.send_json({"event": "session.error", "message": tts_error, "code": "tts_error"})
            prepared.provider_trace.setdefault("stage_metrics", {})
            prepared.provider_trace["stage_metrics"].update(
                {
                    "tts_latency_ms": tts_latency_ms,
                    "total_latency_ms": int((monotonic() - turn_started_at) * 1000),
                }
            )

            if audio_base64:
                first_audio_latency_ms = int((monotonic() - turn_started_at) * 1000)
                await websocket.send_json({"event": "assistant.audio.started", "turn_id": turn_id, "audio_mime": audio_mime})
                await websocket.send_json({"event": "assistant.audio.delta", "turn_id": turn_id, "audio_base64": audio_base64, "audio_mime": audio_mime})
                await websocket.send_json({"event": "assistant.audio.stopped", "turn_id": turn_id})

            assistant_message = {
                "id": f"rt-assistant-{datetime.utcnow().timestamp()}",
                "session_id": str(session_id),
                "role": "assistant",
                "content_type": "audio",
                "text_content": prepared.text,
                "audio_url": audio_url,
                "metadata_json": {
                    "chain_name": prepared.chain_name,
                    "used_fallback": prepared.used_fallback,
                    "pipeline": "realtime_voice_chain",
                    "fallback_reason": prepared.fallback_reason,
                    "voice_used": prepared.voice_used,
                    "provider_trace": prepared.provider_trace,
                    "tts_error": tts_error,
                },
                "replaced": False,
                "created_at": datetime.utcnow().isoformat(),
            }
            await websocket.send_json({"event": "session.updated", "session_id": str(session_id), "message": assistant_message})

            try:
                await _persist_realtime_turn(session_id, text_input, prepared, audio_url, audio_mime)
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json({"event": "session.error", "message": f"persist failed: {exc}", "code": "persist_error"})

            await websocket.send_json(
                {
                    "event": "metrics.turn",
                    **build_turn_metrics_payload(
                        turn_id=turn_id,
                        context_latency_ms=prepared_turn.context_latency_ms,
                        first_text_latency_ms=first_text_latency_ms,
                        first_audio_latency_ms=first_audio_latency_ms,
                        retrieval_latency_ms=prepared_turn.retrieval_latency_ms,
                        llm_latency_ms=llm_latency_ms,
                        tts_latency_ms=tts_latency_ms,
                        total_latency_ms=int((monotonic() - turn_started_at) * 1000),
                    ),
                }
            )
            await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "turn-done"})
        except asyncio.CancelledError:
            try:
                await websocket.send_json({"event": "assistant.interrupted", "turn_id": turn_id, "reason": "cancelled"})
                await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "cancelled"})
            except RuntimeError:
                # Socket may already be closed during cancellation teardown.
                pass
            raise
        finally:
            if current_turn_task and current_turn_task.done():
                current_turn_task = None

    try:
        while True:
            payload = await websocket.receive_text()
            data = json.loads(payload)
            event = data.get("event")

            if event == "audio_chunk":
                raw = data.get("audio_base64", "")
                incoming_mime = data.get("audio_mime")
                if isinstance(incoming_mime, str) and incoming_mime.strip():
                    last_audio_mime = incoming_mime.strip()
                if raw:
                    audio_chunks.append(base64.b64decode(raw))
                    if len(audio_chunks) >= 2 and (monotonic() - last_partial_at) >= partial_interval:
                        candidate = b"".join(audio_chunks[-partial_window_chunks:])
                        if (
                            len(candidate) >= partial_min_bytes
                            and (partial_asr_task is None or partial_asr_task.done())
                        ):
                            last_partial_at = monotonic()
                            partial_asr_task = asyncio.create_task(run_partial_asr(candidate, last_audio_mime))
                continue

            if event in {"input_audio.commit", "vad_end"}:
                if current_turn_task and not current_turn_task.done():
                    continue
                if partial_asr_task and not partial_asr_task.done():
                    partial_asr_task.cancel()
                    partial_asr_task = None

                text_input = (data.get("text") or "").strip()
                asr_trace: dict[str, Any] = {}
                text_source = "client_text"
                if not text_input and _is_usable_partial_text(last_partial_text):
                    text_input = last_partial_text
                    asr_trace = {**last_partial_trace, "text_source": "partial_reused"}
                    text_source = "partial_reused"
                elif not text_input and audio_chunks:
                    async with SessionLocal() as db:
                        runtime = await resolve_session_runtime(db, session_id)
                        text_input, asr_trace = await run_single_asr_with_trace(
                            db,
                            b"".join(audio_chunks),
                            f"realtime.{_ext_from_audio_mime(last_audio_mime)}",
                            asr_provider=runtime.asr_provider,
                            asr_model=runtime.asr_model,
                        )
                    text_input = (text_input or "").strip()
                    asr_trace = {**asr_trace, "text_source": "final_asr"}
                    text_source = "final_asr"

                audio_chunks.clear()
                last_partial_text = ""
                last_partial_trace = {}

                text_input = (text_input or "").strip()
                if not text_input:
                    await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "no-speech"})
                    continue

                if text_source != "client_text" and not _is_usable_partial_text(text_input):
                    await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "asr-empty"})
                    continue

                now = monotonic()
                if (
                    text_source != "client_text"
                    and text_input == last_committed_text
                    and (now - last_committed_at) <= duplicate_input_window
                ):
                    await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "duplicate-input"})
                    continue
                last_committed_text = text_input
                last_committed_at = now

                current_turn_id = f"turn-{uuid.uuid4().hex[:10]}"
                turn_started_at = monotonic()
                current_turn_task = asyncio.create_task(run_turn(current_turn_id, text_input, text_source, asr_trace))
                continue

            if event == "response.cancel":
                if current_turn_task and not current_turn_task.done():
                    current_turn_task.cancel()
                    await websocket.send_json({"event": "assistant.interrupted", "turn_id": current_turn_id, "reason": "response.cancel"})
                    await websocket.send_json({"event": "session.state.changed", "state": "listening", "reason": "response.cancel"})
                else:
                    await websocket.send_json({"event": "assistant.interrupted", "reason": "response.cancel_noop"})
                continue

            if event in {"session.end", "end"}:
                if current_turn_task and not current_turn_task.done():
                    current_turn_task.cancel()
                if partial_asr_task and not partial_asr_task.done():
                    partial_asr_task.cancel()
                await websocket.send_json({"event": "session.state.changed", "state": "idle", "reason": "session-end"})
                await websocket.close()
                break

            await websocket.send_json({"event": "session.error", "message": f"unsupported event: {event}", "code": "unsupported_event"})
    except WebSocketDisconnect:
        if current_turn_task and not current_turn_task.done():
            current_turn_task.cancel()
        if partial_asr_task and not partial_asr_task.done():
            partial_asr_task.cancel()
        return

