import type { StrategyContext, VoiceStrategy } from "./types";

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

interface BrowserSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionCtor = new () => BrowserSpeechRecognition;

type SpeechRecognitionAlternativeLike = {
  transcript: string;
};

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
  length: number;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
};

type SpeechRecognitionErrorEventLike = {
  error: string;
};

export class SplitChainStrategy implements VoiceStrategy {
  private listening = false;
  private recognition: BrowserSpeechRecognition | null = null;
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private restartTimer: number | null = null;
  private interrupted = false;
  private bargeInTriggered = false;
  private audioPlaying = false;
  private activeCtx: StrategyContext | null = null;

  private async openMicStream() {
    return navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });
  }

  private normalizeTranscript(text: string) {
    return text
      .toLowerCase()
      .replace(/[\s\p{P}\p{S}]+/gu, "")
      .trim();
  }

  private shouldSuppressEcho(ctx: StrategyContext, text: string) {
    const clean = this.normalizeTranscript(text);
    if (!clean) return false;
    const lastAssistantReply = ctx.getLastAssistantReply();
    if (!lastAssistantReply?.text?.trim()) return false;
    const ageMs = Date.now() - lastAssistantReply.playedAt;
    if (ageMs > 12000) return false;
    const assistantClean = this.normalizeTranscript(lastAssistantReply.text);
    if (!assistantClean) return false;
    if (clean === assistantClean) return true;
    if (clean.length >= 4 && assistantClean.includes(clean)) return true;
    if (assistantClean.length >= 4 && clean.includes(assistantClean)) return true;
    const overlapChars = [...clean].filter((char) => assistantClean.includes(char)).length;
    const overlapRatio = overlapChars / Math.max(clean.length, assistantClean.length, 1);
    return overlapRatio >= 0.82;
  }

  private maybeBargeIn(ctx: StrategyContext) {
    if (ctx.getConfig().feature !== "realtime-call") return;
    if (this.bargeInTriggered) return;
    const state = ctx.getStudioState();
    if (state !== "thinking" && state !== "speaking") return;
    this.bargeInTriggered = true;
    void ctx.interruptReply("split-barge-in");
  }

  private pauseAsr() {
    if (this.restartTimer !== null) {
      window.clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    this.recognition?.abort();
    this.recognition = null;
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }
    this.recorder = null;
  }

  private async resumeAsr(ctx: StrategyContext) {
    if (!this.listening || this.interrupted) return;
    this.restartTimer = window.setTimeout(() => {
      this.restartTimer = null;
      if (!this.listening || this.audioPlaying) return;
      const cfg = ctx.getConfig();
      if (cfg.splitAsr === "backend") {
        void this.startBackendAsr(ctx);
      } else if (cfg.splitAsr === "browser") {
        void this.startBrowserAsr(ctx);
      } else {
        void this.startBrowserAsr(ctx).catch(() => {
          void this.startBackendAsr(ctx);
        });
      }
    }, 80);
  }

  notifyAudioStarted() {
    this.audioPlaying = true;
    this.pauseAsr();
  }

  notifyAudioStopped() {
    this.audioPlaying = false;
    if (this.activeCtx) {
      void this.resumeAsr(this.activeCtx);
    }
  }

  private async startBrowserAsr(ctx: StrategyContext) {
    const Ctor = (window.SpeechRecognition ?? window.webkitSpeechRecognition) as SpeechRecognitionCtor | undefined;
    if (!Ctor) {
      throw new Error("browser-asr-not-supported");
    }
    if (!this.stream) {
      this.stream = await this.openMicStream();
    }
    const recognition = new Ctor();
    this.recognition = recognition;
    recognition.lang = "zh-CN";
    recognition.continuous = ctx.getConfig().feature === "realtime-call";
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      ctx.setState("listening", "split-browser-asr");
    };
    recognition.onresult = (event) => {
      let interimText = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript?.trim() ?? "";
        if (!text) continue;
        if (result.isFinal) finalText = `${finalText}${text}`.trim();
        else interimText = `${interimText}${text}`.trim();
      }
      if (interimText) {
        if (this.shouldSuppressEcho(ctx, interimText)) {
          return;
        }
        this.maybeBargeIn(ctx);
        ctx.emit("user.transcript.partial", { text: interimText });
      }
      if (finalText) {
        if (this.shouldSuppressEcho(ctx, finalText)) {
          this.bargeInTriggered = false;
          return;
        }
        this.maybeBargeIn(ctx);
        ctx.emit("user.transcript.final", { text: finalText });
        this.bargeInTriggered = false;
        if (ctx.getConfig().autoSubmitVoiceTurns) {
          void ctx.sendTextTurn(finalText, "browser-asr");
        }
      }
    };
    recognition.onerror = (event) => {
      if (event.error !== "aborted") {
        void this.startBackendAsr(ctx);
      }
    };
    recognition.onend = () => {
      this.recognition = null;
      this.bargeInTriggered = false;
      if (!this.listening || this.interrupted) {
        this.interrupted = false;
        return;
      }
      if (this.audioPlaying) return;
      this.restartTimer = window.setTimeout(() => {
        this.restartTimer = null;
        if (!this.listening || this.audioPlaying) return;
        void this.startBrowserAsr(ctx).catch(() => {
          void this.startBackendAsr(ctx);
        });
      }, 80);
    };
    recognition.start();
  }

  private async startBackendAsr(ctx: StrategyContext) {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      ctx.emit("session.error", { message: "backend-asr requires media recorder support" });
      ctx.setState("error", "media-recorder-unsupported");
      return;
    }
    if (!this.stream) {
      this.stream = await this.openMicStream();
    }
    const recorder = new MediaRecorder(this.stream);
    this.recorder = recorder;
    const chunks: Blob[] = [];
    let firstChunkAt = 0;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        if (!firstChunkAt) firstChunkAt = Date.now();
        chunks.push(event.data);
      }
    };

    recorder.onstop = () => {
      this.recorder = null;
      const blob = new Blob(chunks, { type: "audio/webm" });
      if (!blob.size) return;
      const filename = `split-${Date.now()}.webm`;
      void (async () => {
        try {
          ctx.setState("thinking", "backend-asr");
          const text = (await ctx.transcribeAudio(blob, filename)).trim();
          if (!text) {
            ctx.emit("session.error", { message: "backend-asr returned empty text" });
            return;
          }
          if (this.shouldSuppressEcho(ctx, text)) {
            this.bargeInTriggered = false;
            return;
          }
          this.maybeBargeIn(ctx);
          ctx.emit("user.transcript.final", { text });
          this.bargeInTriggered = false;
          if (ctx.getConfig().autoSubmitVoiceTurns) {
            await ctx.sendTextTurn(text, "backend-asr");
          }
          const latency = firstChunkAt ? Date.now() - firstChunkAt : undefined;
          ctx.emit("metrics.turn", { turn_id: `split-${Date.now()}`, first_text_latency_ms: latency });
        } catch (error) {
          ctx.emit("session.error", { message: error instanceof Error ? error.message : "backend-asr failed" });
          ctx.setState("error", "backend-asr-failed");
        } finally {
          if (this.listening && !this.audioPlaying) {
            this.restartTimer = window.setTimeout(() => {
              this.restartTimer = null;
              if (!this.listening || this.audioPlaying) return;
              void this.startBackendAsr(ctx);
            }, 80);
          }
        }
      })();
    };

    recorder.start();
    this.restartTimer = window.setTimeout(() => {
      this.restartTimer = null;
      if (this.recorder && this.recorder.state !== "inactive") {
        this.recorder.stop();
      }
    }, ctx.getConfig().feature === "realtime-call" ? 1400 : 2200);
  }

  async startListening(ctx: StrategyContext): Promise<void> {
    this.activeCtx = ctx;
    this.listening = true;
    this.interrupted = false;
    this.bargeInTriggered = false;
    this.audioPlaying = false;
    const cfg = ctx.getConfig();
    if (cfg.splitAsr === "backend") {
      await this.startBackendAsr(ctx);
      return;
    }
    if (cfg.splitAsr === "browser") {
      await this.startBrowserAsr(ctx);
      return;
    }
    try {
      await this.startBrowserAsr(ctx);
    } catch {
      await this.startBackendAsr(ctx);
    }
  }

  async stopListening(ctx: StrategyContext): Promise<void> {
    this.listening = false;
    this.interrupted = true;
    this.audioPlaying = false;
    if (this.restartTimer !== null) {
      window.clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    this.recognition?.abort();
    this.recognition = null;
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }
    this.recorder = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    ctx.setState("idle", "split-stop");
  }

  async interrupt(ctx: StrategyContext): Promise<void> {
    this.interrupted = true;
    this.bargeInTriggered = false;
    this.audioPlaying = false;
    this.recognition?.abort();
    this.recognition = null;
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }
    this.recorder = null;
    ctx.emit("assistant.interrupted", { reason: "split-interrupt" });
    ctx.setState("listening", "split-interrupt");
  }

  async destroy(): Promise<void> {
    this.listening = false;
    this.bargeInTriggered = false;
    this.audioPlaying = false;
    this.activeCtx = null;
    if (this.restartTimer !== null) {
      window.clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    this.recognition?.abort();
    this.recognition = null;
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }
    this.recorder = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }
}
