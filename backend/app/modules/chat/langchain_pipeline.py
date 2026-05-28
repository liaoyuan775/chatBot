from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Awaitable, Callable

import httpx
from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.provider_gateway import (
    ProviderError,
    asr_transcribe,
    embedding,
    get_provider_context,
    omni_synthesize,
    rerank,
    stream_chat_completion,
    tts_synthesize,
)
from app.models import KnowledgeChunkEntity, KnowledgeDocumentEntity, SystemSettingEntity

settings = get_settings()
REALTIME_COMPAT_MODEL = "qwen-omni-turbo"
DEFAULT_RETRIEVAL_RUNTIME_CONFIG = {
    "top_k": 3,
    "similarity_threshold": 0.0,
    "rag_timeout_ms": 1500,
    "no_result_message": "未查询到相关知识，我将为您进行通用解答。",
    "embedding_provider": "siliconflow",
    "embedding_model": settings.siliconflow_embedding_model,
    "rerank_provider": "siliconflow",
    "rerank_model": settings.siliconflow_rerank_model,
}


def _extract_query_terms(question: str) -> set[str]:
    raw = (question or "").strip().lower()
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw):
        terms.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
            for size in (2, 3, 4):
                for idx in range(0, max(0, len(token) - size + 1)):
                    terms.add(token[idx : idx + size])
    return {term for term in terms if term.strip()}


def _garbled_ratio(text: str) -> float:
    if not text:
        return 1.0
    bad = sum(1 for ch in text if ch in {"?", "\ufffd"})
    return bad / max(1, len(text))


def _keyword_overlap_score(question: str, source_text: str) -> float:
    haystack = (source_text or "").lower()
    if not haystack:
        return 0.0
    score = 0.0
    for term in _extract_query_terms(question):
        if term in haystack:
            score += min(len(term), 8)
    return score


def _candidate_endpoints(base_url: str, path: str, provider_name: str) -> list[str]:
    base = base_url.rstrip("/")
    if provider_name == "dashscope":
        return [f"{base}/compatible-mode/v1{path}", f"{base}{path}"]
    if provider_name == "volcengine":
        return [f"{base}{path}", f"{base}/v1{path}"]
    return [f"{base}/v1{path}", f"{base}{path}"]


def _message_to_openai_dict(msg: BaseMessage) -> dict[str, str]:
    role = "user"
    msg_type = getattr(msg, "type", "human")
    if msg_type in {"ai", "assistant"}:
        role = "assistant"
    elif msg_type == "system":
        role = "system"
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return {"role": role, "content": content}


class ProviderChatModel(SimpleChatModel):
    provider_name: str
    model_name: str
    base_url: str
    api_key: str
    timeout_seconds: int = 20
    temperature: float = 0.4

    @property
    def _llm_type(self) -> str:
        return "provider-chat-model"

    def _call(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager=None, **kwargs: Any) -> str:
        payload = {
            "model": self.model_name,
            "messages": [_message_to_openai_dict(msg) for msg in messages],
            "temperature": float(kwargs.get("temperature", self.temperature)),
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: str | None = None
        with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
            for url in _candidate_endpoints(self.base_url, "/chat/completions", self.provider_name):
                try:
                    response = client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        last_error = f"{response.status_code}: {response.text[:300]}"
                        continue
                    data = response.json()
                    choices = data.get("choices") or []
                    if not choices:
                        last_error = "No choices returned."
                        continue
                    content = choices[0].get("message", {}).get("content", "")
                    if content:
                        return str(content)
                    last_error = "Empty content returned."
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
        raise ProviderError(last_error or "Chat completion failed.")


@dataclass
class LangChainTurnResult:
    text: str
    chain_name: str
    used_fallback: bool
    audio_base64: str | None = None
    audio_mime: str | None = None
    fallback_reason: str | None = None
    pipeline: str = ""
    voice_used: str | None = None
    provider_trace: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    timed_out: bool = False


async def _invoke_chat_lcel(
    *,
    db: AsyncSession,
    provider_name: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
) -> str:
    ctx = await get_provider_context(db, provider_name)
    model = ProviderChatModel(
        provider_name=provider_name,
        model_name=model_name,
        base_url=ctx.base_url,
        api_key=ctx.api_key,
        timeout_seconds=ctx.timeout_seconds,
        temperature=temperature,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            ("human", "{user_prompt}"),
        ]
    )

    async def _run_model(prompt_value) -> str:
        ai_msg = await asyncio.to_thread(model.invoke, prompt_value.to_messages())
        if isinstance(ai_msg, AIMessage):
            return str(ai_msg.content)
        return str(getattr(ai_msg, "content", ""))

    chain = prompt | RunnableLambda(_run_model)
    text = await chain.ainvoke({"system_prompt": system_prompt, "user_prompt": user_prompt})
    return str(text).strip()


