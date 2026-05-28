from __future__ import annotations

import asyncio
import base64
import json
import uuid
import wave
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from time import monotonic
from typing import Any

import aiohttp
from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.provider_gateway import ProviderError, get_provider_context
from app.core.database import SessionLocal
from app.models import MessageEntity, SessionEntity
from app.modules.chat.engine import SessionRuntimeConfig, resolve_session_runtime
from app.modules.chat.langchain_pipeline import is_knowledge_globally_enabled, run_history_context_lcel, run_rag_chain_lcel
from app.modules.chat.service import _resolve_retrieval_outcome, should_retrieve_knowledge
from app.modules.context_memory.service import recompute_session_memory

DEFAULT_REALTIME_VOICE = "Tina"
DEFAULT_OUTPUT_SAMPLE_RATE = 24000


def _normalize_realtime_voice(voice_name: str | None) -> str:
    voice = (voice_name or "").strip()
    if not voice or "/" in voice or ":" in voice:
        return DEFAULT_REALTIME_VOICE
    return voice


def _build_realtime_ws_url(base_url: str, model_name: str) -> str:
    clean = (base_url or "").rstrip("/")
    if clean.startswith("https://"):
        clean = "wss://" + clean[len("https://") :]
    elif clean.startswith("http://"):
        clean = "ws://" + clean[len("http://") :]
    return f"{clean}/api-ws/v1/realtime?model={model_name}"


def _pcm16_to_wav_base64(audio_bytes: bytes, *, sample_rate: int = DEFAULT_OUTPUT_SAMPLE_RATE) -> str:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_bytes)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@dataclass
class OmniTurnState:
    turn_id: str = ""
    user_text: str = ""
    assistant_text: str = ""
    assistant_audio_pcm: bytearray = field(default_factory=bytearray)
    assistant_audio_started: bool = False
    assistant_interrupted: bool = False
    user_speaking: bool = False
    response_active: bool = False
    response_id: str | None = None
    input_committed: bool = False
    response_requested: bool = False
    turn_started_at: float = 0.0
    first_text_at: float | None = None
    first_audio_at: float | None = None
    rag_text: str = ""
    rag_trace: dict[str, Any] = field(default_factory=dict)
    rag_error: str | None = None
    retrieval_decision: str = "skip"
    retrieval_gate_reason: str = "not_evaluated"
    retrieval_reason: str = "not_evaluated"
    retrieval_hit_count: int = 0
    retrieval_timed_out: bool = False
    context_hint: str = ""

    def reset(self) -> None:
        self.turn_id = ""
        self.user_text = ""
        self.assistant_text = ""
        self.assistant_audio_pcm.clear()
        self.assistant_audio_started = False
        self.assistant_interrupted = False
        self.user_speaking = False
        self.response_active = False
        self.response_id = None
        self.input_committed = False
        self.response_requested = False
        self.turn_started_at = 0.0
        self.first_text_at = None
        self.first_audio_at = None
        self.rag_text = ""
        self.rag_trace = {}
        self.rag_error = None
        self.retrieval_decision = "skip"
        self.retrieval_gate_reason = "not_evaluated"
        self.retrieval_reason = "not_evaluated"
        self.retrieval_hit_count = 0
        self.retrieval_timed_out = False
        self.context_hint = ""


async def _persist_omni_turn(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    user_text: str,
    assistant_text: str,
    audio_url: str | None,
    audio_mime: str | None,
    model_name: str,
    voice_name: str,
    provider_trace: dict[str, Any],
) -> MessageEntity:
    db.add(MessageEntity(session_id=session_id, role="user", content_type="audio", text_content=user_text))
    await db.flush()
    assistant_row = MessageEntity(
        session_id=session_id,
        role="assistant",
        content_type="audio",
        text_content=assistant_text,
        audio_url=audio_url,
        metadata_json={
            "pipeline": "omni_realtime_native",
            "main_model": model_name,
            "voice_used": voice_name,
            "audio_mime": audio_mime,
            "provider_trace": provider_trace,
        },
    )
    db.add(assistant_row)
    await db.commit()
    await db.refresh(assistant_row)
    await recompute_session_memory(db, session_id)
    return assistant_row


