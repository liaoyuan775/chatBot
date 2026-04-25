from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "新建会话"


class SessionUpdate(BaseModel):
    title: str | None = None
    chain_id: uuid.UUID | None = None
    persona_id: uuid.UUID | None = None
    voice_id: uuid.UUID | None = None
    knowledge_enabled: bool | None = None


class MessageCreate(BaseModel):
    session_id: uuid.UUID
    content_type: str = "text"
    text_content: str | None = None
    image_url: str | None = None


class MessageEdit(BaseModel):
    text_content: str


class ProviderUpsert(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = 10


class ModelStatusUpdate(BaseModel):
    is_enabled: bool


class ModelRename(BaseModel):
    alias: str


class ModelBatchStatusUpdate(BaseModel):
    model_ids: list[uuid.UUID]
    is_enabled: bool


class ChainUpsert(BaseModel):
    name: str
    is_default: bool = False
    persona_id: uuid.UUID | None = None
    voice_id: uuid.UUID | None = None
    mapping_json: dict[str, Any] = Field(default_factory=dict)


class PersonaUpsert(BaseModel):
    name: str
    is_default: bool = False
    config_json: dict[str, Any] = Field(default_factory=dict)


class PersonaPreviewRequest(BaseModel):
    prompt: str


class VoiceUpsert(BaseModel):
    name: str
    voice_type: str = "system"
    is_default: bool = False
    is_enabled: bool = True
    config_json: dict[str, Any] = Field(default_factory=dict)


class VoiceRename(BaseModel):
    name: str


class VoicePreviewRequest(BaseModel):
    text: str = "Hello, this is a voice preview."


class MemoryConfigUpdate(BaseModel):
    short_turns: int = Field(ge=1, le=30)
    mid_turns: int = Field(ge=1, le=50)
    long_turns: int = Field(ge=1, le=80)


class SettingUpsert(BaseModel):
    setting_value: dict[str, Any]


class CallConfigUpsert(BaseModel):
    main_provider: str
    main_model: str
    omni_mode: str = "auto"
    fallback_asr_provider: str
    fallback_asr_model: str
    fallback_llm_provider: str
    fallback_llm_model: str
    fallback_tts_provider: str
    fallback_tts_model: str
    fallback_tts_voice: str


class RetrievalConfigUpsert(BaseModel):
    top_k: int = Field(default=3, ge=1, le=20)
    similarity_threshold: float = Field(default=0.0, ge=-1.0, le=1.0)
    rag_timeout_ms: int = Field(default=1500, ge=100, le=20000)
    no_result_message: str = "未查询到相关知识，我将为您进行通用解答。"
    embedding_provider: str = "siliconflow"
    embedding_model: str = "BAAI/bge-m3"
    rerank_provider: str = "siliconflow"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