def _clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated {len(text) - limit} chars]"


def _build_augmented_user_prompt(*, user_text: str, context_text: str, knowledge_text: str) -> str:
    clipped_user = _clip_text((user_text or "").strip(), 1800)
    clipped_context = _clip_text((context_text or "").strip(), 1200)
    clipped_knowledge = _clip_text((knowledge_text or "").strip(), 1500)
    knowledge_block = (
        "Retrieved Knowledge (optional; use only when it is relevant to the latest user question):\n"
        f"{clipped_knowledge}"
        if clipped_knowledge
        else "Retrieved Knowledge (optional):\n"
    )
    return (
        f"Conversation Context:\n{clipped_context}\n\n"
        f"{knowledge_block}\n\n"
        f"Latest User Question:\n{clipped_user}"
    )


async def run_history_context_lcel(
    *,
    db: AsyncSession,
    provider_name: str,
    model_name: str,
    history_texts: list[str],
) -> str:
    async def _build(payload: dict[str, Any]) -> str:
        lines = [str(item).strip() for item in payload.get("history_texts", []) if str(item).strip()]
        if not lines:
            return "No context"
        merged = "\n".join(f"- {line}" for line in lines[-8:])
        return _clip_text(merged, 1200)

    formatted = await RunnableLambda(_build).ainvoke({"history_texts": history_texts})
    if formatted == "No context":
        return formatted

    try:
        summary = await _invoke_chat_lcel(
            db=db,
            provider_name=provider_name,
            model_name=model_name,
            system_prompt="Summarize the conversation context into <= 120 Chinese characters.",
            user_prompt=str(formatted),
            temperature=0.2,
        )
        clean = summary.strip()
        return clean or str(formatted)
    except Exception:  # noqa: BLE001
        return str(formatted)


async def summarize_title_lcel(
    *,
    db: AsyncSession,
    provider_name: str,
    model_name: str,
    user_text: str,
) -> str:
    title = await _invoke_chat_lcel(
        db=db,
        provider_name=provider_name,
        model_name=model_name,
        system_prompt="你是标题助手。请把用户首句总结为简短中文标题，不超过12个字，不要标点，不要解释。",
        user_prompt=_clip_text(user_text.strip(), 400),
        temperature=0.2,
    )
    return title.strip()


async def probe_provider_chat_lcel(
    *,
    db: AsyncSession,
    provider_name: str,
    model_name: str,
) -> tuple[bool, str]:
    try:
        pong = await _invoke_chat_lcel(
            db=db,
            provider_name=provider_name,
            model_name=model_name,
            system_prompt="Reply with exactly: pong",
            user_prompt="ping",
            temperature=0,
        )
        return True, f"chat_probe={pong[:32]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


async def is_knowledge_globally_enabled(db: AsyncSession) -> bool:
    row = await db.get(SystemSettingEntity, "knowledge_global")
    if not row or not isinstance(row.setting_value, dict):
        return True
    return bool(row.setting_value.get("enabled", True))


