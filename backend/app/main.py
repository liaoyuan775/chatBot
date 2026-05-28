from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.logging import configure_logging
from app.core.provider_gateway import encrypt_api_key
from app.models import Base, ProviderConfigEntity
from app.modules.admin_auth.middleware import AdminAuthMiddleware
from app.modules.admin_auth.router import router as admin_router
from app.modules.admin_auth.service import cleanup_expired_admin_sessions, ensure_default_admin
from app.modules.chat.engine import ensure_default_call_config
from app.modules.ops.router import router as ops_router
from app.modules.call_config.router import router as call_config_router
from app.modules.chain_config.router import router as chain_router
from app.modules.chat.router import router as chat_router
from app.modules.context_memory.router import router as context_router
from app.modules.knowledge_rag.router import router as knowledge_router
from app.modules.model_catalog.router import router as model_router
from app.modules.persona.router import router as persona_router
from app.modules.provider_registry.router import router as provider_router
from app.modules.realtime_ws.router import router as realtime_router
from app.modules.system_settings.router import router as settings_router
from app.modules.voice.router import router as voice_router

configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AdminAuthMiddleware)

app.include_router(chat_router)
app.include_router(call_config_router)
app.include_router(context_router)
app.include_router(provider_router)
app.include_router(model_router)
app.include_router(chain_router)
app.include_router(persona_router)
app.include_router(voice_router)
app.include_router(knowledge_router)
app.include_router(settings_router)
app.include_router(realtime_router)
app.include_router(admin_router)
app.include_router(ops_router)


@app.on_event("startup")
async def bootstrap_runtime_defaults() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        providers = [
            ("dashscope", settings.dashscope_base_url, settings.dashscope_api_key),
            ("deepseek", "https://api.deepseek.com", getattr(settings, "deepseek_api_key", None)),
            ("volcengine", settings.volcengine_ark_base_url, settings.volcengine_ark_api_key),
            ("siliconflow", "https://api.siliconflow.cn", settings.siliconflow_api_key),
        ]
        await ensure_default_admin(db)
        for provider_name, base_url, api_key in providers:
            row = await db.scalar(
                select(ProviderConfigEntity).where(ProviderConfigEntity.provider_name == provider_name)
            )
            if not row:
                row = ProviderConfigEntity(
                    provider_name=provider_name,
                    base_url=base_url,
                    timeout_seconds=20,
                    status="configured",
                )
                db.add(row)
                await db.flush()
            else:
                if base_url:
                    row.base_url = base_url
                row.timeout_seconds = row.timeout_seconds or 20
                if row.status == "unverified":
                    row.status = "configured"
            if api_key:
                await encrypt_api_key(db, row.id, api_key)
        await db.commit()
        await ensure_default_call_config(db)
        await cleanup_expired_admin_sessions(db)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz")
async def readyz():
    async with SessionLocal() as db:
        provider_count = len((await db.scalars(select(ProviderConfigEntity))).all())
    return {"status": "ready", "provider_count": provider_count, "service": settings.app_name}
