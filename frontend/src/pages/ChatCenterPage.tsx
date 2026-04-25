import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { AudioMessagePlayer } from "../components/AudioMessagePlayer";
import { SessionRuntime, type RuntimeEvent, type StudioState, type VoiceMode } from "../runtime/voice";
import { PcmStreamPlayer } from "../runtime/voice/pcmStreamPlayer";
import { useChatStore } from "../store/chatStore";
import { emitToast } from "../store/toastBus";
import type { Message, Persona, Session } from "../types/domain";

type VoiceFeature = "voice-input" | "realtime-call" | null;

function stateLabel(state: StudioState) {
  if (state === "listening") return "监听中";
  if (state === "thinking") return "思考中";
  if (state === "speaking") return "播报中";
  if (state === "error") return "异常";
  return "待机";
}

function resolveChainMode(value: unknown): VoiceMode {
  return value === "split-chain" ? "split-chain" : "integrated-realtime";
}

function upsertMessages(current: unknown, incoming: Message | Message[]) {
  const rows = Array.isArray(current) ? ([...current] as Message[]) : [];
  for (const message of Array.isArray(incoming) ? incoming : [incoming]) {
    const idx = rows.findIndex((item) => item.id === message.id);
    if (idx >= 0) rows[idx] = message;
    else rows.push(message);
  }
  rows.sort((a, b) => a.created_at.localeCompare(b.created_at));
  return rows;
}