async def get_retrieval_runtime_config(
    db: AsyncSession,
    *,
    chain_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = await db.get(SystemSettingEntity, "knowledge_retrieval_config")
    base_config = row.setting_value if row and isinstance(row.setting_value, dict) else {}
    merged = {**DEFAULT_RETRIEVAL_RUNTIME_CONFIG, **base_config}
    mapping = chain_mapping or {}
    if str(mapping.get("embedding_model") or "").strip():
        merged["embedding_model"] = str(mapping["embedding_model"]).strip()
    if str(mapping.get("rerank_model") or "").strip():
        merged["rerank_model"] = str(mapping["rerank_model"]).strip()
    return merged


async def run_rag_chain_lcel(
    *,
    db: AsyncSession,
    question: str,
    top_k: int = 3,
    similarity_threshold: float | None = None,
    chain_mapping: dict[str, Any] | None = None,
    rag_timeout_ms: int | None = None,
) -> LangChainTurnResult:
    started = perf_counter()
    safe_question = _clip_text((question or "").strip(), 1000)
    retrieval_cfg = await get_retrieval_runtime_config(db, chain_mapping=chain_mapping)
    emb_provider = str(retrieval_cfg.get("embedding_provider", "siliconflow"))
    emb_model = str(retrieval_cfg.get("embedding_model", settings.siliconflow_embedding_model))
    rr_provider = str(retrieval_cfg.get("rerank_provider", "siliconflow"))
    rr_model = str(retrieval_cfg.get("rerank_model", settings.siliconflow_rerank_model))
    effective_top_k = max(1, int(top_k or retrieval_cfg.get("top_k", 3)))
    threshold = (
        float(similarity_threshold)
        if similarity_threshold is not None
        else float(retrieval_cfg.get("similarity_threshold", 0.0))
    )
    timeout_ms = max(100, int(rag_timeout_ms or retrieval_cfg.get("rag_timeout_ms", 1500) or 1500))
    trace: dict[str, Any] = {
        "embedding": {"provider": emb_provider, "model": emb_model},
        "rerank": {"provider": rr_provider, "model": rr_model},
        "config": {"top_k": effective_top_k, "similarity_threshold": threshold, "rag_timeout_ms": timeout_ms},
    }

    async def _run(payload: dict[str, Any]) -> str:
        query_vec = (await embedding(db, payload["emb_provider"], payload["emb_model"], payload["question"]))[0]
        documents = {
            row.id: row.file_name
            for row in (await db.scalars(select(KnowledgeDocumentEntity))).all()
        }
        rows = (await db.scalars(select(KnowledgeChunkEntity))).all()
        if not rows:
            return ""

        def dot(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b))

        scored_rows: list[tuple[float, str]] = []
        for item in rows:
            source_name = documents.get(item.document_id, "")
            content = item.content or ""
            candidate_text = f"Source: {source_name}\n{content}".strip()
            garbled_penalty = 1.0 if _garbled_ratio(candidate_text) <= 0.15 else -20.0
            semantic_score = dot(query_vec, item.embedding)
            lexical_score = _keyword_overlap_score(payload["question"], candidate_text)
            scored_rows.append((semantic_score + lexical_score + garbled_penalty, candidate_text))

        filtered_rows = [item for item in scored_rows if item[0] >= payload["similarity_threshold"]]
        ranked = sorted(filtered_rows, key=lambda item: item[0], reverse=True)[: max(payload["top_k"] * 6, payload["top_k"])]
        docs = [candidate_text for _, candidate_text in ranked]
        if not docs:
            return ""
        try:
            rr = await rerank(
                db,
                payload["rr_provider"],
                payload["rr_model"],
                payload["question"],
                docs,
                top_n=payload["top_k"],
            )
        except Exception:  # noqa: BLE001
            rr = []
        picked = [docs[item.get("index", 0)] for item in rr if isinstance(item.get("index"), int)]
        return "\n".join((picked or docs)[: payload["top_k"]])

    rag_chain = RunnableLambda(_run)
    fallback_reason: str | None = None
    knowledge_text = ""
    timed_out = False
    try:
        knowledge_text = await asyncio.wait_for(
            rag_chain.ainvoke(
                {
                    "question": safe_question,
                    "emb_provider": emb_provider,
                    "emb_model": emb_model,
                    "rr_provider": rr_provider,
                    "rr_model": rr_model,
                    "top_k": effective_top_k,
                    "similarity_threshold": threshold,
                }
            ),
            timeout=timeout_ms / 1000,
        )
        hit_count = max(0, str(knowledge_text).count("Source:")) or (1 if str(knowledge_text).strip() else 0)
        trace["status"] = "hit" if hit_count > 0 else "no_hit"
        trace["hit_count"] = hit_count
    except asyncio.TimeoutError:
        fallback_reason = f"rag_timeout:{timeout_ms}ms"
        knowledge_text = ""
        timed_out = True
        trace["status"] = "timeout"
        trace["hit_count"] = 0
    except Exception as exc:  # noqa: BLE001
        fallback_reason = str(exc)
        knowledge_text = ""
        trace["status"] = "provider_error"
        trace["hit_count"] = 0

    return LangChainTurnResult(
        text=str(knowledge_text),
        chain_name="rag_chain",
        used_fallback=False,
        fallback_reason=fallback_reason,
        pipeline="rag_chain",
        provider_trace=trace,
        latency_ms=int((perf_counter() - started) * 1000),
        timed_out=timed_out,
    )


async def run_text_chain_lcel(
    *,
    db: AsyncSession,
    provider_name: str,
    model_name: str,
    user_text: str,
    context_text: str,
    knowledge_text: str,
    system_prompt: str = "You are a Chinese multimodal assistant. Keep answers concise and accurate.",
) -> LangChainTurnResult:
    started = perf_counter()
    user_prompt = _build_augmented_user_prompt(
        user_text=user_text,
        context_text=context_text,
        knowledge_text=knowledge_text,
    )
    result_text = await _invoke_chat_lcel(
        db=db,
        provider_name=provider_name,
        model_name=model_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.4,
    )
    return LangChainTurnResult(
        text=result_text,
        chain_name="text_chain",
        used_fallback=False,
        pipeline="rag_chain->text_chain",
        provider_trace={"llm": {"provider": provider_name, "model": model_name}},
        latency_ms=int((perf_counter() - started) * 1000),
    )


