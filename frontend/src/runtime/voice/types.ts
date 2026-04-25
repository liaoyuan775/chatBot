export type StudioState = "idle" | "listening" | "thinking" | "speaking" | "error";

export type VoiceMode = "integrated-realtime" | "split-chain";

export type RuntimeMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  partial?: boolean;
  interrupted?: boolean;
  final?: boolean;
  audioUrl?: string | null;
  createdAt: string;
};

export type TurnMetrics = {
  turnId: string;
  contextLatencyMs?: number;
  firstTextLatencyMs?: number;
  firstAudioLatencyMs?: number;
  interruptLatencyMs?: number;
  retrievalLatencyMs?: number;
  llmLatencyMs?: number;
  ttsLatencyMs?: number;
  totalLatencyMs?: number;
};

export type RuntimeMetrics = {
  lastTurn?: TurnMetrics;
  lastRetrieval?: {
    turnId?: string;
    latencyMs?: number;
    hitCount?: number;
    decision?: string;
    reason?: string;
    timedOut?: boolean;
  };
};

export type RuntimeSnapshot = {
  sessionId: string | null;
  mode: VoiceMode;
  studioState: StudioState;
  transcript: string;
  messages: RuntimeMessage[];
  metrics: RuntimeMetrics;
  listening: boolean;
};

export type RuntimeEventMap = {
  "session.ready": { session_id: string; mode: VoiceMode };
  "session.updated": { message?: unknown; messages?: unknown[]; session_id: string };
  "session.error": { message: string; code?: string };
  "session.state.changed": { state: StudioState; reason?: string };
  "user.transcript.partial": { text: string; turn_id?: string };
  "user.transcript.final": { text: string; turn_id?: string };
  "assistant.text.delta": { text: string; turn_id?: string };
  "assistant.text.final": { text: string; turn_id?: string };
  "assistant.audio.started": { turn_id?: string; audio_mime?: string };
  "assistant.audio.delta": { audio_base64: string; audio_mime?: string; turn_id?: string };
  "assistant.audio.stopped": { turn_id?: string };
  "assistant.interrupted": { turn_id?: string; reason?: string };
  "metrics.turn": {
    turn_id: string;
    context_latency_ms?: number;
    first_text_latency_ms?: number;
    first_audio_latency_ms?: number;
    interrupt_latency_ms?: number;
    retrieval_latency_ms?: number;
    llm_latency_ms?: number;
    tts_latency_ms?: number;
    total_latency_ms?: number;
  };
  "metrics.retrieval": {
    turn_id?: string;
    latency_ms?: number;
    hit_count?: number;
    decision?: string;
    reason?: string;
    timed_out?: boolean;
  };
};

export type RuntimeEventName = keyof RuntimeEventMap;

export type RuntimeEvent = {
  [K in RuntimeEventName]: {
    type: K;
    payload: RuntimeEventMap[K];
    at: number;
  };
}[RuntimeEventName];

export type RuntimeEventListener = (event: RuntimeEvent) => void;

export type RuntimeConfig = {
  mode: VoiceMode;
  splitAsr: "auto" | "browser" | "backend";
  feature: "voice-input" | "realtime-call";
  autoSubmitVoiceTurns: boolean;
};

export type StrategyContext = {
  getSessionId: () => string | null;
  getConfig: () => RuntimeConfig;
  getStudioState: () => StudioState;
  getLastAssistantReply: () => { text: string; playedAt: number } | null;
  emit: <K extends RuntimeEventName>(type: K, payload: RuntimeEventMap[K]) => void;
  setState: (state: StudioState, reason?: string) => void;
  sendTextTurn: (text: string, source: "browser-asr" | "backend-asr" | "manual-text") => Promise<void>;
  interruptReply: (reason?: string) => Promise<void>;
  transcribeAudio: (blob: Blob, filename: string) => Promise<string>;
};

export interface VoiceStrategy {
  startListening(ctx: StrategyContext): Promise<void>;
  stopListening(ctx: StrategyContext): Promise<void>;
  interrupt(ctx: StrategyContext): Promise<void>;
  destroy?(): Promise<void>;
}


