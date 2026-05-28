export type Session = {
  id: string;
  title: string;
  status: string;
  knowledge_enabled: boolean;
  chain_id?: string | null;
  persona_id?: string | null;
  voice_id?: string | null;
  chain_name?: string;
  persona_name?: string;
  voice_name?: string;
  summary?: string;
  created_at: string;
  updated_at?: string;
};

export type Message = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content_type: "text" | "image" | "audio" | "generated_image";
  text_content?: string | null;
  image_url?: string | null;
  audio_url?: string | null;
  has_audio?: boolean;
  metadata_json?: Record<string, unknown>;
  replaced: boolean;
  created_at: string;
};

export type ContextSnapshot = {
  short_term: Array<Record<string, unknown>>;
  mid_summary: Array<Record<string, unknown>>;
  long_count: number;
};

export type MemoryConfig = {
  short_turns: number;
  mid_turns: number;
  long_turns: number;
};

export type Provider = {
  id: string;
  provider_name: string;
  base_url?: string;
  timeout_seconds: number;
  status: string;
  api_key_masked?: string | null;
  has_api_key?: boolean;
  updated_at?: string;
};

export type ModelRecord = {
  id: string;
  provider_name: string;
  model_name: string;
  model_type: string;
  is_enabled: boolean;
  is_available: boolean;
  alias?: string | null;
  metadata_json?: Record<string, unknown>;
};

export type ChainConfig = {
  id: string;
  name: string;
  is_default: boolean;
  persona_id?: string | null;
  voice_id?: string | null;
  mapping_json: Record<string, string>;
  is_valid: boolean;
  chain_mode?: "integrated" | "split";
  chain_summary?: string;
  updated_at?: string;
};

export type Persona = {
  id: string;
  name: string;
  is_default: boolean;
  config_json: Record<string, unknown>;
  created_at?: string;
};

export type VoiceProfile = {
  id: string;
  name: string;
  voice_type: string;
  is_default: boolean;
  is_enabled: boolean;
  config_json: Record<string, unknown>;
  created_at?: string;
};

export type KnowledgeDocument = {
  id: string;
  knowledge_base_id?: string | null;
  knowledge_base_name?: string;
  file_name: string;
  file_type: string;
  parse_status: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
};

export type KnowledgeSwitch = {
  enabled: boolean;
};

export type RetrievalConfig = {
  top_k: number;
  similarity_threshold: number;
  rag_timeout_ms: number;
  no_result_message: string;
  embedding_provider: string;
  embedding_model: string;
  rerank_provider: string;
  rerank_model: string;
};

export type Setting = {
  setting_key: string;
  setting_value: Record<string, unknown>;
  updated_at?: string;
};

export type DatabaseStatus = {
  status: string;
  reason?: string;
};

export type CallConfig = {
  id: string;
  main_provider: string;
  main_model: string;
  omni_mode: string;
  fallback_asr_provider: string;
  fallback_asr_model: string;
  fallback_llm_provider: string;
  fallback_llm_model: string;
  fallback_tts_provider: string;
  fallback_tts_model: string;
  fallback_tts_voice: string;
  updated_at: string;
};
