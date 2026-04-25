import type { StrategyContext, VoiceStrategy } from "./types";

type UnifiedServerEvent = {
  event?: string;
  [key: string]: unknown;
};

function arrayBufferToBase64(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return window.btoa(binary);
}

function getWsBase() {
  const configured = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  const base =
    configured ||
    (typeof window !== "undefined" && window.location?.origin ? window.location.origin : "http://127.0.0.1:8000");
  return base
    .replace("http://", "ws://")
    .replace("https://", "wss://");
}

function downsampleToPcm16(input: Float32Array, inputRate: number, targetRate: number) {
  if (targetRate === inputRate) {
    const pcm = new Int16Array(input.length);
    for (let i = 0; i < input.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, input[i]));
      pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm.buffer;
  }

  const ratio = inputRate / targetRate;
  const length = Math.max(1, Math.round(input.length / ratio));
  const pcm = new Int16Array(length);
  let offset = 0;
  for (let i = 0; i < length; i += 1) {
    const nextOffset = Math.min(input.length, Math.round((i + 1) * ratio));
    let sum = 0;
    let count = 0;
    while (offset < nextOffset) {
      sum += input[offset];
      offset += 1;
      count += 1;
    }
    const sample = Math.max(-1, Math.min(1, count ? sum / count : 0));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return pcm.buffer;
}

export class IntegratedRealtimeStrategy implements VoiceStrategy {
  private ws: WebSocket | null = null;

  private stream: MediaStream | null = null;

  private listening = false;

  private reconnectTimer: number | null = null;

  private audioContext: AudioContext | null = null;

  private analyser: AnalyserNode | null = null;

  private sourceNode: MediaStreamAudioSourceNode | null = null;

  private processorNode: ScriptProcessorNode | null = null;

  private muteGainNode: GainNode | null = null;

  private speechMeterTimer: number | null = null;

  private assistantSpeaking = false;

  private speechFrameStreak = 0;

  private lastAutoInterruptAt = 0;

  private readonly targetSampleRate = 16000;

  private readonly speechThresholdRms = 0.01;

  private readonly speechThresholdWhenAssistantRms = 0.024;

  private readonly speechActivationFrames = 2;

  private readonly speechActivationFramesWhenAssistant = 4;

  private readonly autoInterruptCooldownMs = 900;

  private syncConfig(ctx: StrategyContext) {
    this.send({
      event: "session.config",
      auto_reply: ctx.getConfig().autoSubmitVoiceTurns,
      feature: ctx.getConfig().feature
    });
  }

