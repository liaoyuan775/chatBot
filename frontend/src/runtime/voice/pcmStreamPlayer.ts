function base64ToBytes(base64: string) {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function pcm16ToFloat32(bytes: Uint8Array) {
  const sampleCount = Math.floor(bytes.byteLength / 2);
  const output = new Float32Array(sampleCount);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let i = 0; i < sampleCount; i += 1) {
    const sample = view.getInt16(i * 2, true);
    output[i] = sample / 0x8000;
  }
  return output;
}

export class PcmStreamPlayer {
  private context: AudioContext | null = null;

  private nextStartTime = 0;

  private activeSources = new Set<AudioBufferSourceNode>();

  private async ensureContext() {
    if (!this.context) {
      this.context = new AudioContext({ latencyHint: "interactive" });
    }
    if (this.context.state !== "running") {
      await this.context.resume();
    }
    if (!this.nextStartTime || this.nextStartTime < this.context.currentTime) {
      this.nextStartTime = this.context.currentTime + 0.02;
    }
    return this.context;
  }

  async enqueue(base64Audio: string, sampleRate = 24000) {
    const context = await this.ensureContext();
    const channelData = pcm16ToFloat32(base64ToBytes(base64Audio));
    if (!channelData.length) return;
    const buffer = context.createBuffer(1, channelData.length, sampleRate);
    buffer.copyToChannel(channelData, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const startAt = Math.max(this.nextStartTime, context.currentTime + 0.01);
    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;
    this.activeSources.add(source);
    source.onended = () => {
      this.activeSources.delete(source);
    };
  }

  stop() {
    this.activeSources.forEach((source) => {
      try {
        source.stop();
      } catch {
        // Ignore nodes that have already ended.
      }
    });
    this.activeSources.clear();
    if (this.context) {
      this.nextStartTime = this.context.currentTime + 0.02;
    } else {
      this.nextStartTime = 0;
    }
  }

  async close() {
    this.stop();
    if (this.context) {
      const ctx = this.context;
      this.context = null;
      await ctx.close().catch(() => undefined);
    }
  }
}
