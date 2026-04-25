from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    CallConfigEntity,
    ChainConfigEntity,
    ModelCatalogEntity,
    PersonaEntity,
    ProviderConfigEntity,
    SessionChainAuditEntity,
    SessionEntity,
    VoiceProfileEntity,
)
from app.modules.chain_config.router import get_chain_validation_result
from app.modules.chat.langchain_pipeline import (
    prepare_realtime_chain_lcel,
    run_realtime_chain_lcel,
    run_single_voice_chain_lcel,
    run_text_chain_lcel,
)

settings = get_settings()
REALTIME_COMPAT_MODEL = "qwen-omni-turbo"
TEXT_EMERGENCY_PROVIDER = "dashscope"
TEXT_EMERGENCY_MODEL = "qwen-plus"

BASELINE_MODELS = [
    ("dashscope", settings.dashscope_realtime_model, "llm", True),
    ("dashscope", REALTIME_COMPAT_MODEL, "llm", True),
    ("dashscope", TEXT_EMERGENCY_MODEL, "llm", True),
    ("siliconflow", "FunAudioLLM/SenseVoiceSmall", "asr", True),
    ("volcengine", "doubao-seed-1-6-251015", "llm", True),
    ("siliconflow", settings.siliconflow_tts_model, "tts", True),
    ("siliconflow", "BAAI/bge-m3", "embedding", True),
    ("siliconflow", "BAAI/bge-reranker-v2-m3", "rerank", True),
    ("dashscope", "z-image-turbo", "image", True),
]


@dataclass
class ChainResult:
    text: str
    chain_name: str
    used_fallback: bool
    fail_reason: str | None = None
    audio_base64: str | None = None
    audio_mime: str | None = None
    fallback_reason: str | None = None
    pipeline: str = ""
    voice_used: str | None = None
    provider_trace: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0


@dataclass
class SessionRuntimeConfig:
    chain_name: str = "default"
    chain_mapping: dict[str, Any] = field(default_factory=dict)
    text_llm_provider: str = "volcengine"
    text_llm_model: str = "doubao-seed-1-6-251015"
    image_provider: str = "dashscope"
    image_model: str = "z-image-turbo"
    realtime_main_provider: str = "dashscope"
    realtime_main_model: str = "qwen3.5-omni-plus-realtime"
    realtime_fallback_llm_provider: str = "volcengine"
    realtime_fallback_llm_model: str = "doubao-seed-1-6-251015"
    asr_provider: str = "siliconflow"
    asr_model: str = "FunAudioLLM/SenseVoiceSmall"
    tts_provider: str = "siliconflow"
    tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    tts_voice: str = "FunAudioLLM/CosyVoice2-0.5B:alex"
    omni_mode: str = "auto"
    use_main_for_asr: bool = False
    use_main_for_tts: bool = False
    persona_system_prompt: str = "You are a Chinese multimodal assistant. Keep answers concise and accurate."
    persona_realtime_prompt: str = "You are a real-time voice assistant."


def _extract_model_capabilities(model_row: ModelCatalogEntity | None) -> set[str]:
    if not model_row:
        return set()
    metadata = model_row.metadata_json or {}
    raw = metadata.get("capabilities") if isinstance(metadata, dict) else None
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    return set()


def _infer_capabilities_from_name(model_name: str) -> set[str]:
    name = (model_name or "").strip().lower()
    capabilities: set[str] = set()
    if not name:
        return capabilities
    if any(keyword in name for keyword in ["omni", "realtime"]):
        capabilities.update({"chat", "realtime", "audio_input", "audio_output", "asr", "tts"})
    if any(keyword in name for keyword in ["sensevoice", "asr"]):
        capabilities.update({"audio_input", "asr"})
    if any(keyword in name for keyword in ["cosyvoice", "tts"]):
        capabilities.update({"audio_output", "tts"})
    if any(keyword in name for keyword in ["qwen", "doubao", "seed"]):
        capabilities.add("chat")
    return capabilities


