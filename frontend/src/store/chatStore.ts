import { create } from "zustand";

type ChatStore = {
  activeSessionId: string | null;
  inputText: string;
  realtimeEnabled: boolean;
  voiceMode: "integrated-realtime" | "split-chain";
  studioState: "idle" | "listening" | "thinking" | "speaking" | "error";
  runtimeMetrics: {
    turnId?: string;
    contextLatencyMs?: number;
    firstTextLatencyMs?: number;
    firstAudioLatencyMs?: number;
    interruptLatencyMs?: number;
    retrievalLatencyMs?: number;
    llmLatencyMs?: number;
    ttsLatencyMs?: number;
    totalLatencyMs?: number;
  };
  turnDraft: {
    userText?: string;
    assistantText?: string;
  };
  setActiveSessionId: (id: string | null) => void;
  setInputText: (text: string) => void;
  setRealtimeEnabled: (v: boolean) => void;
  setVoiceMode: (mode: "integrated-realtime" | "split-chain") => void;
  setStudioState: (state: "idle" | "listening" | "thinking" | "speaking" | "error") => void;
  setRuntimeMetrics: (metrics: ChatStore["runtimeMetrics"]) => void;
  setTurnDraft: (draft: ChatStore["turnDraft"]) => void;
};

export const useChatStore = create<ChatStore>((set) => ({
  activeSessionId: null,
  inputText: "",
  realtimeEnabled: false,
  voiceMode: "integrated-realtime",
  studioState: "idle",
  runtimeMetrics: {},
  turnDraft: {},
  setActiveSessionId: (id) => set({ activeSessionId: id }),
  setInputText: (text) => set({ inputText: text }),
  setRealtimeEnabled: (v) => set({ realtimeEnabled: v }),
  setVoiceMode: (mode) => set({ voiceMode: mode }),
  setStudioState: (studioState) => set({ studioState }),
  setRuntimeMetrics: (runtimeMetrics) => set({ runtimeMetrics }),
  setTurnDraft: (turnDraft) => set({ turnDraft })
}));