async def stream_text_chain_lcel(
    *,
    db: AsyncSession,
    provider_name: str,
    model_name: str,
    user_text: str,
    context_text: str,
    knowledge_text: str,
    system_prompt: str = "You are a Chinese multimodal assistant. Keep answers concise and accurate.",
):
    user_prompt = _build_augmented_user_prompt(
        user_text=user_text,
        context_text=context_text,
        knowledge_text=knowledge_text,
    )
    async for delta in stream_chat_completion(
        db=db,
        provider_name=provider_name,
        model= model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    ):
        yield delta


async def run_single_voice_chain_lcel(
    *,
    db: AsyncSession,
    asr_provider: str,
    asr_model: str,
    audio_bytes: bytes,
    filename: str,
) -> LangChainTurnResult:
    started = perf_counter()
    max_safe_bytes = 2 * 1024 * 1024

    async def _run_asr(payload: dict[str, Any]) -> str:
        return await asr_transcribe(
            db,
            payload["asr_provider"],
            payload["asr_model"],
            payload["audio_bytes"],
            payload["filename"],
        )

    asr_chain = RunnableLambda(_run_asr)
    fallback_reason: str | None = None
    provider_trace: dict[str, Any] = {
        "asr": {"provider": asr_provider, "model": asr_model, "source_bytes": len(audio_bytes)},
    }
    try:
        text = await asr_chain.ainvoke(
            {
                "asr_provider": asr_provider,
                "asr_model": asr_model,
                "audio_bytes": audio_bytes,
                "filename": filename,
            }
        )
    except Exception as exc:  # noqa: BLE001
        fallback_reason = str(exc)
        # Large voice samples can exceed provider-side processing windows.
        # Retry with the leading segment to keep the single-voice chain usable.
        if len(audio_bytes) > max_safe_bytes:
            try:
                clipped = audio_bytes[:max_safe_bytes]
                text = await asr_chain.ainvoke(
                    {
                        "asr_provider": asr_provider,
                        "asr_model": asr_model,
                        "audio_bytes": clipped,
                        "filename": f"clip_{filename}",
                    }
                )
                provider_trace["asr"]["clipped_retry"] = True
                provider_trace["asr"]["clipped_bytes"] = len(clipped)
                fallback_reason = None
            except Exception as clip_exc:  # noqa: BLE001
                fallback_reason = f"{fallback_reason}; clipped_retry={clip_exc}"
                text = "语音未识别，请用户重试"
        else:
            text = "语音未识别，请用户重试"

    clean = str(text or "").strip()
    if not clean:
        clean = "语音未识别，请用户重试"
        fallback_reason = fallback_reason or "ASR returned empty text."

    return LangChainTurnResult(
        text=clean,
        chain_name="single_voice_chain",
        used_fallback=False,
        fallback_reason=fallback_reason,
        pipeline="single_voice_chain",
        provider_trace=provider_trace,
        latency_ms=int((perf_counter() - started) * 1000),
    )


@dataclass
class RealtimePreparedResult:
    text: str
    chain_name: str
    used_fallback: bool
    fallback_reason: str | None
    provider_trace: dict[str, Any]
    voice_used: str | None
    tts_provider: str
    tts_model: str
    latency_ms: int
    synthesize_audio: Callable[[], Awaitable[tuple[str, str]]]
    tts_source: str = "fallback_tts"


