from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SessionEntity(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(120), default="New Session")
    chain_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chains.id"))
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"))
    voice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("voices.id"))
    knowledge_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MessageEntity(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    content_type: Mapped[str] = mapped_column(String(32), default="text")
    text_content: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    replaced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionMemoryEntity(Base):
    __tablename__ = "session_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), unique=True)
    short_turns: Mapped[int] = mapped_column(Integer, default=6)
    mid_turns: Mapped[int] = mapped_column(Integer, default=8)
    long_turns: Mapped[int] = mapped_column(Integer, default=12)
    short_term: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    mid_summary: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LongTermMemoryEntity(Base):
    __tablename__ = "long_term_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    summary_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderConfigEntity(Base):
    __tablename__ = "provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_name: Mapped[str] = mapped_column(String(64), unique=True)
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(32), default="unverified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelCatalogEntity(Base):
    __tablename__ = "model_catalog"
    __table_args__ = (UniqueConstraint("provider_id", "model_name", name="uq_provider_model_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider_configs.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(128))
    model_type: Mapped[str] = mapped_column(String(32))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    alias: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PersonaEntity(Base):
    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VoiceProfileEntity(Base):
    __tablename__ = "voices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    voice_type: Mapped[str] = mapped_column(String(32), default="system")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    vector_ref: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChainConfigEntity(Base):
    __tablename__ = "chains"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id", ondelete="SET NULL"))
    voice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("voices.id", ondelete="SET NULL"))
    mapping_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeBaseEntity(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeDocumentEntity(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
    )
    file_name: Mapped[str] = mapped_column(String(200))
    file_type: Mapped[str] = mapped_column(String(16))
    parse_status: Mapped[str] = mapped_column(String(32), default="uploaded")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunkEntity(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(8))


class SystemSettingEntity(Base):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    setting_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CallConfigEntity(Base):
    __tablename__ = "call_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    main_provider: Mapped[str] = mapped_column(String(64), default="dashscope")
    main_model: Mapped[str] = mapped_column(String(128), default="qwen3.5-omni-plus-realtime")
    omni_mode: Mapped[str] = mapped_column(String(32), default="auto")
    fallback_asr_provider: Mapped[str] = mapped_column(String(64), default="siliconflow")
    fallback_asr_model: Mapped[str] = mapped_column(String(128), default="FunAudioLLM/SenseVoiceSmall")
    fallback_llm_provider: Mapped[str] = mapped_column(String(64), default="volcengine")
    fallback_llm_model: Mapped[str] = mapped_column(String(128), default="doubao-seed-1-6-251015")
    fallback_tts_provider: Mapped[str] = mapped_column(String(64), default="siliconflow")
    fallback_tts_model: Mapped[str] = mapped_column(String(128), default="FunAudioLLM/CosyVoice2-0.5B")
    fallback_tts_voice: Mapped[str] = mapped_column(String(128), default="FunAudioLLM/CosyVoice2-0.5B:alex")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SessionChainAuditEntity(Base):
    __tablename__ = "session_chain_audits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(32), default="text")
    chain_name: Mapped[str] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    fail_reason: Mapped[str | None] = mapped_column(Text)
    trace_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminUserEntity(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AdminSessionEntity(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    session_token_hash: Mapped[str] = mapped_column(Text, unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAuditLogEntity(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(160))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    detail_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
