from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, update

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.provider_gateway import encrypt_api_key
from app.models import CallConfigEntity, ChainConfigEntity, ModelCatalogEntity, ProviderConfigEntity

settings = get_settings()
BASELINE_MODELS = [
    ("dashscope", "qwen3.5-omni-plus-realtime", "llm", True),
    ("dashscope", "qwen-omni-turbo", "llm", True),
    ("dashscope", "qwen-plus", "llm", True),
    ("siliconflow", "FunAudioLLM/SenseVoiceSmall", "asr", True),
    ("volcengine", "doubao-seed-1-6-251015", "llm", True),
    ("siliconflow", settings.siliconflow_tts_model, "tts", True),
    ("siliconflow", "BAAI/bge-m3", "embedding", True),
    ("siliconflow", "BAAI/bge-reranker-v2-m3", "rerank", True),
    ("dashscope", "z-image-turbo", "image", True),
]


async def main() -> None:
    async with SessionLocal() as db:
        providers = [
            ("dashscope", settings.dashscope_base_url, settings.dashscope_api_key),
            ("volcengine", settings.volcengine_ark_base_url, settings.volcengine_ark_api_key),
            ("siliconflow", "https://api.siliconflow.cn", settings.siliconflow_api_key),
            ("openai", "https://api.openai.com/v1", getattr(settings, "openai_api_key", None)),
            ("glm", "https://open.bigmodel.cn/api/paas/v4", getattr(settings, "glm_api_key", None)),
            ("kimi", "https://api.moonshot.cn/v1", getattr(settings, "kimi_api_key", None)),
            ("minimax", "https://api.minimax.chat/v1", getattr(settings, "minimax_api_key", None)),
        ]
        provider_map: dict[str, ProviderConfigEntity] = {}
        for provider_name, base_url, api_key in providers:
            provider = await db.scalar(
                select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name)
            )
            if not provider:
                provider = ProviderConfigEntity(
                    provider_name=provider_name,
                    base_url=base_url,
                    timeout_seconds=20,
                    status="configured",
                )
                db.add(provider)
                await db.flush()
            else:
                provider.base_url = base_url or provider.base_url
                provider.timeout_seconds = provider.timeout_seconds or 20
            if api_key:
                await encrypt_api_key(db, provider.id, api_key)
            provider_map[provider_name] = provider

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
            if not row:
                db.add(
                    ModelCatalogEntity(
                        provider_id=provider.id,
                        model_name=model_name,
                        model_type=model_type,
                        is_enabled=is_enabled,
                        is_available=True,
                        metadata_json={"id": model_name, "seeded": True},
                    )
                )
            else:
                row.model_type = model_type
                row.is_enabled = is_enabled or row.is_enabled
                row.is_available = True
                if not row.metadata_json:
                    row.metadata_json = {"id": model_name, "seeded": True}

        call = await db.scalar(select(CallConfigEntity))
        if not call:
            call = CallConfigEntity()
            db.add(call)
        call.main_provider = "dashscope"
        call.main_model = "qwen3.5-omni-plus-realtime"
        call.fallback_asr_provider = "siliconflow"
        call.fallback_asr_model = "FunAudioLLM/SenseVoiceSmall"
        call.fallback_llm_provider = "volcengine"
        call.fallback_llm_model = "doubao-seed-1-6-251015"
        call.fallback_tts_provider = "siliconflow"
        call.fallback_tts_model = settings.siliconflow_tts_model
        call.fallback_tts_voice = settings.siliconflow_tts_voice

        main_chain = await db.scalar(select(ChainConfigEntity).where(ChainConfigEntity.name == "Main-Qwen-Omni"))
        if not main_chain:
            main_chain = ChainConfigEntity(name="Main-Qwen-Omni")
            db.add(main_chain)
        main_chain.is_default = True
        main_chain.is_valid = True
        main_chain.mapping_json = {"llm_model": "qwen3.5-omni-plus-realtime"}
        await db.execute(update(ChainConfigEntity).where(ChainConfigEntity.name != "Main-Qwen-Omni").values(is_default=False))

        fallback_chain = await db.scalar(select(ChainConfigEntity).where(ChainConfigEntity.name == "Fallback-SenseVoice-Seed-Cosy"))
        if not fallback_chain:
            db.add(
                ChainConfigEntity(
                    name="Fallback-SenseVoice-Seed-Cosy",
                    is_default=False,
                    is_valid=True,
                    mapping_json={
                        "asr_model": "FunAudioLLM/SenseVoiceSmall",
                        "llm_model": "doubao-seed-1-6-251015",
                        "tts_model": settings.siliconflow_tts_model,
                    },
                )
            )

        await db.commit()
    print("Default call config, baseline model catalog and chain templates are ready.")


if __name__ == "__main__":
    asyncio.run(main())