async def prepare_realtime_chain_lcel(
    *,
    db: AsyncSession,
    main_provider: str,
    main_model: str,
    fallback_llm_provider: str,
    fallback_llm_model: str,
    tts_provider: str,
    tts_model: str,
    tts_voice: str,
    text_input: str,
    context_text: str = "No context",
    knowledge_text: str = "",
    system_prompt: str = "You are a real-time voice assistant.",
    prefer_main_tts: bool = False,
) -> RealtimePreparedResult:
    started = perf_counter()
    provider_trace: dict[str, Any] = {}
    fallback_reason: str | None = None
    actual_main_model = main_model
    user_prompt = _build_augmented_user_prompt(
        user_text=text_input,
        context_text=context_text,
        knowledge_text=knowledge_text,
    )

    try:
        reply_text = await _invoke_chat_lcel(
            db=db,
            provider_name=main_provider,
            model_name=main_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
        )
        provider_trace["llm"] = {"provider": main_provider, "model": main_model, "requested_model": main_model}
        chain_name = "main_chain"
        used_fallback = False
    except Exception as exc:  # noqa: BLE001
        fallback_reason = str(exc)
        can_try_compat = (
            main_provider == "dashscope"
            and "realtime" in main_model.lower()
            and main_model != REALTIME_COMPAT_MODEL
        )
        if can_try_compat:
            try:
                reply_text = await _invoke_chat_lcel(
                    db=db,
                    provider_name=main_provider,
                    model_name=REALTIME_COMPAT_MODEL,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3,
                )
                actual_main_model = REALTIME_COMPAT_MODEL
                provider_trace["llm"] = {
                    "provider": main_provider,
                    "model": REALTIME_COMPAT_MODEL,
                    "requested_model": main_model,
                    "compat_mode": True,
                }
                chain_name = "main_chain_compat"
                used_fallback = True
                fallback_reason = f"primary={exc}"
            except Exception as compat_exc:  # noqa: BLE001
                fallback_reason = f"primary={exc}; compat={compat_exc}"
                reply_text = await _invoke_chat_lcel(
                    db=db,
                    provider_name=fallback_llm_provider,
                    model_name=fallback_llm_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3,
                )
                provider_trace["llm"] = {"provider": fallback_llm_provider, "model": fallback_llm_model}
                chain_name = "fallback_chain"
                used_fallback = True
        else:
            reply_text = await _invoke_chat_lcel(
                db=db,
                provider_name=fallback_llm_provider,
                model_name=fallback_llm_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            provider_trace["llm"] = {"provider": fallback_llm_provider, "model": fallback_llm_model}
            chain_name = "fallback_chain"
            used_fallback = True

    if actual_main_model != main_model:
        provider_trace["main_model_actual"] = actual_main_model

    async def _synthesize_audio() -> tuple[str, str]:
        if prefer_main_tts:
            audio_base64, audio_mime = await omni_synthesize(
                db,
                main_provider,
                actual_main_model,
                tts_voice,
                reply_text,
                response_format="mp3",
            )
            return audio_base64, audio_mime
        audio_base64, audio_mime = await tts_synthesize(
            db,
            tts_provider,
            tts_model,
            tts_voice,
            reply_text,
            response_format="mp3",
            stream=False,
        )
        return audio_base64, audio_mime

    return RealtimePreparedResult(
        text=str(reply_text),
        chain_name=chain_name,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        provider_trace=provider_trace,
        voice_used=tts_voice,
        tts_provider=main_provider if prefer_main_tts else tts_provider,
        tts_model=actual_main_model if prefer_main_tts else tts_model,
        latency_ms=int((perf_counter() - started) * 1000),
        synthesize_audio=_synthesize_audio,
        tts_source="main_omni_model" if prefer_main_tts else "fallback_tts",
    )


async def run_realtime_chain_lcel(
    *,
    db: AsyncSession,
    main_provider: str,
    main_model: str,
    fallback_llm_provider: str,
    fallback_llm_model: str,
    tts_provider: str,
    tts_model: str,
    tts_voice: str,
    text_input: str,
    context_text: str = "No context",
    knowledge_text: str = "",
    system_prompt: str = "You are a real-time voice assistant.",
    synthesize_audio: bool = True,
) -> LangChainTurnResult:
    prepared = await prepare_realtime_chain_lcel(
        db=db,
        main_provider=main_provider,
        main_model=main_model,
        fallback_llm_provider=fallback_llm_provider,
        fallback_llm_model=fallback_llm_model,
        tts_provider=tts_provider,
        tts_model=tts_model,
        tts_voice=tts_voice,
        text_input=text_input,
        context_text=context_text,
        knowledge_text=knowledge_text,
        system_prompt=system_prompt,
    )
    provider_trace = dict(prepared.provider_trace)
    audio_base64 = ""
    audio_mime: str | None = None
    total_started = perf_counter()
    if synthesize_audio:
        audio_base64, audio_mime = await prepared.synthesize_audio()
        provider_trace["tts"] = {"provider": prepared.tts_provider, "model": prepared.tts_model, "source": prepared.tts_source}

    return LangChainTurnResult(
        text=prepared.text,
        chain_name=prepared.chain_name,
        used_fallback=prepared.used_fallback,
        audio_base64=str(audio_base64),
        audio_mime=audio_mime,
        fallback_reason=prepared.fallback_reason,
        pipeline="realtime_voice_chain",
        voice_used=prepared.voice_used,
        provider_trace=provider_trace,
        latency_ms=prepared.latency_ms + int((perf_counter() - total_started) * 1000),
    )