async def run_dashscope_omni_bridge(
    websocket: WebSocket,
    *,
    session_id: uuid.UUID,
    runtime: SessionRuntimeConfig,
) -> None:
    async with SessionLocal() as db:
        ctx = await get_provider_context(db, runtime.realtime_main_provider)

    upstream_url = _build_realtime_ws_url(ctx.base_url, runtime.realtime_main_model)
    turn = OmniTurnState()
    voice_name = _normalize_realtime_voice(runtime.tts_voice)
    session_ready_sent = False
    session_update_sent = False
    closed = False
    auto_reply = True

    async def emit(event_name: str, payload: dict[str, Any]) -> None:
        if closed:
            return
        await websocket.send_json({"event": event_name, **payload})

    async def persist_current_turn() -> None:
        if not turn.user_text.strip() or not (turn.assistant_text.strip() or turn.assistant_audio_pcm):
            return
        audio_url: str | None = None
        audio_mime: str | None = None
        if turn.assistant_audio_pcm:
            audio_mime = "audio/wav"
            audio_url = f"data:{audio_mime};base64,{_pcm16_to_wav_base64(bytes(turn.assistant_audio_pcm))}"
        provider_trace = {
            "mode": "dashscope-native-realtime",
            "provider": runtime.realtime_main_provider,
            "model": runtime.realtime_main_model,
            "voice": voice_name,
        }
        if turn.rag_trace:
            provider_trace["rag"] = turn.rag_trace
        if turn.rag_error:
            provider_trace["rag_error"] = turn.rag_error
        provider_trace["retrieval_gate"] = {
            "decision": turn.retrieval_decision,
            "gate_reason": turn.retrieval_gate_reason,
            "reason": turn.retrieval_reason,
            "timed_out": turn.retrieval_timed_out,
            "hit_count": turn.retrieval_hit_count,
        }
        try:
            async with SessionLocal() as db:
                assistant_row = await _persist_omni_turn(
                    db,
                    session_id=session_id,
                    user_text=turn.user_text.strip(),
                    assistant_text=turn.assistant_text.strip(),
                    audio_url=audio_url,
                    audio_mime=audio_mime,
                    model_name=runtime.realtime_main_model,
                    voice_name=voice_name,
                    provider_trace=provider_trace,
                )
        except Exception:
            return
        await emit(
            "session.updated",
            {
                "session_id": str(session_id),
                "message": {
                    "id": str(assistant_row.id),
                    "session_id": str(session_id),
                    "role": "assistant",
                    "content_type": "audio",
                    "text_content": assistant_row.text_content,
                    "audio_url": assistant_row.audio_url,
                    "metadata_json": assistant_row.metadata_json or {},
                    "replaced": False,
                    "created_at": assistant_row.created_at.isoformat() if assistant_row.created_at else datetime.utcnow().isoformat(),
                },
            },
        )

    async with aiohttp.ClientSession(
        headers={"Authorization": f"Bearer {ctx.api_key}"},
        trust_env=False,
    ) as http_session:
        async with http_session.ws_connect(upstream_url, heartbeat=20, autoping=True, max_msg_size=0) as upstream:
            async def send_session_update() -> None:
                nonlocal ctx, runtime, session_update_sent, voice_name
                if session_update_sent:
                    return
                async with SessionLocal() as db:
                    runtime = await resolve_session_runtime(db, session_id)
                    ctx = await get_provider_context(db, runtime.realtime_main_provider)
                voice_name = _normalize_realtime_voice(runtime.tts_voice)
                await upstream.send_str(
                    json.dumps(
                        {
                            "event_id": f"session-{uuid.uuid4().hex[:10]}",
                            "type": "session.update",
                            "session": {
                                "modalities": ["text", "audio"],
                                "voice": voice_name,
                                "input_audio_format": "pcm",
                                "output_audio_format": "pcm",
                                "instructions": runtime.persona_realtime_prompt,
                                "input_audio_transcription": {"model": "qwen3-asr-flash-realtime"},
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.5,
                                    "prefix_padding_ms": 300,
                                    "silence_duration_ms": 800,
                                    "create_response": False,
                                    "interrupt_response": True,
                                },
                            },
                        }
                    )
                )
                session_update_sent = True

            async def commit_input_buffer() -> None:
                if turn.input_committed:
                    return
                turn.input_committed = True
                await upstream.send_str(
                    json.dumps({"event_id": f"commit-{uuid.uuid4().hex[:10]}", "type": "input_audio_buffer.commit"})
                )

            async def fetch_conversation_context() -> None:
                if turn.context_hint:
                    return
                async with SessionLocal() as db:
                    history = (
                        await db.scalars(
                            select(MessageEntity)
                            .where(MessageEntity.session_id == session_id, MessageEntity.role.in_(["user", "assistant"]))
                            .order_by(MessageEntity.created_at.desc())
                            .limit(8)
                        )
                    ).all()
                history_lines: list[str] = []
                for item in reversed(history):
                    text = (item.text_content or "").strip()
                    if not text:
                        continue
                    role_label = "用户" if item.role == "user" else "助手"
                    history_lines.append(f"{role_label}: {text}")
                if not history_lines:
                    turn.context_hint = "No context"
                    return
                try:
                    async with SessionLocal() as db:
                        ctx = await asyncio.wait_for(
                            run_history_context_lcel(
                                db=db,
                                provider_name=runtime.text_llm_provider,
                                model_name=runtime.text_llm_model,
                                history_texts=history_lines,
                            ),
                            timeout=5.0,
                        )
                        turn.context_hint = ctx
                except Exception:
                    turn.context_hint = "\n".join(f"- {line}" for line in history_lines[-6:])

            async def request_response() -> None:
                if not auto_reply or turn.response_requested:
                    return
                turn.response_requested = True
                extra_parts = [runtime.persona_realtime_prompt]
                if turn.context_hint and turn.context_hint != "No context":
                    extra_parts.append(f"Conversation history:\n{turn.context_hint}")
                if turn.rag_text.strip():
                    extra_parts.append(
                        f"Knowledge:\n{turn.rag_text[:1800]}\n\n"
                        "Use the provided knowledge when it is relevant to the user's latest utterance. "
                        "If the knowledge is irrelevant, ignore it."
                    )
                extra_instructions = "\n\n".join(extra_parts)
                await upstream.send_str(
                    json.dumps(
                        {
                            "event_id": f"response-{uuid.uuid4().hex[:10]}",
                            "type": "response.create",
                            "response": {
                                "modalities": ["text", "audio"],
                                "voice": voice_name,
                                "output_audio_format": "pcm",
                                "instructions": extra_instructions,
                            },
                        }
                    )
                )

            async def retrieve_knowledge_if_needed(user_text: str) -> None:
                turn.rag_text = ""
                turn.rag_trace = {}
                turn.rag_error = None
                turn.retrieval_decision = "skip"
                turn.retrieval_gate_reason = "not_evaluated"
                turn.retrieval_reason = "not_evaluated"
                turn.retrieval_hit_count = 0
                turn.retrieval_timed_out = False
                query = (user_text or "").strip()
                if not query:
                    return
                async with SessionLocal() as db:
                    session = await db.get(SessionEntity, session_id)
                    if not session or not session.knowledge_enabled:
                        turn.retrieval_decision = "skip"
                        turn.retrieval_gate_reason = "session_knowledge_disabled"
                        turn.retrieval_reason = "session_knowledge_disabled"
                        await emit(
                            "metrics.retrieval",
                            {
                                "turn_id": turn.turn_id or None,
                                "latency_ms": 0,
                                "hit_count": 0,
                                "decision": "skip",
                                "reason": "session_knowledge_disabled",
                                "timed_out": False,
                            },
                        )
                        return
                    if not await is_knowledge_globally_enabled(db):
                        turn.retrieval_decision = "skip"
                        turn.retrieval_gate_reason = "knowledge_global_disabled"
                        turn.retrieval_reason = "knowledge_global_disabled"
                        await emit(
                            "metrics.retrieval",
                            {
                                "turn_id": turn.turn_id or None,
                                "latency_ms": 0,
                                "hit_count": 0,
                                "decision": "skip",
                                "reason": "knowledge_global_disabled",
                                "timed_out": False,
                            },
                        )
                        return
                    decision = should_retrieve_knowledge(query)
                    turn.retrieval_decision = decision.decision
                    turn.retrieval_gate_reason = decision.reason
                    if decision.decision != "retrieve":
                        turn.retrieval_reason = decision.reason
                        turn.rag_trace = {"decision": decision.decision, "reason": decision.reason, "timed_out": False, "hit_count": 0}
                        await emit(
                            "metrics.retrieval",
                            {
                                "turn_id": turn.turn_id or None,
                                "latency_ms": 0,
                                "hit_count": 0,
                                "decision": decision.decision,
                                "reason": decision.reason,
                                "timed_out": False,
                            },
                        )
                        return
                    started = monotonic()
                    rag = await run_rag_chain_lcel(
                        db=db,
                        question=query,
                        chain_mapping=getattr(runtime, "chain_mapping", None),
                    )
                    turn.rag_text = (rag.text or "").strip()
                    turn.rag_trace = dict(rag.provider_trace or {})
                    turn.rag_error = rag.fallback_reason
                    latency_ms = int((monotonic() - started) * 1000)
                    retrieval_reason, hit_count = _resolve_retrieval_outcome(
                        decision=decision.decision,
                        gate_reason=decision.reason,
                        knowledge_text=turn.rag_text,
                        rag_reason=rag.fallback_reason,
                        timed_out=rag.timed_out,
                    )
                    turn.retrieval_reason = retrieval_reason
                    turn.retrieval_hit_count = hit_count
                    turn.retrieval_timed_out = rag.timed_out
                    await emit(
                        "metrics.retrieval",
                        {
                            "turn_id": turn.turn_id or None,
                            "latency_ms": latency_ms,
                            "hit_count": hit_count,
                            "decision": decision.decision,
                            "reason": retrieval_reason,
                            "timed_out": rag.timed_out,
                        },
                    )

            async def cancel_response(reason: str) -> None:
                if not turn.response_active:
                    return
                await upstream.send_str(
                    json.dumps({"event_id": f"cancel-{uuid.uuid4().hex[:10]}", "type": "response.cancel"})
                )
                await upstream.send_str(
                    json.dumps({"event_id": f"clear-{uuid.uuid4().hex[:10]}", "type": "input_audio_buffer.clear"})
                )
                turn.response_active = False
                turn.response_id = None
                turn.input_committed = False
                turn.response_requested = False
                turn.assistant_interrupted = True
                if turn.assistant_audio_started:
                    await emit("assistant.audio.stopped", {"turn_id": turn.turn_id})
                    turn.assistant_audio_started = False
                await emit("assistant.interrupted", {"turn_id": turn.turn_id or None, "reason": reason})
                await emit("session.state.changed", {"state": "listening", "reason": reason})

            async def handle_upstream() -> None:
                nonlocal runtime, session_ready_sent, closed
                async for message in upstream:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(message.data)
                    elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING}:
                        break
                    elif message.type == aiohttp.WSMsgType.ERROR:
                        raise RuntimeError(str(upstream.exception() or "upstream websocket error"))
                    else:
                        continue
                    event_type = str(payload.get("type") or "")
                    if event_type == "error":
                        error = payload.get("error") or {}
                        message_text = str(error.get("message") or "upstream realtime error")
                        await emit("session.error", {"message": message_text, "code": str(error.get("code") or "") or None})
                        continue

                    if event_type == "session.created" and not session_update_sent:
                        await send_session_update()
                        continue

                    if event_type == "session.updated" and not session_ready_sent:
                        session_ready_sent = True
                        await emit("session.ready", {"session_id": str(session_id), "mode": "integrated-realtime"})
                        await emit("session.state.changed", {"state": "listening", "reason": "connected"})
                        continue

                    if event_type == "input_audio_buffer.speech_started":
                        turn.user_speaking = True
                        if turn.response_active:
                            await cancel_response("barge-in")
                        if turn.turn_id and (
                            turn.user_text.strip()
                            or turn.assistant_text.strip()
                            or bool(turn.assistant_audio_pcm)
                            or turn.input_committed
                        ):
                            turn.reset()
                        if not turn.turn_id:
                            turn.turn_id = f"turn-{uuid.uuid4().hex[:10]}"
                            turn.turn_started_at = monotonic()
                            turn.input_committed = False
                            turn.response_requested = False
                        continue

                    if event_type == "input_audio_buffer.speech_stopped":
                        turn.user_speaking = False
                        await emit("session.state.changed", {"state": "thinking", "reason": "speech-stopped"})
                        await commit_input_buffer()
                        continue

                    if event_type == "conversation.item.input_audio_transcription.text":
                        transcript = str(payload.get("text") or "")
                        if transcript:
                            await emit("user.transcript.partial", {"text": transcript, "turn_id": turn.turn_id or None})
                        continue

                    if event_type == "conversation.item.input_audio_transcription.completed":
                        transcript = str(payload.get("transcript") or payload.get("text") or "")
                        if transcript:
                            if not turn.turn_id:
                                turn.turn_id = f"turn-{uuid.uuid4().hex[:10]}"
                                turn.turn_started_at = monotonic()
                            turn.user_text = transcript
                            await emit("user.transcript.final", {"text": transcript, "turn_id": turn.turn_id})
                            await emit(
                                "session.state.changed",
                                {"state": "thinking" if auto_reply else "listening", "reason": "user-final"},
                            )
                            if auto_reply:
                                try:
                                    await asyncio.gather(
                                        retrieve_knowledge_if_needed(transcript),
                                        fetch_conversation_context(),
                                    )
                                except Exception as exc:
                                    turn.rag_text = ""
                                    turn.rag_trace = {}
                                    turn.rag_error = str(exc)
                                await request_response()
                            if not auto_reply:
                                turn.reset()
                        continue

                    if event_type == "response.created":
                        turn.response_active = True
                        turn.response_id = str(payload.get("response", {}).get("id") or payload.get("response_id") or "")
                        await emit("session.state.changed", {"state": "thinking", "reason": "response-created"})
                        continue

                    if event_type == "response.audio_transcript.delta":
                        delta = str(payload.get("delta") or "")
                        if delta:
                            if turn.first_text_at is None:
                                turn.first_text_at = monotonic()
                            turn.assistant_text += delta
                            await emit("assistant.text.delta", {"text": turn.assistant_text, "turn_id": turn.turn_id or None})
                        continue

                    if event_type == "response.audio_transcript.done":
                        transcript = str(payload.get("transcript") or turn.assistant_text)
                        if transcript:
                            if turn.first_text_at is None:
                                turn.first_text_at = monotonic()
                            turn.assistant_text = transcript
                            await emit("assistant.text.final", {"text": transcript, "turn_id": turn.turn_id or None})
                        continue

                    if event_type == "response.audio.delta":
                        delta = str(payload.get("delta") or "")
                        if not delta:
                            continue
                        if turn.first_audio_at is None:
                            turn.first_audio_at = monotonic()
                        if not turn.assistant_audio_started:
                            turn.assistant_audio_started = True
                            await emit("assistant.audio.started", {"turn_id": turn.turn_id or None, "audio_mime": "audio/pcm;rate=24000"})
                        try:
                            pcm_bytes = base64.b64decode(delta)
                        except Exception:
                            pcm_bytes = b""
                        if pcm_bytes:
                            turn.assistant_audio_pcm.extend(pcm_bytes)
                        await emit(
                            "assistant.audio.delta",
                            {"turn_id": turn.turn_id or None, "audio_base64": delta, "audio_mime": "audio/pcm;rate=24000"},
                        )
                        await emit("session.state.changed", {"state": "speaking", "reason": "audio-delta"})
                        continue

                    if event_type == "response.audio.done":
                        if turn.assistant_audio_started:
                            turn.assistant_audio_started = False
                            await emit("assistant.audio.stopped", {"turn_id": turn.turn_id or None})
                        continue

                    if event_type == "response.done":
                        turn.response_active = False
                        if turn.assistant_audio_started:
                            turn.assistant_audio_started = False
                            await emit("assistant.audio.stopped", {"turn_id": turn.turn_id or None})
                        await persist_current_turn()
                        first_text_latency_ms = (
                            int((turn.first_text_at - turn.turn_started_at) * 1000)
                            if turn.turn_started_at and turn.first_text_at is not None
                            else None
                        )
                        first_audio_latency_ms = (
                            int((turn.first_audio_at - turn.turn_started_at) * 1000)
                            if turn.turn_started_at and turn.first_audio_at is not None
                            else None
                        )
                        await emit(
                            "metrics.turn",
                            {
                                "turn_id": turn.turn_id or f"turn-{uuid.uuid4().hex[:10]}",
                                "first_text_latency_ms": first_text_latency_ms,
                                "first_audio_latency_ms": first_audio_latency_ms,
                            },
                        )
                        await emit("session.state.changed", {"state": "listening", "reason": "turn-done"})
                        turn.reset()
                        continue

            async def handle_client() -> None:
                nonlocal auto_reply, closed
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        event_name = str(data.get("event") or "")
                        if event_name == "audio_chunk":
                            audio_base64 = str(data.get("audio_base64") or "")
                            if audio_base64:
                                await upstream.send_str(json.dumps({"type": "input_audio_buffer.append", "audio": audio_base64}))
                            continue
                        if event_name == "session.config":
                            auto_reply = bool(data.get("auto_reply", True))
                            continue
                        if event_name == "response.cancel":
                            await cancel_response("response.cancel")
                            continue
                        if event_name == "input_audio.commit":
                            await commit_input_buffer()
                            continue
                        if event_name == "vad_end":
                            continue
                        if event_name in {"session.end", "end"}:
                            await emit("session.state.changed", {"state": "idle", "reason": "session-end"})
                            closed = True
                            await websocket.close()
                            await upstream.close()
                            break
                except Exception:
                    closed = True
                    try:
                        await upstream.close()
                    except Exception:
                        pass
                    raise

            await asyncio.gather(handle_upstream(), handle_client())
