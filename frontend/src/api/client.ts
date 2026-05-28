import axios from "axios";
import type {
  CallConfig,
  ChainConfig,
  ContextSnapshot,
  DatabaseStatus,
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeSwitch,
  MemoryConfig,
  Message,
  ModelRecord,
  Persona,
  Provider,
  RetrievalConfig,
  Session,
  Setting,
  VoiceProfile
} from "../types/domain";
import { emitToast } from "../store/toastBus";

function resolveApiBaseUrl() {
  const configured = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (configured) return configured;
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "http://127.0.0.1:8000";
}

const http = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 20000,
  withCredentials: true
});

const mutatingMethods = new Set(["post", "put", "patch", "delete"]);

http.interceptors.response.use(
  (response) => {
    const method = response.config.method?.toLowerCase() ?? "";
    const skipToast = Boolean((response.config.headers as Record<string, unknown> | undefined)?.["x-toast-skip"]);
    if (mutatingMethods.has(method) && !skipToast) {
      const message = typeof response.data?.message === "string" ? response.data.message : "操作成功";
      emitToast(message, "success");
    }
    return response;
  },
  (error) => {
    const method = error?.config?.method?.toLowerCase?.() ?? "";
    const skipToast = Boolean((error?.config?.headers as Record<string, unknown> | undefined)?.["x-toast-skip"]);
    if (mutatingMethods.has(method) && !skipToast) {
      const detail = error?.response?.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((item) => item?.msg).filter(Boolean).join("；")
            : "操作失败，请稍后重试。";
      emitToast(message, "error");
    }
    return Promise.reject(error);
  }
);