  private connect(ctx: StrategyContext) {
    const sessionId = ctx.getSessionId();
    if (!sessionId) return;
    const ws = new WebSocket(`${getWsBase()}/ws/realtime-chat?session_id=${sessionId}`);
    this.ws = ws;
    ws.onopen = () => {
      this.syncConfig(ctx);
      ctx.emit("session.ready", { session_id: sessionId, mode: "integrated-realtime" });
      ctx.setState("listening", "connected");
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(String(event.data)) as UnifiedServerEvent;
        const eventName = String(data.event ?? "");
        if (!eventName) return;
        if (eventName === "session.error") {
          ctx.emit("session.error", { message: String(data.message ?? "unknown") });
          ctx.setState("error", String(data.message ?? "unknown"));
          return;
        }
        if (eventName === "session.state.changed") {
          const state = String(data.state ?? "idle") as "idle" | "listening" | "thinking" | "speaking" | "error";
          ctx.emit("session.state.changed", { state, reason: typeof data.reason === "string" ? data.reason : undefined });
          ctx.setState(state, typeof data.reason === "string" ? data.reason : undefined);
          return;
        }
        if (eventName === "user.transcript.partial") {
          ctx.emit("user.transcript.partial", {
            text: String(data.text ?? ""),
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined
          });
          return;
        }
        if (eventName === "user.transcript.final") {
          ctx.emit("user.transcript.final", {
            text: String(data.text ?? ""),
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined
          });
          return;
        }
        if (eventName === "assistant.text.delta") {
          ctx.emit("assistant.text.delta", {
            text: String(data.text ?? ""),
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined
          });
          return;
        }
        if (eventName === "assistant.text.final") {
          ctx.emit("assistant.text.final", {
            text: String(data.text ?? ""),
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined
          });
          return;
        }
        if (eventName === "assistant.audio.started") {
          this.assistantSpeaking = true;
          ctx.emit("assistant.audio.started", {
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined,
            audio_mime: typeof data.audio_mime === "string" ? data.audio_mime : undefined
          });
          return;
        }
        if (eventName === "assistant.audio.delta") {
          const audio_base64 = String(data.audio_base64 ?? "");
          if (!audio_base64) return;
          ctx.emit("assistant.audio.delta", {
            audio_base64,
            audio_mime: typeof data.audio_mime === "string" ? data.audio_mime : undefined,
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined
          });
          return;
        }
        if (eventName === "assistant.audio.stopped") {
          this.assistantSpeaking = false;
          ctx.emit("assistant.audio.stopped", { turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined });
          return;
        }
        if (eventName === "assistant.interrupted") {
          this.assistantSpeaking = false;
          ctx.emit("assistant.interrupted", {
            turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined,
            reason: typeof data.reason === "string" ? data.reason : undefined
          });
          return;
        }
        if (eventName === "session.updated") {
          ctx.emit("session.updated", {
            session_id: sessionId,
            message: typeof data.message === "object" ? data.message : undefined,
            messages: Array.isArray(data.messages) ? (data.messages as unknown[]) : undefined
          });
          return;
        }
        if (eventName === "metrics.turn") {
          ctx.emit("metrics.turn", {
            turn_id: String(data.turn_id ?? ""),
            first_text_latency_ms: typeof data.first_text_latency_ms === "number" ? data.first_text_latency_ms : undefined,
            first_audio_latency_ms: typeof data.first_audio_latency_ms === "number" ? data.first_audio_latency_ms : undefined,
            interrupt_latency_ms: typeof data.interrupt_latency_ms === "number" ? data.interrupt_latency_ms : undefined
          });
        }
      } catch {
        ctx.emit("session.error", { message: "invalid realtime message" });
      }
    };
    ws.onerror = () => {
      ctx.emit("session.error", { message: "realtime websocket error" });
      ctx.setState("error", "ws-error");
    };
    ws.onclose = () => {
      this.ws = null;
      this.assistantSpeaking = false;
      if (this.listening && this.reconnectTimer === null) {
        this.reconnectTimer = window.setTimeout(() => {
          this.reconnectTimer = null;
          if (this.listening) {
            this.connect(ctx);
          }
        }, 500);
      }
    };
  }

  private send(payload: Record<string, unknown>) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(payload));
    return true;
  }

  private startSpeechMeter(ctx: StrategyContext) {
    if (!this.analyser) return;
    const data = new Uint8Array(this.analyser.fftSize);
    this.speechMeterTimer = window.setInterval(() => {
      if (!this.listening || !this.analyser) return;
      this.analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const normalized = (data[i] - 128) / 128;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / data.length);
      const threshold = this.assistantSpeaking ? this.speechThresholdWhenAssistantRms : this.speechThresholdRms;
      const requiredFrames = this.assistantSpeaking ? this.speechActivationFramesWhenAssistant : this.speechActivationFrames;
      if (rms >= threshold) {
        this.speechFrameStreak = Math.min(this.speechFrameStreak + 1, requiredFrames + 3);
      } else {
        this.speechFrameStreak = Math.max(0, this.speechFrameStreak - 1);
      }
      if (
        this.assistantSpeaking &&
        this.speechFrameStreak >= requiredFrames &&
        Date.now() - this.lastAutoInterruptAt >= this.autoInterruptCooldownMs
      ) {
        this.lastAutoInterruptAt = Date.now();
        this.assistantSpeaking = false;
        this.send({ event: "response.cancel", reason: "auto-barge-in" });
        ctx.emit("assistant.interrupted", { reason: "auto-barge-in" });
        ctx.setState("listening", "auto-barge-in");
      }
    }, 120);
  }

  private stopAudioPipeline() {
    if (this.speechMeterTimer !== null) {
      window.clearInterval(this.speechMeterTimer);
      this.speechMeterTimer = null;
    }
    this.processorNode?.disconnect();
    this.sourceNode?.disconnect();
    this.analyser?.disconnect();
    this.muteGainNode?.disconnect();
    this.processorNode = null;
    this.sourceNode = null;
    this.analyser = null;
    this.muteGainNode = null;
    this.speechFrameStreak = 0;
    this.lastAutoInterruptAt = 0;
    if (this.audioContext) {
      const ctx = this.audioContext;
      this.audioContext = null;
      void ctx.close().catch(() => undefined);
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  private async startMic(ctx: StrategyContext) {
    if (this.audioContext) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1
      }
    });
    const AudioContextCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextCtor) {
      throw new Error("audio-context-not-supported");
    }
    const audioContext = new AudioContextCtor({ latencyHint: "interactive" });
    this.audioContext = audioContext;
    const source = audioContext.createMediaStreamSource(this.stream);
    this.sourceNode = source;
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    this.analyser = analyser;
    source.connect(analyser);

    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    this.processorNode = processor;
    source.connect(processor);
    const muteGain = audioContext.createGain();
    muteGain.gain.value = 0;
    this.muteGainNode = muteGain;
    processor.connect(muteGain);
    muteGain.connect(audioContext.destination);

    processor.onaudioprocess = (event) => {
      if (!this.listening) return;
      const input = event.inputBuffer.getChannelData(0);
      const pcmBuffer = downsampleToPcm16(input, audioContext.sampleRate, this.targetSampleRate);
      const audioBase64 = arrayBufferToBase64(pcmBuffer);
      this.send({
        event: "audio_chunk",
        audio_base64: audioBase64,
        audio_mime: `audio/pcm;rate=${this.targetSampleRate}`
      });
    };

    await audioContext.resume();
    this.startSpeechMeter(ctx);
    ctx.setState("listening", "start-listening");
  }

  async startListening(ctx: StrategyContext): Promise<void> {
    this.listening = true;
    this.assistantSpeaking = false;
    if (!this.ws) this.connect(ctx);
    else this.syncConfig(ctx);
    await this.startMic(ctx);
  }

  async stopListening(ctx: StrategyContext): Promise<void> {
    this.listening = false;
    this.assistantSpeaking = false;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const shouldFlushTranscript = !ctx.getConfig().autoSubmitVoiceTurns;
    if (shouldFlushTranscript) {
      this.send({ event: "input_audio.commit" });
      await new Promise((resolve) => window.setTimeout(resolve, 900));
    }
    this.send({ event: "session.end" });
    this.ws?.close();
    this.ws = null;
    this.stopAudioPipeline();
    ctx.setState("idle", "stop-listening");
  }

  async interrupt(ctx: StrategyContext): Promise<void> {
    const sent = this.send({ event: "response.cancel" });
    this.assistantSpeaking = false;
    if (!sent) {
      ctx.emit("assistant.interrupted", { reason: "local-interrupt" });
    }
    ctx.setState("listening", "interrupt");
  }

  async destroy(): Promise<void> {
    this.listening = false;
    this.assistantSpeaking = false;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.stopAudioPipeline();
  }
}
