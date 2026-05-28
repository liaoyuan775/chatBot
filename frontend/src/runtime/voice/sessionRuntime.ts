import { IntegratedRealtimeStrategy } from "./integratedStrategy";
import { SplitChainStrategy } from "./splitStrategy";
import type {
  RuntimeConfig,
  RuntimeEvent,
  RuntimeEventListener,
  RuntimeEventMap,
  RuntimeEventName,
  RuntimeMessage,
  RuntimeSnapshot,
  StrategyContext,
  StudioState,
  VoiceMode,
  VoiceStrategy
} from "./types";

export type SendTextTurnExecutor = (params: {
  sessionId: string;
  text: string;
  signal?: AbortSignal;
  onDelta: (chunk: {
    text?: string;
    done?: boolean;
    audio_url?: string | null;
    audio_base64?: string;
    audio_mime?: string;
    image_url?: string | null;
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
}) => Promise<void>;

export type TranscribeAudioExecutor = (params: { sessionId: string; blob: Blob; filename: string }) => Promise<string>;

export type SessionRuntimeDeps = {
  sendTextTurn: SendTextTurnExecutor;
  transcribeAudio: TranscribeAudioExecutor;
};

function createMessage(role: "user" | "assistant", text: string, id?: string): RuntimeMessage {
  return {
    id: id ?? `${role}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    role,
    text,
    createdAt: new Date().toISOString(),
    partial: false,
    final: false,
    interrupted: false,
    audioUrl: null
  };
}

export class SessionRuntime {
  private deps: SessionRuntimeDeps;

  private listeners = new Set<RuntimeEventListener>();

  private snapshot: RuntimeSnapshot;

  private liveConfig: RuntimeConfig;

  private activeStrategy: VoiceStrategy | null = null;

  private integratedStrategy = new IntegratedRealtimeStrategy();

  private splitStrategy = new SplitChainStrategy();

  private currentAssistantMessageId: string | null = null;

  private currentTurnId: string | null = null;

  private turnStartedAt = 0;

  private firstTextAt = 0;

  private firstAudioAt = 0;

  private currentTextAbortController: AbortController | null = null;

  private lastAssistantReply: { text: string; playedAt: number } | null = null;

  private streamedAudioInCurrentTurn = false;

  constructor(deps: SessionRuntimeDeps, config?: Partial<RuntimeConfig>) {
    this.deps = deps;
    this.liveConfig = {
      mode: config?.mode ?? "integrated-realtime",
      splitAsr: config?.splitAsr ?? "auto",
      feature: config?.feature ?? "realtime-call",
      autoSubmitVoiceTurns: config?.autoSubmitVoiceTurns ?? true
    };
    this.snapshot = {
      sessionId: null,
      mode: this.liveConfig.mode,
      studioState: "idle",
      transcript: "",
      messages: [],
      metrics: {},
      listening: false
    };
  }

  private getContext(): StrategyContext {
    return {
      getSessionId: () => this.snapshot.sessionId,
      getConfig: () => this.liveConfig,
      getStudioState: () => this.snapshot.studioState,
      getLastAssistantReply: () => this.lastAssistantReply,
      emit: (type, payload) => this.emit(type, payload),
      setState: (state, reason) => this.setState(state, reason),
      sendTextTurn: async (text, _source) => {
        await this.sendTextTurn(text, { emitUserMessage: _source === "manual-text" });
      },
      interruptReply: async (reason) => this.abortActiveReply(reason),
      transcribeAudio: async (blob, filename) => {
        const sessionId = this.snapshot.sessionId;
        if (!sessionId) return "";
        return this.deps.transcribeAudio({ sessionId, blob, filename });
      }
    };
  }

  private selectStrategy(mode: VoiceMode): VoiceStrategy {
    return mode === "integrated-realtime" ? this.integratedStrategy : this.splitStrategy;
  }

  private addOrUpdateAssistantMessage(text: string, done: boolean, audioUrl?: string | null) {
    if (!this.currentAssistantMessageId) {
      const msg = createMessage("assistant", text);
      msg.partial = !done;
      msg.final = done;
      msg.audioUrl = audioUrl ?? null;
      this.currentAssistantMessageId = msg.id;
      this.snapshot.messages = [...this.snapshot.messages, msg];
      return;
    }
    this.snapshot.messages = this.snapshot.messages.map((item) => {
      if (item.id !== this.currentAssistantMessageId) return item;
      return {
        ...item,
        text,
        partial: !done,
        final: done,
        audioUrl: audioUrl === undefined ? item.audioUrl : audioUrl
      };
    });
  }

  private addUserMessage(text: string, partial: boolean) {
    const last = this.snapshot.messages[this.snapshot.messages.length - 1];
    if (last && last.role === "user" && last.partial) {
      this.snapshot.messages = this.snapshot.messages.map((item, idx) => {
        if (idx !== this.snapshot.messages.length - 1) return item;
        return { ...item, text, partial, final: !partial };
      });
      return;
    }
    const msg = createMessage("user", text);
    msg.partial = partial;
    msg.final = !partial;
    this.snapshot.messages = [...this.snapshot.messages, msg];
  }

  private emit(type: RuntimeEventName, payload: RuntimeEventMap[RuntimeEventName]) {
    const data = payload as any;
    if (type === "session.state.changed") {
      this.snapshot.studioState = data.state;
    }
    if (type === "user.transcript.partial") {
      if (data.turn_id) this.currentTurnId = data.turn_id;
      this.snapshot.transcript = data.text;
      this.addUserMessage(data.text, true);
    }
    if (type === "user.transcript.final") {
      if (data.turn_id) this.currentTurnId = data.turn_id;
      this.snapshot.transcript = data.text;
      this.addUserMessage(data.text, false);
      this.currentAssistantMessageId = null;
    }
    if (type === "assistant.text.delta") {
      this.addOrUpdateAssistantMessage(data.text, false);
      if (!this.firstTextAt) this.firstTextAt = Date.now();
    }
    if (type === "assistant.text.final") {
      this.addOrUpdateAssistantMessage(data.text, true);
      if (!this.firstTextAt) this.firstTextAt = Date.now();
      const finalText = (data.text || "").trim();
      if (finalText) {
        this.lastAssistantReply = { text: finalText, playedAt: Date.now() };
      }
    }
    if (type === "assistant.audio.started") {
      if (!this.firstAudioAt) this.firstAudioAt = Date.now();
      const latestAssistantText =
        [...this.snapshot.messages].reverse().find((item) => item.role === "assistant")?.text?.trim() ?? "";
      if (latestAssistantText) {
        this.lastAssistantReply = { text: latestAssistantText, playedAt: Date.now() };
      }
      this.activeStrategy?.notifyAudioStarted?.();
    }
    if (type === "assistant.audio.stopped") {
      // no-op: notifyAudioStopped() is called via notifyAudioPlaybackEnded() when browser speakers actually finish
    }
    if (type === "assistant.interrupted") {
      if (this.currentAssistantMessageId) {
        this.snapshot.messages = this.snapshot.messages.map((item) =>
          item.id === this.currentAssistantMessageId ? { ...item, interrupted: true, final: true, partial: false } : item
        );
      }
    }
    if (type === "metrics.turn") {
      this.snapshot.metrics.lastTurn = {
        turnId: data.turn_id,
        contextLatencyMs: data.context_latency_ms,
        firstTextLatencyMs: data.first_text_latency_ms,
        firstAudioLatencyMs: data.first_audio_latency_ms,
        interruptLatencyMs: data.interrupt_latency_ms,
        retrievalLatencyMs: data.retrieval_latency_ms,
        llmLatencyMs: data.llm_latency_ms,
        ttsLatencyMs: data.tts_latency_ms,
        totalLatencyMs: data.total_latency_ms
      };
    }
    if (type === "metrics.retrieval") {
      this.snapshot.metrics.lastRetrieval = {
        turnId: data.turn_id,
        latencyMs: data.latency_ms,
        hitCount: data.hit_count,
        decision: data.decision,
        reason: data.reason,
        timedOut: data.timed_out
      };
    }

    const evt = { type, payload, at: Date.now() } as RuntimeEvent;
    this.listeners.forEach((listener) => {
      listener(evt);
    });
  }

  private setState(state: StudioState, reason?: string) {
    this.snapshot.studioState = state;
    this.emit("session.state.changed", { state, reason });
  }

  private async ensureStrategy() {
    const nextStrategy = this.selectStrategy(this.snapshot.mode);
    if (this.activeStrategy && this.activeStrategy !== nextStrategy) {
      await this.activeStrategy.stopListening(this.getContext());
      await this.activeStrategy.destroy?.();
      this.activeStrategy = null;
    }
    if (!this.activeStrategy) {
      this.activeStrategy = nextStrategy;
    }
  }

  setSession(sessionId: string | null) {
    this.snapshot.sessionId = sessionId;
    if (sessionId) {
      this.emit("session.updated", { session_id: sessionId });
    }
  }

  applyLiveConfig(next: Partial<RuntimeConfig>) {
    this.liveConfig = {
      mode: next.mode ?? this.liveConfig.mode,
      splitAsr: next.splitAsr ?? this.liveConfig.splitAsr,
      feature: next.feature ?? this.liveConfig.feature,
      autoSubmitVoiceTurns: next.autoSubmitVoiceTurns ?? this.liveConfig.autoSubmitVoiceTurns
    };
    this.snapshot.mode = this.liveConfig.mode;
    this.emit("session.updated", { session_id: this.snapshot.sessionId ?? "", messages: [] });
  }

  async startListening() {
    if (!this.snapshot.sessionId) return;
    this.snapshot.listening = true;
    try {
      await this.ensureStrategy();
      await this.activeStrategy?.startListening(this.getContext());
    } catch {
      this.snapshot.listening = false;
    }
  }

  async stopListening() {
    this.snapshot.listening = false;
    await this.activeStrategy?.stopListening(this.getContext());
  }

  async interruptCurrentReply() {
    const started = Date.now();
    await this.abortActiveReply("manual-interrupt");
    await this.activeStrategy?.interrupt(this.getContext());
    const latency = Date.now() - started;
    if (this.currentTurnId) {
      this.emit("metrics.turn", { turn_id: this.currentTurnId, interrupt_latency_ms: latency });
    }
  }

  notifyAudioPlaybackEnded() {
    this.activeStrategy?.notifyAudioStopped?.();
  }

  private async abortActiveReply(reason = "abort-controller") {
    const pendingTurnId = this.currentTurnId;
    if (!this.currentTextAbortController) return;
    this.currentTextAbortController.abort();
    this.currentTextAbortController = null;
    if (pendingTurnId) {
      this.emit("assistant.interrupted", { turn_id: pendingTurnId, reason });
    }
  }

  async sendTextTurn(text: string, options?: { emitUserMessage?: boolean }) {
    const sessionId = this.snapshot.sessionId;
    const clean = text.trim();
    if (!sessionId || !clean) return;

    await this.abortActiveReply("superseded-turn");
    const turnId = `turn-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    this.currentTurnId = turnId;
    this.turnStartedAt = Date.now();
    this.firstTextAt = 0;
    this.firstAudioAt = 0;
    this.streamedAudioInCurrentTurn = false;

    if (options?.emitUserMessage !== false) {
      this.emit("user.transcript.final", { text: clean, turn_id: turnId });
    }
    this.setState("thinking", "send-text-turn");
    const controller = new AbortController();
    this.currentTextAbortController = controller;

    try {
      await this.deps.sendTextTurn({
        sessionId,
        text: clean,
        signal: controller.signal,
        onDelta: (chunk) => {
          if (chunk.event === "metrics.retrieval" && chunk.retrieval) {
            this.emit("metrics.retrieval", {
              turn_id: chunk.turn_id ?? turnId,
              latency_ms: chunk.retrieval.latency_ms,
              hit_count: chunk.retrieval.hit_count,
              decision: chunk.retrieval.decision,
              reason: chunk.retrieval.reason,
              timed_out: chunk.retrieval.timed_out
            });
          }
          if (chunk.event === "assistant.audio.delta" && chunk.audio_base64) {
            this.streamedAudioInCurrentTurn = true;
            if (!this.firstAudioAt) {
              this.emit("assistant.audio.started", {
                turn_id: chunk.turn_id ?? turnId,
                audio_mime: chunk.audio_mime ?? "audio/mpeg"
              });
            }
            this.emit("assistant.audio.delta", {
              turn_id: chunk.turn_id ?? turnId,
              audio_mime: chunk.audio_mime ?? "audio/mpeg",
              audio_base64: chunk.audio_base64
            });
          }
          const textValue = String(chunk.text ?? "");
          if (textValue) {
            this.emit(chunk.done ? "assistant.text.final" : "assistant.text.delta", { text: textValue, turn_id: turnId });
            if (!chunk.done) {
              this.setState("thinking", "assistant-streaming");
            }
          }
          if (chunk.audio_url) {
            this.addOrUpdateAssistantMessage(textValue, Boolean(chunk.done), chunk.audio_url);
            if (!chunk.event && !this.streamedAudioInCurrentTurn) {
              const match = String(chunk.audio_url).match(/^data:([^;]+);base64,(.+)$/);
              const audioMime = match?.[1] ?? "audio/mpeg";
              this.emit("assistant.audio.started", { turn_id: turnId, audio_mime: audioMime });
              if (match?.[2]) {
                this.emit("assistant.audio.delta", { turn_id: turnId, audio_mime: audioMime, audio_base64: match[2] });
              }
              this.emit("assistant.audio.stopped", { turn_id: turnId });
              this.setState("speaking", "assistant-audio-ready");
            }
          }
          if (chunk.done) {
            if (this.firstAudioAt) {
              this.emit("assistant.audio.stopped", { turn_id: turnId });
            }
            const firstTextLatency =
              chunk.metrics?.first_text_latency_ms ?? (this.firstTextAt ? this.firstTextAt - this.turnStartedAt : undefined);
            const firstAudioLatency =
              chunk.metrics?.first_audio_latency_ms ?? (this.firstAudioAt ? this.firstAudioAt - this.turnStartedAt : undefined);
            this.emit("metrics.turn", {
              turn_id: turnId,
              context_latency_ms: chunk.metrics?.context_latency_ms,
              first_text_latency_ms: firstTextLatency,
              first_audio_latency_ms: firstAudioLatency,
              retrieval_latency_ms: chunk.metrics?.retrieval_latency_ms,
              llm_latency_ms: chunk.metrics?.llm_latency_ms,
              tts_latency_ms: chunk.metrics?.tts_latency_ms,
              total_latency_ms: chunk.metrics?.total_latency_ms
            });
            this.setState(this.snapshot.listening ? "listening" : "idle", "turn-done");
          }
        }
      });
    } catch (error) {
      if (error instanceof Error && /取消|Abort|aborted|超时/.test(error.message)) {
        this.emit("assistant.interrupted", { turn_id: turnId, reason: "abort-controller" });
        this.setState(this.snapshot.listening ? "listening" : "idle", "turn-aborted");
      } else {
        this.emit("session.error", { message: error instanceof Error ? error.message : "send text turn failed" });
        this.setState("error", "send-text-failed");
      }
    } finally {
      if (this.currentTextAbortController === controller) {
        this.currentTextAbortController = null;
      }
      this.streamedAudioInCurrentTurn = false;
    }
  }

  getSnapshot() {
    return this.snapshot;
  }

  onEvent(listener: RuntimeEventListener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  async destroy() {
    this.snapshot.listening = false;
    await this.activeStrategy?.destroy?.();
    this.listeners.clear();
  }
}