export const api = {
  listSessions: async () => (await http.get<Session[]>("/api/sessions")).data,
  getSession: async (sessionId: string) => (await http.get<Session>(`/api/sessions/${sessionId}`)).data,
  createSession: async (title = "新建会话") => (await http.post<{ id: string }>("/api/sessions", { title })).data,
  updateSession: async (sessionId: string, payload: Partial<Pick<Session, "title" | "chain_id" | "persona_id" | "voice_id" | "knowledge_enabled">>) =>
    (await http.patch(`/api/sessions/${sessionId}`, payload)).data,
  deleteSession: async (sessionId: string) => (await http.delete(`/api/sessions/${sessionId}`, { params: { confirm: true } })).data,
  batchDeleteSessions: async (sessionIds: string[]) =>
    (await http.post("/api/sessions/batch-delete", sessionIds, { params: { confirm: true } })).data,

  listMessages: async (sessionId: string) => (await http.get<Message[]>("/api/messages", { params: { session_id: sessionId } })).data,
  sendMessage: async (payload: { session_id: string; content_type: string; text_content?: string; image_url?: string }) =>
    (await http.post("/api/messages", payload)).data,
  streamMessage: async (
    payload: { session_id: string; content_type: string; text_content?: string; image_url?: string },
    handlers: {
      onChunk?: (chunk: {
        text?: string;
        audio_url?: string | null;
        audio_base64?: string;
        audio_mime?: string;
        image_url?: string | null;
        done?: boolean;
        error?: string | null;
        event?: string;
        turn_id?: string;
        metrics?: {
          context_latency_ms?: number;
          first_text_latency_ms?: number;
          first_audio_latency_ms?: number;
          retrieval_latency_ms?: number;
          llm_latency_ms?: number;
          tts_latency_ms?: number;
          total_latency_ms?: number;
        };
        retrieval?: {
          latency_ms?: number;
          hit_count?: number;
          decision?: string;
          reason?: string;
          timed_out?: boolean;
        };
      }) => void;
    },
    options?: { signal?: AbortSignal }
  ) => {
    const controller = new AbortController();
    const externalSignal = options?.signal;
    const onExternalAbort = () => controller.abort();
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort();
      else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
    const timeoutId = window.setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch(`${http.defaults.baseURL}/api/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
        credentials: "include"
      });
      if (response.status === 405) {
        const fallback = await http.post("/api/messages", payload, { headers: { "x-toast-skip": "1" } });
        const data = fallback.data as { assistant_reply?: string; assistant_audio_url?: string | null; message?: string };
        handlers.onChunk?.({ text: data.assistant_reply ?? "", done: true, audio_url: data.assistant_audio_url ?? null, error: null });
        return;
      }
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const data = await response.json() as { detail?: unknown };
          if (typeof data.detail === "string" && data.detail.trim()) detail = data.detail;
        } catch {
          try {
            const text = await response.text();
            if (text.trim()) detail = text.slice(0, 240);
          } catch {
            // ignore parsing failures
          }
        }
        throw new Error(detail);
      }
      if (!response.body) {
        throw new Error("流式响应为空");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          try {
            handlers.onChunk?.(JSON.parse(trimmed) as { text?: string; audio_url?: string | null; done?: boolean; error?: string | null });
          } catch {
            // skip malformed line and continue receiving subsequent chunks
          }
        }
      }
      if (buffer.trim()) {
        handlers.onChunk?.(JSON.parse(buffer.trim()) as { text?: string; audio_url?: string | null; done?: boolean; error?: string | null });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("请求超时，已取消发送，请重试。");
      }
      throw error;
    } finally {
      if (externalSignal) {
        externalSignal.removeEventListener("abort", onExternalAbort);
      }
      window.clearTimeout(timeoutId);
    }
  },
  sendAudioMessage: async (sessionId: string, file: Blob, filename: string) => {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file, filename);
    return (await http.post<{
      message: string;
      assistant_reply?: string;
      assistant_audio_url?: string | null;
      asr_text?: string;
      asr_success?: boolean;
      asr_error?: string | null;
      fallback_reason?: string | null;
      provider_trace?: Record<string, unknown>;
      pipeline?: string;
    }>("/api/messages/audio", form)).data;
  },
  transcribeAudio: async (sessionId: string, file: Blob, filename: string) => {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file, filename);
    return (
      await http.post<{
        asr_text: string;
        asr_success: boolean;
        asr_error?: string | null;
      }>("/api/messages/audio/transcribe", form)
    ).data;
  },
  editMessage: async (messageId: string, text_content: string) => (await http.patch(`/api/messages/${messageId}`, { text_content })).data,
  deleteMessage: async (messageId: string) => (await http.delete(`/api/messages/${messageId}`, { params: { confirm: true } })).data,
  regenerate: async (messageId: string) => (await http.post(`/api/messages/${messageId}/regenerate`)).data,

  getMemoryConfig: async () => (await http.get<MemoryConfig>("/api/context/config")).data,
  updateMemoryConfig: async (payload: MemoryConfig) => (await http.put("/api/context/config", payload)).data,
  getSessionContext: async (sessionId: string) => (await http.get<ContextSnapshot>(`/api/context/sessions/${sessionId}`)).data,
  clearSessionContext: async (sessionId: string) => (await http.post(`/api/context/sessions/${sessionId}/clear`)).data,
  compressSessionContext: async (sessionId: string) => (await http.post(`/api/context/sessions/${sessionId}/compress`)).data,
  exportSessionContext: async (sessionId: string) => (await http.get<{ file_name: string; content: string }>(`/api/context/sessions/${sessionId}/export`)).data,

  initCallConfig: async () => (await http.post("/api/call-config/init-defaults")).data,
  getCallConfig: async () => (await http.get<CallConfig>("/api/call-config")).data,
  updateCallConfig: async (payload: Omit<CallConfig, "id" | "updated_at">) => (await http.put("/api/call-config", payload)).data,
  adminLogin: async (payload: { username: string; password: string }) => (await http.post("/api/admin/auth/login", payload)).data,
  adminLogout: async () => (await http.post("/api/admin/auth/logout")).data,
  adminMe: async () => (await http.get<{ authenticated: boolean; user?: { id?: string; username?: string } }>("/api/admin/auth/me")).data,
  listAuditLogs: async () => (await http.get<Array<Record<string, unknown>>>("/api/admin/audit-logs")).data,
  getDiagnostics: async () => (await http.get<Record<string, unknown>>("/api/admin/ops/diagnostics")).data,

  listProviders: async () => (await http.get<Provider[]>("/api/providers")).data,
  listProviderTemplates: async () => (await http.get<Array<{ provider_name: string; base_url: string }>>("/api/providers/templates")).data,
  upsertProvider: async (provider: string, payload: { api_key?: string; base_url?: string; timeout_seconds: number }) =>
    (await http.put(`/api/providers/${provider}`, payload)).data,
  testProvider: async (provider: string) => (await http.post(`/api/providers/${provider}/test`)).data,
  syncProviderModels: async (provider: string) => (await http.post(`/api/providers/${provider}/sync-models`)).data,
  disableProvider: async (provider: string) => (await http.post(`/api/providers/${provider}/disable`)).data,
  deleteProvider: async (provider: string) => (await http.delete(`/api/providers/${provider}`)).data,

  listModels: async (params?: { model_type?: string; enabled?: boolean; provider_name?: string }) =>
    (await http.get<ModelRecord[]>("/api/models", { params })).data,
  getModelDetail: async (modelId: string) => (await http.get<ModelRecord>(`/api/models/${modelId}`)).data,
  updateModelStatus: async (modelId: string, is_enabled: boolean) =>
    (await http.patch(`/api/models/${modelId}/status`, { is_enabled })).data,
  batchUpdateModelStatus: async (model_ids: string[], is_enabled: boolean) =>
    (await http.post("/api/models/batch-status", { model_ids, is_enabled })).data,
  renameModel: async (modelId: string, alias: string) => (await http.patch(`/api/models/${modelId}/rename`, { alias })).data,

  listChains: async () => (await http.get<ChainConfig[]>("/api/chains")).data,
  createChain: async (payload: Record<string, unknown>) => (await http.post("/api/chains", payload)).data,
  updateChain: async (chainId: string, payload: Record<string, unknown>) => (await http.put(`/api/chains/${chainId}`, payload)).data,
  validateChain: async (id: string) =>
    (await http.post(`/api/chains/${id}/validate`, null, { headers: { "x-toast-skip": "1" } })).data,
  copyChain: async (id: string) => (await http.post(`/api/chains/${id}/copy`)).data,
  deleteChain: async (id: string) => (await http.delete(`/api/chains/${id}`)).data,

  listPersonas: async () => (await http.get<Persona[]>("/api/personas")).data,
  createPersona: async (payload: Record<string, unknown>) => (await http.post("/api/personas", payload)).data,
  updatePersona: async (personaId: string, payload: Record<string, unknown>) => (await http.put(`/api/personas/${personaId}`, payload)).data,
  copyPersona: async (personaId: string) => (await http.post(`/api/personas/${personaId}/copy`)).data,
  previewPersona: async (personaId: string, prompt: string) => (await http.post<{ reply: string }>(`/api/personas/${personaId}/preview`, { prompt }, { headers: { "x-toast-skip": "1" } })).data,
  deletePersona: async (personaId: string) => (await http.delete(`/api/personas/${personaId}`)).data,

  listVoices: async () => (await http.get<VoiceProfile[]>("/api/voices")).data,
  createVoice: async (payload: Record<string, unknown>) => (await http.post("/api/voices", payload)).data,
  updateVoice: async (voiceId: string, payload: Record<string, unknown>) => (await http.put(`/api/voices/${voiceId}`, payload)).data,
  cloneVoice: async (voiceId: string) => (await http.post(`/api/voices/${voiceId}/clone`)).data,
  uploadVoiceSample: async (
    voiceId: string,
    file: Blob,
    filename: string,
    source_type: "upload" | "record",
    options?: { clone?: boolean; reference_text?: string }
  ) => {
    const form = new FormData();
    form.append("file", file, filename);
    form.append("source_type", source_type);
    if (options?.clone !== undefined) form.append("clone", String(options.clone));
    if (options?.reference_text) form.append("reference_text", options.reference_text);
    return (
      await http.post<{ message: string; sample_source: string; clone_uri?: string; clone_error?: string; clone_reference_text?: string }>(
        `/api/voices/${voiceId}/sample`,
        form,
        { headers: { "x-toast-skip": "1" } }
      )
    ).data;
  },
  renameVoice: async (voiceId: string, name: string) => (await http.patch(`/api/voices/${voiceId}/rename`, { name })).data,
  previewVoice: async (voiceId: string, text: string) =>
    (await http.post<{ audio_base64: string; format: string; audio_mime?: string }>(`/api/voices/${voiceId}/preview`, { text })).data,
  deleteVoice: async (voiceId: string) => (await http.delete(`/api/voices/${voiceId}`)).data,

  listKnowledgeBases: async () => (await http.get<KnowledgeBase[]>("/api/knowledge/bases")).data,
  createKnowledgeBase: async (payload: { name: string; description?: string; is_default?: boolean }) =>
    (await http.post("/api/knowledge/bases", payload)).data,
  updateKnowledgeBase: async (knowledgeBaseId: string, payload: { name: string; description?: string; is_default?: boolean }) =>
    (await http.patch(`/api/knowledge/bases/${knowledgeBaseId}`, payload)).data,
  deleteKnowledgeBase: async (knowledgeBaseId: string) =>
    (await http.delete(`/api/knowledge/bases/${knowledgeBaseId}`)).data,
  listKnowledgeDocs: async (knowledge_base_id?: string) =>
    (await http.get<KnowledgeDocument[]>("/api/knowledge/documents", { params: { knowledge_base_id } })).data,
  deleteKnowledgeDoc: async (documentId: string) => (await http.delete(`/api/knowledge/documents/${documentId}`)).data,
  reparseKnowledgeDoc: async (documentId: string, chunk_size = 500, overlap = 80) => {
    const form = new FormData();
    form.append("chunk_size", String(chunk_size));
    form.append("overlap", String(overlap));
    return (await http.post(`/api/knowledge/documents/${documentId}/reparse`, form)).data;
  },
  createKnowledgeDoc: async (payload: { file: File; chunk_size?: number; overlap?: number; knowledge_base_id?: string }) => {
    const form = new FormData();
    form.append("file", payload.file);
    form.append("chunk_size", String(payload.chunk_size ?? 500));
    form.append("overlap", String(payload.overlap ?? 80));
    if (payload.knowledge_base_id) form.append("knowledge_base_id", payload.knowledge_base_id);
    return (await http.post("/api/knowledge/documents", form)).data;
  },
  retrievalTest: async (question: string, top_k?: number, similarity_threshold?: number, knowledge_base_id?: string) => {
    const form = new FormData();
    form.append("question", question);
    if (top_k !== undefined) form.append("top_k", String(top_k));
    if (similarity_threshold !== undefined) form.append("similarity_threshold", String(similarity_threshold));
    if (knowledge_base_id) form.append("knowledge_base_id", knowledge_base_id);
    return (await http.post("/api/knowledge/retrieval-test", form)).data;
  },
  getKnowledgeSwitch: async () => (await http.get<KnowledgeSwitch>("/api/knowledge/global-switch")).data,
  updateKnowledgeSwitch: async (enabled: boolean) =>
    (await http.put("/api/knowledge/global-switch", null, { params: { enabled } })).data,
  getRetrievalConfig: async () => (await http.get<RetrievalConfig>("/api/knowledge/retrieval-config")).data,
  updateRetrievalConfig: async (payload: RetrievalConfig) => (await http.put("/api/knowledge/retrieval-config", payload)).data,

  listSettings: async () => (await http.get<Setting[]>("/api/settings")).data,
  updateSetting: async (key: string, setting_value: Record<string, unknown>) =>
    (await http.put(`/api/settings/${key}`, { setting_value })).data,
  getDatabaseStatus: async () => (await http.get<DatabaseStatus>("/api/settings/database/status")).data,
  clearHistory: async () => (await http.post("/api/settings/data/clear-history", null, { params: { confirm: true } })).data,
  clearLongMemory: async () => (await http.post("/api/settings/data/clear-long-memory", null, { params: { confirm: true } })).data,
  clearKnowledgeVectors: async () => (await http.post("/api/settings/data/clear-knowledge-vectors", null, { params: { confirm: true } })).data,
  restoreDefaults: async () => (await http.post("/api/settings/restore-defaults")).data
};