function optimisticUserMessage(sessionId: string, text: string): Message {
  return {
    id: `local-user-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    session_id: sessionId,
    role: "user",
    content_type: "text",
    text_content: text,
    image_url: null,
    audio_url: null,
    metadata_json: { optimistic: true },
    replaced: false,
    created_at: new Date().toISOString()
  };
}

export function ChatCenterPage() {
  const queryClient = useQueryClient();
  const {
    activeSessionId,
    setActiveSessionId,
    inputText,
    setInputText,
    setRealtimeEnabled,
    setVoiceMode,
    setStudioState: setStoreStudioState,
    setRuntimeMetrics,
    setTurnDraft,
    turnDraft
  } = useChatStore();

  const runtimeRef = useRef<SessionRuntime | null>(null);
  const assistantAudioRef = useRef<HTMLAudioElement | null>(null);
  const assistantPcmPlayerRef = useRef<PcmStreamPlayer | null>(null);
  const assistantAudioQueueRef = useRef<Array<{ mime: string; base64: string }>>([]);
  const assistantAudioPlayingRef = useRef(false);
  const [mode, setMode] = useState<VoiceMode>("integrated-realtime");
  const [listening, setListening] = useState(false);
  const [studioState, setStudioState] = useState<StudioState>("idle");
  const [voiceStatus, setVoiceStatus] = useState("待机");
  const [transcript, setTranscript] = useState("");
  const [metric, setMetric] = useState("-");
  const [retrievalStatus, setRetrievalStatus] = useState("未执行");
  const [isComposing, setIsComposing] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [activeVoiceFeature, setActiveVoiceFeature] = useState<VoiceFeature>(null);

  const sessionsQuery = useQuery({ queryKey: ["sessions"], queryFn: api.listSessions });
  const chainsQuery = useQuery({ queryKey: ["chains"], queryFn: api.listChains });
  const personasQuery = useQuery({ queryKey: ["personas"], queryFn: api.listPersonas });
  const messagesQuery = useQuery({
    queryKey: ["messages", activeSessionId],
    queryFn: () => api.listMessages(activeSessionId!),
    enabled: Boolean(activeSessionId)
  });

  const sessions = sessionsQuery.data ?? [];
  const chains = chainsQuery.data ?? [];
  const personas = personasQuery.data ?? [];
  const messages = messagesQuery.data ?? [];

  const activeSession = useMemo<Session | undefined>(
    () => sessions.find((session) => session.id === activeSessionId),
    [sessions, activeSessionId]
  );
  const activeChain = useMemo(
    () => chains.find((chain) => chain.id === activeSession?.chain_id),
    [chains, activeSession?.chain_id]
  );
  const chainRuntimeMode = resolveChainMode(activeChain?.mapping_json?.voice_runtime_mode);
  const allSessionIds = sessions.map((session) => session.id);
  const allSelected = allSessionIds.length > 0 && allSessionIds.every((id) => selectedSessionIds.includes(id));

  useEffect(() => {
    if (!assistantPcmPlayerRef.current) {
      assistantPcmPlayerRef.current = new PcmStreamPlayer();
    }
    if (runtimeRef.current) return;
    runtimeRef.current = new SessionRuntime(
      {
        sendTextTurn: async ({ sessionId, text, onDelta, signal }) => {
          await api.streamMessage(
            { session_id: sessionId, content_type: "text", text_content: text },
            { onChunk: onDelta },
            { signal }
          );
          await queryClient.invalidateQueries({ queryKey: ["messages", sessionId] });
          await queryClient.invalidateQueries({ queryKey: ["sessions"] });
        },
        transcribeAudio: async ({ sessionId, blob, filename }) => {
          const result = await api.transcribeAudio(sessionId, blob, filename);
          if (!result.asr_success) throw new Error(result.asr_error || "语音识别失败");
          return result.asr_text;
        }
      },
      { mode: "integrated-realtime", splitAsr: "auto", feature: "realtime-call", autoSubmitVoiceTurns: true }
    );
    return () => {
      void assistantPcmPlayerRef.current?.close();
      assistantPcmPlayerRef.current = null;
      void runtimeRef.current?.destroy();
      runtimeRef.current = null;
    };
  }, [queryClient]);

  useEffect(() => {
    if (!sessions.length) return;
    if (!activeSessionId || !sessions.some((session) => session.id === activeSessionId)) {
      setActiveSessionId(sessions[0].id);
    }
  }, [activeSessionId, sessions, setActiveSessionId]);

  useEffect(() => {
    setSelectedSessionIds((current) => {
      const next = current.filter((id) => sessions.some((session) => session.id === id));
      return next.length === current.length ? current : next;
    });
  }, [sessions]);

  useEffect(() => {
    runtimeRef.current?.setSession(activeSessionId);
  }, [activeSessionId]);

  useEffect(() => {
    setRetrievalStatus("未执行");
  }, [activeSessionId]);

  const stopAssistantAudio = () => {
    assistantAudioRef.current?.pause();
    assistantAudioRef.current = null;
    assistantPcmPlayerRef.current?.stop();
    assistantAudioQueueRef.current = [];
    assistantAudioPlayingRef.current = false;
  };

  const playNextAssistantAudio = () => {
    if (assistantAudioPlayingRef.current) return;
    const next = assistantAudioQueueRef.current.shift();
    if (!next) return;
    assistantAudioPlayingRef.current = true;
    const audio = new Audio(`data:${next.mime};base64,${next.base64}`);
    assistantAudioRef.current = audio;
    audio.onended = () => {
      assistantAudioPlayingRef.current = false;
      assistantAudioRef.current = null;
      playNextAssistantAudio();
    };
    audio.onerror = () => {
      assistantAudioPlayingRef.current = false;
      assistantAudioRef.current = null;
      playNextAssistantAudio();
    };
    void audio.play().catch(() => {
      assistantAudioPlayingRef.current = false;
      assistantAudioRef.current = null;
      playNextAssistantAudio();
    });
  };

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    const off = runtime.onEvent((event: RuntimeEvent) => {
      if (event.type === "session.state.changed") {
        setStudioState(event.payload.state);
        setStoreStudioState(event.payload.state);
        if (event.payload.reason) setVoiceStatus(event.payload.reason);
      }
      if (event.type === "session.error") {
        setVoiceStatus(event.payload.message);
        setStudioState("error");
        setStoreStudioState("error");
        emitToast(event.payload.message || "实时会话异常", "error");
      }
      if (event.type === "user.transcript.partial" || event.type === "user.transcript.final") {
        stopAssistantAudio();
        setTranscript(event.payload.text);
        if (activeVoiceFeature !== "voice-input") {
          setTurnDraft({ userText: event.payload.text, assistantText: "" });
        }
      }
      if (event.type === "assistant.text.delta" || event.type === "assistant.text.final") {
        setTurnDraft({ userText: turnDraft.userText, assistantText: event.payload.text });
      }
      if (event.type === "metrics.turn") {
        const c = event.payload.context_latency_ms ?? "-";
        const t = event.payload.first_text_latency_ms ?? "-";
        const a = event.payload.first_audio_latency_ms ?? "-";
        const i = event.payload.interrupt_latency_ms ?? "-";
        const l = event.payload.llm_latency_ms ?? "-";
        const s = event.payload.tts_latency_ms ?? "-";
        const total = event.payload.total_latency_ms ?? "-";
        setMetric(`${retrievalStatus} / 上下文 ${c}ms / 首字 ${t}ms / 首音 ${a}ms / LLM ${l}ms / TTS ${s}ms / 总耗时 ${total}ms / 打断 ${i}ms`);
        setRuntimeMetrics({
          turnId: event.payload.turn_id,
          contextLatencyMs: event.payload.context_latency_ms,
          firstTextLatencyMs: event.payload.first_text_latency_ms,
          firstAudioLatencyMs: event.payload.first_audio_latency_ms,
          interruptLatencyMs: event.payload.interrupt_latency_ms,
          retrievalLatencyMs: event.payload.retrieval_latency_ms,
          llmLatencyMs: event.payload.llm_latency_ms,
          ttsLatencyMs: event.payload.tts_latency_ms,
          totalLatencyMs: event.payload.total_latency_ms
        });
        if (activeSessionId) {
          void queryClient.invalidateQueries({ queryKey: ["messages", activeSessionId] });
        }
      }
      if (event.type === "metrics.retrieval") {
        const decision = event.payload.decision ?? "unknown";
        if (decision === "retrieve") {
          if (event.payload.timed_out || event.payload.reason === "retrieval_timeout") {
            setRetrievalStatus(`检索超时 ${event.payload.latency_ms ?? "-"}ms / 已降级直答`);
          } else if (event.payload.reason === "retrieval_provider_error") {
            setRetrievalStatus(`检索失败 ${event.payload.latency_ms ?? "-"}ms / 已降级直答`);
          } else if (event.payload.reason === "retrieval_no_hit") {
            setRetrievalStatus(`检索未命中 ${event.payload.latency_ms ?? "-"}ms`);
          } else {
            setRetrievalStatus(`检索 ${event.payload.latency_ms ?? "-"}ms / 命中 ${event.payload.hit_count ?? 0}`);
          }
        } else {
          setRetrievalStatus(`检索已跳过 (${event.payload.reason ?? "unknown"})`);
        }
      }
      if (event.type === "assistant.audio.delta") {
        const mime = event.payload.audio_mime || "audio/mpeg";
        if (mime.startsWith("audio/pcm")) {
          assistantAudioRef.current?.pause();
          const match = mime.match(/rate=(\d+)/i);
          const sampleRate = match ? Number(match[1]) : 24000;
          void assistantPcmPlayerRef.current?.enqueue(event.payload.audio_base64, sampleRate);
        } else {
          assistantPcmPlayerRef.current?.stop();
          assistantAudioQueueRef.current.push({ mime, base64: event.payload.audio_base64 });
          playNextAssistantAudio();
        }
      }
      if (event.type === "assistant.interrupted") {
        stopAssistantAudio();
      }
      if (event.type === "session.updated" && activeSessionId && event.payload.session_id === activeSessionId) {
        if (event.payload.message) {
          queryClient.setQueryData(["messages", activeSessionId], (current: unknown) =>
            upsertMessages(current, event.payload.message as Message)
          );
        }
        if (Array.isArray(event.payload.messages)) {
          queryClient.setQueryData(["messages", activeSessionId], (current: unknown) =>
            upsertMessages(current, event.payload.messages as Message[])
          );
        }
      }
    });
    return off;
  }, [activeSessionId, activeVoiceFeature, queryClient, retrievalStatus, setRuntimeMetrics, setStoreStudioState, setTurnDraft, turnDraft.userText]);

  const createSessionMutation = useMutation({
    mutationFn: () => api.createSession("新建会话"),
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      setActiveSessionId(data.id);
    }
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: string) => api.deleteSession(sessionId),
    onSuccess: async (_, deletedId) => {
      if (deletedId === activeSessionId) {
        await runtimeRef.current?.stopListening();
        setListening(false);
        setActiveVoiceFeature(null);
      }
      setSelectedSessionIds((current) => current.filter((id) => id !== deletedId));
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      await queryClient.invalidateQueries({ queryKey: ["messages"] });
    }
  });

  const batchDeleteMutation = useMutation({
    mutationFn: (sessionIds: string[]) => api.batchDeleteSessions(sessionIds),
    onSuccess: async (_, deletedIds) => {
      if (activeSessionId && deletedIds.includes(activeSessionId)) {
        await runtimeRef.current?.stopListening();
        setListening(false);
        setActiveVoiceFeature(null);
      }
      setSelectedSessionIds([]);
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      await queryClient.invalidateQueries({ queryKey: ["messages"] });
    }
  });

  const refreshListeningRuntime = async (
    nextFeature: Exclude<VoiceFeature, null>,
    nextMode: VoiceMode,
    forceRestart = false
  ) => {
    if (!runtimeRef.current || !activeSessionId || !listening) return;
    if (!forceRestart && nextMode === "integrated-realtime") {
      runtimeRef.current.applyLiveConfig({
        mode: nextMode,
        splitAsr: "auto",
        feature: nextFeature,
        autoSubmitVoiceTurns: nextFeature === "realtime-call"
      });
      runtimeRef.current.setSession(activeSessionId);
      await runtimeRef.current.startListening();
      setMode(nextMode);
      setVoiceMode(nextMode);
      return;
    }
    await stopVoice();
    await startVoiceFeature(nextFeature);
  };

  const updateSessionMutation = useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: string; payload: Partial<Pick<Session, "chain_id" | "persona_id" | "voice_id" | "knowledge_enabled">> }) =>
      api.updateSession(sessionId, payload),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      if (
        variables.sessionId === activeSessionId &&
        activeVoiceFeature &&
        listening
      ) {
        const forceRestart = Object.prototype.hasOwnProperty.call(variables.payload, "chain_id");
        const nextMode =
          typeof variables.payload.chain_id === "string"
            ? resolveChainMode(chains.find((chain) => chain.id === variables.payload.chain_id)?.mapping_json?.voice_runtime_mode)
            : chainRuntimeMode;
        await refreshListeningRuntime(activeVoiceFeature, nextMode, forceRestart);
      }
    }
  });

  const sendMutation = useMutation({
    mutationFn: async ({ text, sessionId }: { text: string; sessionId: string }) => {
      if (!sessionId) return;
      runtimeRef.current?.setSession(sessionId);
      await runtimeRef.current?.sendTextTurn(text);
    },
    onError: async () => {
      if (activeSessionId) {
        await queryClient.invalidateQueries({ queryKey: ["messages", activeSessionId] });
      }
    }
  });

  const stopVoice = async () => {
    if (!runtimeRef.current) return;
    stopAssistantAudio();
    await runtimeRef.current.stopListening();
    if (activeVoiceFeature === "voice-input") {
      const finalTranscript = runtimeRef.current.getSnapshot().transcript.trim();
      if (finalTranscript) {
        setInputText(finalTranscript);
      }
    }
    setListening(false);
    setRealtimeEnabled(false);
    setVoiceStatus("语音已关闭");
    setStudioState("idle");
    setStoreStudioState("idle");
    setActiveVoiceFeature(null);
    setTurnDraft({});
  };

  const startVoiceFeature = async (feature: Exclude<VoiceFeature, null>) => {
    if (!runtimeRef.current || !activeSessionId) return;
    if (listening && activeVoiceFeature && activeVoiceFeature !== feature) {
      await stopVoice();
    }
    runtimeRef.current.applyLiveConfig({
      mode: chainRuntimeMode,
      splitAsr: "auto",
      feature,
      autoSubmitVoiceTurns: feature === "realtime-call"
    });
    runtimeRef.current.setSession(activeSessionId);
    await runtimeRef.current.startListening();
    setMode(chainRuntimeMode);
    setVoiceMode(chainRuntimeMode);
    setListening(true);
    setRealtimeEnabled(true);
    setActiveVoiceFeature(feature);
    setTranscript("");
    setRetrievalStatus("未执行");
    setTurnDraft({});
    if (feature === "voice-input") {
      setVoiceStatus(`语音输入已开启（链路模式：${chainRuntimeMode}）`);
    } else {
      setVoiceStatus(`实时通话已开启（链路模式：${chainRuntimeMode}）`);
    }
  };

  const interruptVoice = async () => {
    if (!runtimeRef.current) return;
    stopAssistantAudio();
    await runtimeRef.current.interruptCurrentReply();
    setVoiceStatus("已打断当前回复");
  };

  const sendTextNow = () => {
    const text = inputText.trim();
    const sessionId = activeSessionId;
    if (!text || sendMutation.isPending || !sessionId) return;
    setRetrievalStatus("未执行");
    queryClient.setQueryData(["messages", sessionId], (current: unknown) =>
      upsertMessages(current, optimisticUserMessage(sessionId, text))
    );
    setTurnDraft({});
    setInputText("");
    sendMutation.mutate({ text, sessionId });
  };

  const toggleSessionSelection = (sessionId: string) => {
    setSelectedSessionIds((current) =>
      current.includes(sessionId) ? current.filter((item) => item !== sessionId) : [...current, sessionId]
    );
  };

  const toggleSelectAll = () => {
    setSelectedSessionIds(allSelected ? [] : allSessionIds);
  };

  const batchDeleteSessions = () => {
    if (!selectedSessionIds.length || batchDeleteMutation.isPending) return;
    if (window.confirm(`确认删除 ${selectedSessionIds.length} 个会话吗？`)) {
      batchDeleteMutation.mutate(selectedSessionIds);
    }
  };

  const displayMessages = useMemo(() => {
    const rows = [...messages];
    const allowDraftMessages = activeVoiceFeature !== "voice-input";
    const latestUserText = [...rows].reverse().find((message) => message.role === "user")?.text_content?.trim() ?? "";
    const latestAssistantText =
      [...rows].reverse().find((message) => message.role === "assistant")?.text_content?.trim() ?? "";
    if (allowDraftMessages && turnDraft.userText?.trim() && latestUserText !== turnDraft.userText.trim()) {
      rows.push({
        id: "draft-user",
        session_id: activeSessionId ?? "",
        role: "user",
        content_type: "text",
        text_content: turnDraft.userText,
        image_url: null,
        audio_url: null,
        metadata_json: { draft: true },
        replaced: false,
        created_at: new Date().toISOString()
      });
    }
    if (allowDraftMessages && turnDraft.assistantText?.trim() && latestAssistantText !== turnDraft.assistantText.trim()) {
      rows.push({
        id: "draft-assistant",
        session_id: activeSessionId ?? "",
        role: "assistant",
        content_type: "text",
        text_content: turnDraft.assistantText,
        image_url: null,
        audio_url: null,
        metadata_json: { draft: true },
        replaced: false,
        created_at: new Date().toISOString()
      });
    }
    return rows;
  }, [activeSessionId, activeVoiceFeature, messages, turnDraft.assistantText, turnDraft.userText]);

  return (
    <section className="chat-mode-shell fade-up">
      <div className="grid h-full gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="chat-left-col space-y-4">
          <div className="soft-card p-4 space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--ink)]">监控面板</h3>
              <span className="info-chip">{activeSession?.status ?? "未选中"}</span>
            </div>
            <div>状态: {listening ? `${stateLabel(studioState)} / ${voiceStatus}` : "未开启"}</div>
            <div>当前链路模式: {chainRuntimeMode}</div>
            <div>运行模式: {mode}</div>
            <div>知识库: {activeSession?.knowledge_enabled ? "当前会话已开启" : "当前会话已关闭"}</div>
            <div>实时转写: {transcript || "-"}</div>
            <div>本轮指标: {metric}</div>
            <label className="text-xs text-[var(--muted)]">
              绑定链路
              <select
                className="field-input mt-1"
                value={activeSession?.chain_id ?? ""}
                disabled={!activeSessionId}
                onChange={(e) =>
                  activeSessionId &&
                  updateSessionMutation.mutate({
                    sessionId: activeSessionId,
                    payload: { chain_id: e.target.value || null }
                  })
                }
              >
                <option value="">未绑定</option>
                {chains.map((chain) => (
                  <option key={chain.id} value={chain.id}>
                    {chain.name} ({resolveChainMode(chain.mapping_json?.voice_runtime_mode)})
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-[var(--muted)]">
              当前人格
              <select
                className="field-input mt-1"
                value={activeSession?.persona_id ?? ""}
                disabled={!activeSessionId}
                onChange={(e) =>
                  activeSessionId &&
                  updateSessionMutation.mutate({
                    sessionId: activeSessionId,
                    payload: { persona_id: e.target.value || null }
                  })
                }
              >
                <option value="">未绑定</option>
                {personas.map((persona: Persona) => (
                  <option key={persona.id} value={persona.id}>
                    {persona.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center justify-between rounded-lg border border-[var(--line)] bg-white/70 px-3 py-2 text-xs text-[var(--muted)]">
              <span>当前会话启用知识库</span>
              <input
                type="checkbox"
                checked={Boolean(activeSession?.knowledge_enabled)}
                disabled={!activeSessionId}
                onChange={(e) =>
                  activeSessionId &&
                  updateSessionMutation.mutate({
                    sessionId: activeSessionId,
                    payload: { knowledge_enabled: e.target.checked }
                  })
                }
              />
            </label>
	          </div>

          <div className="soft-card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--ink)]">历史会话</h3>
              <button className="action-btn action-btn-primary" onClick={() => createSessionMutation.mutate()}>
                新建
              </button>
            </div>
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="info-chip">已选 {selectedSessionIds.length}</span>
              <div className="flex gap-2">
                <button className="action-btn action-btn-secondary" onClick={toggleSelectAll} disabled={!sessions.length}>
                  {allSelected ? "清空选择" : "全选"}
                </button>
                <button
                  className="action-btn action-btn-danger"
                  disabled={!selectedSessionIds.length || batchDeleteMutation.isPending}
                  onClick={batchDeleteSessions}
                >
                  批量删除
                </button>
              </div>
            </div>
            <div className="space-y-2 max-h-[34vh] overflow-auto pr-1">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className={`rounded-lg border px-3 py-2 ${
                    session.id === activeSessionId
                      ? "border-[var(--primary)] bg-[var(--primary-soft)]/40"
                      : "border-[var(--line)] bg-white/90"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <label className="flex items-start gap-2">
                      <input
                        className="mt-1"
                        type="checkbox"
                        checked={selectedSessionIds.includes(session.id)}
                        onChange={() => toggleSessionSelection(session.id)}
                      />
                      <button className="text-left" onClick={() => setActiveSessionId(session.id)}>
                        <div className="text-sm font-semibold">{session.title}</div>
                        <div className="text-xs text-[var(--muted)]">{session.summary || "暂无摘要"}</div>
                      </button>
                    </label>
                    <button
                      className="rounded-full border border-[var(--line)] px-2 py-1 text-xs text-[var(--danger)]"
                      onClick={() => {
                        if (window.confirm("确认删除该会话吗？")) {
                          deleteSessionMutation.mutate(session.id);
                        }
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>

        <div className="chat-right-col soft-card-strong h-full overflow-hidden">
          <div className="chat-history scroll-area h-full overflow-y-auto px-4 pb-5 pt-4 md:px-6">
            <div className="space-y-3">
              {displayMessages.map((message) => (
                <article
                  key={message.id}
                  className={`max-w-[66%] rounded-xl border px-2.5 py-1.5 text-[12px] leading-5 ${
                    message.role === "user"
                      ? "ml-auto border-[#cfe3df] bg-[#eff8f6]"
                      : "mr-auto border-[#d9e5eb] bg-[#f8fbfd]"
                  }`}
                >
                  <div className="mb-1 text-[10px] text-[var(--muted)]">{message.role === "user" ? "用户" : "助手"}</div>
                  {message.text_content ? <p className="whitespace-pre-wrap">{message.text_content}</p> : null}
                  {message.image_url ? (
                    <img className="mt-2 max-h-[320px] w-full rounded-lg border border-[var(--line)] object-cover" src={message.image_url} alt="generated" />
                  ) : null}
                  {message.audio_url ? <AudioMessagePlayer className="mt-2" src={message.audio_url} /> : null}
                </article>
              ))}
            </div>
          </div>

          <div className="chat-composer-inline">
            <div className="chat-composer-shell chat-composer-shell-inline">
              <div className="chat-triad-row">
                <button className="chat-triad-btn chat-triad-btn-active">文本输入</button>
                <button
                  className={`chat-triad-btn ${activeVoiceFeature === "voice-input" ? "chat-triad-btn-danger" : ""}`}
                  disabled={!activeSessionId}
                  onClick={() =>
                    activeVoiceFeature === "voice-input" ? void stopVoice() : void startVoiceFeature("voice-input")
                  }
                >
                  {activeVoiceFeature === "voice-input" ? "停止语音" : "语音输入"}
                </button>
                <button
                  className={`chat-triad-btn ${activeVoiceFeature === "realtime-call" ? "chat-triad-btn-danger" : ""}`}
                  disabled={!activeSessionId}
                  onClick={() =>
                    activeVoiceFeature === "realtime-call"
                      ? void stopVoice()
                      : void startVoiceFeature("realtime-call")
                  }
                >
                  {activeVoiceFeature === "realtime-call" ? "结束通话" : "实时通话"}
                </button>
              </div>

              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={() => setIsComposing(false)}
                onKeyDown={(e) => {
                  const composing = isComposing || Boolean((e.nativeEvent as KeyboardEvent).isComposing);
                  if (e.key === "Enter" && !e.shiftKey && !composing) {
                    e.preventDefault();
                    sendTextNow();
                  }
                }}
                className="chat-composer-textarea"
                placeholder="输入消息"
              />

              <div className="chat-composer-actions">
                <div className="chat-composer-status">
                  {listening ? (
                    <div className="flex gap-2">
                      <button className="hidden" onClick={() => void interruptVoice()} aria-hidden="true" tabIndex={-1}>
                        已隐藏手动打断
                      </button>
                      <button className="chat-triad-sub" onClick={() => void stopVoice()}>
                        关闭语音
                      </button>
                    </div>
                  ) : (
                    <span className="chat-composer-hint">按回车发送（Shift+回车换行）</span>
                  )}
                </div>
                <button
                  className="chat-send-btn chat-send-btn-circle"
                  title="发送"
                  disabled={!activeSessionId || !inputText.trim() || sendMutation.isPending}
                  onClick={sendTextNow}
                >
                  发送
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