async def _find_enabled_model(db: AsyncSession, provider_name: str, model_name: str) -> ModelCatalogEntity | None:
    provider_row = await db.scalar(select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name))
    if not provider_row or not model_name:
        return None
    return await db.scalar(
        select(ModelCatalogEntity).where(
            ModelCatalogEntity.provider_id == provider_row.id,
            ModelCatalogEntity.model_name == model_name,
            ModelCatalogEntity.is_enabled.is_(True),
        )
    )


async def _resolve_model_capabilities(db: AsyncSession, provider_name: str, model_name: str) -> set[str]:
    model_row = await _find_enabled_model(db, provider_name, model_name)
    capabilities = _extract_model_capabilities(model_row)
    if capabilities:
        return capabilities
    return _infer_capabilities_from_name(model_name)


def _should_prefer_main_audio(omni_mode: str) -> bool:
    mode = (omni_mode or "").strip().lower()
    # This project currently uses a split-compatible realtime stack:
    # ASR/TTS are executed via dedicated endpoints unless explicitly forced.
    return mode in {"enabled", "force_main", "prefer_main"}


def _normalize_tts_voice(provider_name: str, voice_name: str) -> str:
    provider = (provider_name or "").strip().lower()
    voice = (voice_name or "").strip()
    if provider == "dashscope":
        # DashScope expects a provider-native voice id (e.g. longanyang),
        # not SiliconFlow style names like FunAudio...:alex.
        if not voice or "/" in voice or ":" in voice:
            return settings.dashscope_tts_voice
        return voice
    if provider == "siliconflow":
        return voice or settings.siliconflow_tts_voice
    return voice or settings.siliconflow_tts_voice


def _persona_prompt_from_config(config: dict[str, Any] | None, *, realtime: bool) -> str:
    base = "You are a Chinese multimodal assistant. Keep answers concise and accurate."
    if realtime:
        base = "You are a real-time voice assistant."
    if not config:
        return base
    role = str(config.get("role") or "assistant")
    style = str(config.get("style") or "professional")
    tone = str(config.get("tone") or "calm")
    strictness = str(config.get("strictness") or "medium")
    allow_question_back = bool(config.get("allow_question_back", False))
    unknown_answer = str(config.get("unknown_answer") or "这个问题我暂时没有可靠依据。")
    return (
        f"{base}\n"
        f"Persona role: {role}\n"
        f"Style: {style}\n"
        f"Tone: {tone}\n"
        f"Strictness: {strictness}\n"
        f"Allow question back: {allow_question_back}\n"
        f"If uncertain: {unknown_answer}"
    )


async def _resolve_model_provider(
    db: AsyncSession,
    *,
    model_name: str | None,
    expected_type: str,
    fallback_provider: str,
    fallback_model: str,
) -> tuple[str, str]:
    candidate = (model_name or "").strip()
    if not candidate:
        return fallback_provider, fallback_model

    rows = (
        await db.scalars(
            select(ModelCatalogEntity).where(
                ModelCatalogEntity.model_name == candidate,
                ModelCatalogEntity.model_type == expected_type,
                ModelCatalogEntity.is_enabled.is_(True),
            )
        )
    ).all()
    for row in rows:
        provider = await db.get(ProviderConfigEntity, row.provider_id)
        if provider:
            return provider.provider_name, row.model_name
    return fallback_provider, fallback_model


async def ensure_baseline_model_catalog(db: AsyncSession) -> None:
    provider_map = {
        row.provider_name: row
        for row in (await db.scalars(select(ProviderConfigEntity))).all()
    }
    changed = False
    for provider_name, model_name, model_type, is_enabled in BASELINE_MODELS:
        provider = provider_map.get(provider_name)
        if not provider:
            continue
        row = await db.scalar(
            select(ModelCatalogEntity).where(
                ModelCatalogEntity.provider_id == provider.id,
                ModelCatalogEntity.model_name == model_name,
            )
        )
        metadata_json = {"id": model_name, "seeded": True}
        if not row:
            db.add(
                ModelCatalogEntity(
                    provider_id=provider.id,
                    model_name=model_name,
                    model_type=model_type,
                    is_enabled=is_enabled,
                    is_available=True,
                    metadata_json=metadata_json,
                )
            )
            changed = True
        else:
            row.model_type = model_type
            row.is_available = True
            if is_enabled:
                row.is_enabled = True
            if not row.metadata_json:
                row.metadata_json = metadata_json
            changed = True
    if changed:
        await db.commit()


