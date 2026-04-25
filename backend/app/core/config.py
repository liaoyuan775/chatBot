from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Chinese Voice Chat Backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"], alias="CORS_ORIGINS")
    app_encryption_key: str = Field(default="replace_me", alias="APP_ENCRYPTION_KEY")

    database_url: str = Field(alias="DATABASE_URL")
    allowed_databases: str = Field(default="chatbot_dev,chatbot_prod", alias="ALLOWED_DATABASES")

    session_ttl_seconds: int = Field(default=3600, alias="SESSION_TTL_SECONDS")
    memory_window_turns: int = Field(default=6, alias="MEMORY_WINDOW_TURNS")
    simulation_enabled: bool = Field(default=False, alias="SIMULATION_ENABLED")

    volcengine_ark_api_key: str | None = Field(default=None, alias="VOLCENGINE_ARK_API_KEY")
    volcengine_ark_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", alias="VOLCENGINE_ARK_BASE_URL")
    volcengine_text_model: str = Field(default="doubao-seed-1-6-251015", alias="VOLCENGINE_TEXT_MODEL")

    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")
    dashscope_realtime_model: str = Field(default="qwen3.5-omni-plus-realtime", alias="DASHSCOPE_REALTIME_MODEL")
    dashscope_base_url: str = Field(default="https://dashscope.aliyuncs.com", alias="DASHSCOPE_BASE_URL")
    dashscope_tts_model: str = Field(default="cosyvoice-v3-flash", alias="DASHSCOPE_TTS_MODEL")
    dashscope_tts_voice: str = Field(default="longanyang", alias="DASHSCOPE_TTS_VOICE")

    siliconflow_api_key: str | None = Field(default=None, alias="SILICONFLOW_API_KEY")
    siliconflow_asr_model: str = Field(default="FunAudioLLM/SenseVoiceSmall", alias="SILICONFLOW_ASR_MODEL")
    siliconflow_tts_model: str = Field(default="FunAudioLLM/CosyVoice2-0.5B", alias="SILICONFLOW_TTS_MODEL")
    siliconflow_tts_voice: str = Field(default="FunAudioLLM/CosyVoice2-0.5B:alex", alias="SILICONFLOW_TTS_VOICE")
    siliconflow_embedding_model: str = Field(default="BAAI/bge-m3", alias="SILICONFLOW_EMBEDDING_MODEL")
    siliconflow_rerank_model: str = Field(default="BAAI/bge-reranker-v2-m3", alias="SILICONFLOW_RERANK_MODEL")

    @field_validator("database_url")
    @classmethod
    def validate_database_name(cls, value: str) -> str:
        parsed = urlparse(value)
        db_name = parsed.path.lstrip("/")
        if db_name in {"postgres", "template0", "template1", ""}:
            raise ValueError("DATABASE_URL must target chatbot_dev or chatbot_prod, never default postgres/template db.")
        return value

    def assert_database_allowed(self) -> None:
        parsed = urlparse(self.database_url)
        db_name = parsed.path.lstrip("/")
        allowed = {name.strip() for name in self.allowed_databases.split(",") if name.strip()}
        if db_name not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise ValueError(f"DATABASE_URL database `{db_name}` is not in ALLOWED_DATABASES ({allowed_text}).")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.assert_database_allowed()
    return settings
