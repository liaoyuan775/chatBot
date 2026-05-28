from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.provider_gateway import ProviderError, list_models_remote
from app.modules.chat.langchain_pipeline import probe_provider_chat_lcel


MODEL_TYPE_RULES: list[tuple[str, str]] = [
    ("sensevoice", "asr"),
    ("asr", "asr"),
    ("cosyvoice", "tts"),
    ("tts", "tts"),
    ("embedding", "embedding"),
    ("bge-m3", "embedding"),
    ("rerank", "rerank"),
    ("realtime", "llm"),
    ("deepseek", "llm"),
    ("qwen", "llm"),
    ("doubao", "llm"),
    ("seed", "llm"),
    ("flux", "image"),
    ("image", "image"),
]


CAPABILITY_RULES: list[tuple[str, set[str]]] = [
    ("omni", {"chat", "realtime", "audio_input", "audio_output", "asr", "tts"}),
    ("realtime", {"chat", "realtime", "audio_input", "audio_output", "asr", "tts"}),
    ("sensevoice", {"audio_input", "asr"}),
    ("asr", {"audio_input", "asr"}),
    ("cosyvoice", {"audio_output", "tts"}),
    ("tts", {"audio_output", "tts"}),
    ("deepseek", {"chat"}),
    ("qwen", {"chat"}),
    ("doubao", {"chat"}),
    ("seed", {"chat"}),
]


def infer_model_type(model_name: str) -> str:
    name = model_name.lower()
    for keyword, mtype in MODEL_TYPE_RULES:
        if keyword in name:
            return mtype
    return "llm"


def infer_model_capabilities(model_name: str, metadata: dict | None = None) -> list[str]:
    capabilities: set[str] = set()
    payload = metadata or {}
    raw = payload.get("capabilities") if isinstance(payload, dict) else None
    if isinstance(raw, list):
        capabilities.update(str(item).strip().lower() for item in raw if str(item).strip())
    name = (model_name or "").lower()
    for keyword, inferred in CAPABILITY_RULES:
        if keyword in name:
            capabilities.update(inferred)
    return sorted(capabilities)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
async def test_connectivity(db: AsyncSession, provider_name: str) -> tuple[bool, str]:
    try:
        models = await list_models_remote(db, provider_name)
        llm_candidate = ""
        for item in models:
            name = str(item.get("id") or item.get("model") or "")
            if infer_model_type(name) == "llm":
                llm_candidate = name
                break
        if llm_candidate:
            ok, probe_msg = await probe_provider_chat_lcel(
                db=db,
                provider_name=provider_name,
                model_name=llm_candidate,
            )
            if ok:
                return True, f"Connected ({datetime.now(timezone.utc).isoformat()}); models={len(models)}; {probe_msg}"
            return False, f"Connected model list but chat probe failed: {probe_msg}"
        return True, f"Connected ({datetime.now(timezone.utc).isoformat()}); models={len(models)}"
    except ProviderError as exc:
        return False, str(exc)