async def ensure_default_call_config(db: AsyncSession) -> CallConfigEntity:
    await ensure_baseline_model_catalog(db)
    row = await db.scalar(select(CallConfigEntity).order_by(CallConfigEntity.updated_at.desc()))
    if row:
        return row
    row = CallConfigEntity(
        main_provider="dashscope",
        main_model=settings.dashscope_realtime_model,
        omni_mode="auto",
        fallback_asr_provider="siliconflow",
        fallback_asr_model=settings.siliconflow_asr_model,
        fallback_llm_provider="volcengine",
        fallback_llm_model=settings.volcengine_text_model,
        fallback_tts_provider="siliconflow",
        fallback_tts_model=settings.siliconflow_tts_model,
        fallback_tts_voice=settings.siliconflow_tts_voice,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _audit(
    db: AsyncSession,
    session_id,
    mode: str,
    chain_name: str,
    success: bool,
    retries: int,
    fail_reason: str | None,
    trace: dict[str, Any],
    message_id=None,
) -> None:
    db.add(
        SessionChainAuditEntity(
            session_id=session_id,
            message_id=message_id,
            mode=mode,
            chain_name=chain_name,
            success=success,
            retries=retries,
            fail_reason=fail_reason,
            trace_json=trace,
        )
    )
    await db.commit()


async def _resolve_tts_config_by_voice(
    db: AsyncSession,
    voice_id,
    default_provider: str,
    default_model: str,
    default_voice: str,
) -> tuple[str, str, str]:
    tts_provider = default_provider
    tts_model = default_model
    tts_voice = default_voice
    if not voice_id:
        return tts_provider, tts_model, tts_voice
    voice_profile = await db.get(VoiceProfileEntity, voice_id)
    if not voice_profile:
        return tts_provider, tts_model, tts_voice
    voice_cfg = voice_profile.config_json or {}
    configured_provider = str(voice_cfg.get("tts_provider") or "").strip()
    configured_model = str(voice_cfg.get("tts_model") or "").strip()
    configured = str(voice_cfg.get("voice_name") or "").strip()
    if configured_provider:
        tts_provider = configured_provider
    if configured_model:
        tts_model = configured_model
    if configured:
        tts_voice = configured
        # heuristic: SiliconFlow cloning uri implies SiliconFlow CosyVoice2
        if (tts_voice.startswith("speech:") or tts_voice.startswith("custom:")) and not configured_provider:
            tts_provider = "siliconflow"
        if (tts_voice.startswith("speech:") or tts_voice.startswith("custom:")) and not configured_model:
            tts_model = settings.siliconflow_tts_model
    return tts_provider, tts_model, tts_voice


async def resolve_session_runtime(db: AsyncSession, session_id) -> SessionRuntimeConfig:
    cfg = await ensure_default_call_config(db)
    runtime = SessionRuntimeConfig(
        chain_name="default",
        text_llm_provider=cfg.fallback_llm_provider,
        text_llm_model=cfg.fallback_llm_model,
        image_provider="dashscope",
        image_model="z-image-turbo",
        realtime_main_provider=cfg.main_provider,
        realtime_main_model=cfg.main_model,
        realtime_fallback_llm_provider=cfg.fallback_llm_provider,
        realtime_fallback_llm_model=cfg.fallback_llm_model,
        asr_provider=cfg.fallback_asr_provider,
        asr_model=cfg.fallback_asr_model,
        tts_provider=cfg.fallback_tts_provider,
        tts_model=cfg.fallback_tts_model,
        tts_voice=cfg.fallback_tts_voice,
        omni_mode=getattr(cfg, "omni_mode", "auto"),
        persona_system_prompt=_persona_prompt_from_config(None, realtime=False),
        persona_realtime_prompt=_persona_prompt_from_config(None, realtime=True),
    )
    session = await db.get(SessionEntity, session_id)
    if not session:
        return runtime

    chain = await db.get(ChainConfigEntity, session.chain_id) if session.chain_id else None
    if chain:
        is_valid, _errors = await get_chain_validation_result(db, chain)
        chain.is_valid = is_valid
        if not is_valid:
            # 链路不完整时不阻断对话，按回退配置继续执行文本链路。
            await db.commit()
            runtime.chain_name = f"{chain.name} (degraded)"
        else:
            runtime.chain_name = chain.name
        mapping = chain.mapping_json or {}
        runtime.chain_mapping = dict(mapping)
        runtime.text_llm_provider, runtime.text_llm_model = await _resolve_model_provider(
            db,
            model_name=str(mapping.get("llm_model") or ""),
            expected_type="llm",
            fallback_provider=runtime.text_llm_provider,
            fallback_model=runtime.text_llm_model,
        )
        runtime.realtime_fallback_llm_provider = runtime.text_llm_provider
        runtime.realtime_fallback_llm_model = runtime.text_llm_model

        chain_llm_model = str(mapping.get("llm_model") or "")
        if "realtime" in chain_llm_model.lower():
            runtime.realtime_main_provider, runtime.realtime_main_model = await _resolve_model_provider(
                db,
                model_name=chain_llm_model,
                expected_type="llm",
                fallback_provider=runtime.realtime_main_provider,
                fallback_model=runtime.realtime_main_model,
            )

        runtime.asr_provider, runtime.asr_model = await _resolve_model_provider(
            db,
            model_name=str(mapping.get("asr_model") or ""),
            expected_type="asr",
            fallback_provider=runtime.asr_provider,
            fallback_model=runtime.asr_model,
        )
        runtime.tts_provider, runtime.tts_model = await _resolve_model_provider(
            db,
            model_name=str(mapping.get("tts_model") or ""),
            expected_type="tts",
            fallback_provider=runtime.tts_provider,
            fallback_model=runtime.tts_model,
        )
        runtime.image_provider, runtime.image_model = await _resolve_model_provider(
            db,
            model_name=str(mapping.get("image_model") or ""),
            expected_type="image",
            fallback_provider=runtime.image_provider,
            fallback_model=runtime.image_model,
        )

    persona_id = session.persona_id or (chain.persona_id if chain else None)
    persona = await db.get(PersonaEntity, persona_id) if persona_id else None
    runtime.persona_system_prompt = _persona_prompt_from_config(persona.config_json if persona else None, realtime=False)
    runtime.persona_realtime_prompt = _persona_prompt_from_config(persona.config_json if persona else None, realtime=True)

    voice_id = session.voice_id or (chain.voice_id if chain else None)
    runtime.tts_provider, runtime.tts_model, runtime.tts_voice = await _resolve_tts_config_by_voice(
        db,
        voice_id,
        runtime.tts_provider,
        runtime.tts_model,
        runtime.tts_voice,
    )
    runtime.tts_voice = _normalize_tts_voice(runtime.tts_provider, runtime.tts_voice)
    main_capabilities = await _resolve_model_capabilities(db, runtime.realtime_main_provider, runtime.realtime_main_model)
    if _should_prefer_main_audio(runtime.omni_mode):
        if {"audio_input", "asr"} & main_capabilities:
            runtime.use_main_for_asr = True
            runtime.asr_provider = runtime.realtime_main_provider
            runtime.asr_model = runtime.realtime_main_model
        if {"audio_output", "tts"} & main_capabilities:
            runtime.use_main_for_tts = True
            runtime.tts_provider = runtime.realtime_main_provider
            runtime.tts_model = runtime.realtime_main_model
    return runtime


async def run_text_chain(
    db: AsyncSession,
    session_id,
    user_text: str,
    context_text: str,
    knowledge_text: str = "",
    message_id=None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    system_prompt: str | None = None,
    chain_name_hint: str | None = None,
) -> ChainResult:
    cfg = await ensure_default_call_config(db)
    primary_provider = llm_provider or cfg.fallback_llm_provider
    primary_model = llm_model or cfg.fallback_llm_model
    resolved_system_prompt = system_prompt or "You are a Chinese multimodal assistant. Keep answers concise and accurate."
    try:
        primary = await run_text_chain_lcel(
            db=db,
            provider_name=primary_provider,
            model_name=primary_model,
            user_text=user_text,
            context_text=context_text,
            knowledge_text=knowledge_text,
            system_prompt=resolved_system_prompt,
        )
        chain_name = f"text_chain:{chain_name_hint}" if chain_name_hint else primary.chain_name
        await _audit(
            db,
            session_id=session_id,
            mode="text",
            chain_name=chain_name,
            success=True,
            retries=0,
            fail_reason=primary.fallback_reason,
            trace={
                **primary.provider_trace,
                "llm_fallback": False,
                "chain_name_hint": chain_name_hint,
                "pipeline": primary.pipeline,
                "latency_ms": primary.latency_ms,
            },
            message_id=message_id,
        )
        return ChainResult(
            text=primary.text,
            chain_name=chain_name,
            used_fallback=primary.used_fallback,
            fail_reason=primary.fallback_reason,
            fallback_reason=primary.fallback_reason,
            pipeline=primary.pipeline,
            provider_trace=primary.provider_trace,
            latency_ms=primary.latency_ms,
        )
    except Exception as primary_exc:  # noqa: BLE001
        # Keep the required Seed chain as first path, then degrade to an emergency
        # public model so text/single-voice chat stays available.
        try:
            emergency = await run_text_chain_lcel(
                db=db,
                provider_name=TEXT_EMERGENCY_PROVIDER,
                model_name=TEXT_EMERGENCY_MODEL,
                user_text=user_text,
                context_text=context_text,
                knowledge_text=knowledge_text,
                system_prompt=resolved_system_prompt,
            )
            trace = {
                **emergency.provider_trace,
                "llm_fallback": True,
                "pipeline": "rag_chain->text_chain(emergency)",
                "primary_error": str(primary_exc),
                "primary_provider": primary_provider,
                "primary_model": primary_model,
                "chain_name_hint": chain_name_hint,
                "latency_ms": emergency.latency_ms,
            }
            await _audit(
                db,
                session_id=session_id,
                mode="text",
                chain_name="text_chain_emergency",
                success=True,
                retries=1,
                fail_reason=str(primary_exc),
                trace=trace,
                message_id=message_id,
            )
            return ChainResult(
                text=emergency.text,
                chain_name="text_chain_emergency",
                used_fallback=True,
                fail_reason=str(primary_exc),
                fallback_reason=str(primary_exc),
                pipeline="rag_chain->text_chain(emergency)",
                provider_trace=trace,
                latency_ms=emergency.latency_ms,
            )
        except Exception as emergency_exc:  # noqa: BLE001
            fail_text = f"primary={primary_exc}; emergency={emergency_exc}"
            await db.rollback()
            cfg = await ensure_default_call_config(db)
            await _audit(
                db,
                session_id=session_id,
                mode="text",
                chain_name="text_chain",
                success=False,
                retries=2,
                fail_reason=fail_text,
                trace={"provider": cfg.fallback_llm_provider, "model": cfg.fallback_llm_model, "pipeline": "rag_chain->text_chain"},
                message_id=message_id,
            )
            raise RuntimeError(fail_text) from emergency_exc

async def prepare_realtime_chain(
    db: AsyncSession,
    session_id,
    text_input: str,
    *,
    context_text: str = "No context",
    knowledge_text: str = "",
):
    runtime = await resolve_session_runtime(db, session_id)
    return await prepare_realtime_chain_lcel(
        db=db,
        main_provider=runtime.realtime_main_provider,
        main_model=runtime.realtime_main_model,
        fallback_llm_provider=runtime.realtime_fallback_llm_provider,
        fallback_llm_model=runtime.realtime_fallback_llm_model,
        tts_provider=runtime.tts_provider,
        tts_model=runtime.tts_model,
        tts_voice=runtime.tts_voice,
        text_input=text_input,
        context_text=context_text,
        knowledge_text=knowledge_text,
        system_prompt=runtime.persona_realtime_prompt,
        prefer_main_tts=runtime.use_main_for_tts,
    )


async def run_realtime_chain(
    db: AsyncSession,
    session_id,
    text_input: str,
    message_id=None,
    synthesize_audio: bool = True,
    *,
    context_text: str = "No context",
    knowledge_text: str = "",
) -> ChainResult:
    runtime = await resolve_session_runtime(db, session_id)
    try:
        result = await run_realtime_chain_lcel(
            db=db,
            main_provider=runtime.realtime_main_provider,
            main_model=runtime.realtime_main_model,
            fallback_llm_provider=runtime.realtime_fallback_llm_provider,
            fallback_llm_model=runtime.realtime_fallback_llm_model,
            tts_provider=runtime.tts_provider,
            tts_model=runtime.tts_model,
            tts_voice=runtime.tts_voice,
            text_input=text_input,
            context_text=context_text,
            knowledge_text=knowledge_text,
            system_prompt=runtime.persona_realtime_prompt,
            synthesize_audio=synthesize_audio,
        )
        await _audit(
            db,
            session_id=session_id,
            mode="realtime",
            chain_name=result.chain_name,
            success=True,
            retries=0,
            fail_reason=result.fallback_reason,
            trace={
                **result.provider_trace,
                "pipeline": result.pipeline,
                "chain_name_hint": runtime.chain_name,
                "voice_used": result.voice_used,
                "latency_ms": result.latency_ms,
            },
            message_id=message_id,
        )
        return ChainResult(
            text=result.text,
            chain_name=result.chain_name,
            used_fallback=result.used_fallback,
            fail_reason=result.fallback_reason,
            audio_base64=result.audio_base64,
            audio_mime=result.audio_mime,
            fallback_reason=result.fallback_reason,
            pipeline=result.pipeline,
            voice_used=result.voice_used,
            provider_trace=result.provider_trace,
            latency_ms=result.latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        await _audit(
            db,
            session_id=session_id,
            mode="realtime",
            chain_name="realtime_voice_chain",
            success=False,
            retries=2,
            fail_reason=str(exc),
            trace={
                "main_provider": runtime.realtime_main_provider,
                "fallback_provider": runtime.realtime_fallback_llm_provider,
                "tts_provider": runtime.tts_provider,
                "chain_name_hint": runtime.chain_name,
                "pipeline": "realtime_voice_chain",
            },
            message_id=message_id,
        )
        raise


async def run_single_asr_with_trace(
    db: AsyncSession,
    audio_bytes: bytes,
    filename: str = "single_voice.wav",
    asr_provider: str | None = None,
    asr_model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    cfg = await ensure_default_call_config(db)
    provider = asr_provider or cfg.fallback_asr_provider
    model = asr_model or cfg.fallback_asr_model
    result = await run_single_voice_chain_lcel(
        db=db,
        asr_provider=provider,
        asr_model=model,
        audio_bytes=audio_bytes,
        filename=filename,
    )
    trace = {
        **result.provider_trace,
        "pipeline": result.pipeline,
        "fallback_reason": result.fallback_reason,
        "latency_ms": result.latency_ms,
    }
    return result.text, trace


async def run_single_asr(db: AsyncSession, audio_bytes: bytes, filename: str = "single_voice.wav") -> str:
    text, _trace = await run_single_asr_with_trace(db, audio_bytes, filename)
    return text
