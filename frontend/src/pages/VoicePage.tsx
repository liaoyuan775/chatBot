import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";
import { getMicSupportError } from "../runtime/voice/micSupport";
import { emitToast } from "../store/toastBus";

const MAX_SAMPLE_SECONDS = 30;
const RECOMMENDED_SAMPLE_SECONDS_TEXT = "8-10";

type FeedbackKind = "success" | "error" | "info";

const DEFAULT_VOICE_FORM = {
  name: "温柔女声 A",
  voice_type: "system",
  is_default: true,
  is_enabled: true,
  config_json: {
    voice_name: "FunAudioLLM/CosyVoice2-0.5B:alex",
    sample_source: ""
  }
};

function sanitizeVoicePayload(
  form: typeof DEFAULT_VOICE_FORM,
  options?: { keepSampleState?: boolean }
) {
  const config = { ...form.config_json };
  if (!options?.keepSampleState) {
    delete (config as Record<string, unknown>).sample_source;
    delete (config as Record<string, unknown>).sample_source_type;
    delete (config as Record<string, unknown>).sample_updated_at;
    delete (config as Record<string, unknown>).clone_uri;
    delete (config as Record<string, unknown>).clone_error;
    delete (config as Record<string, unknown>).clone_reference_text;
    delete (config as Record<string, unknown>).clone_provider;
    delete (config as Record<string, unknown>).clone_model;
  }
  return {
    ...form,
    config_json: config
  };
}

export function VoicePage() {
  const queryClient = useQueryClient();
  const voicesQuery = useQuery({ queryKey: ["voices"], queryFn: api.listVoices });
  const [editingId, setEditingId] = useState("");
  const [previewText, setPreviewText] = useState("你好，这是一段音色试听文本，用来确认当前音色是否符合预期。");
  const [sampleFileName, setSampleFileName] = useState("");
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [pendingSampleFile, setPendingSampleFile] = useState<File | null>(null);
  const [referenceText, setReferenceText] = useState("");
  const [sampleFeedback, setSampleFeedback] = useState<{ message: string; kind: FeedbackKind } | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<number | null>(null);
  const recordingTickRef = useRef<number | null>(null);
  const recordingStartAtRef = useRef<number>(0);

  const [form, setForm] = useState(DEFAULT_VOICE_FORM);

  const resetSampleSelection = () => {
    setPendingSampleFile(null);
    setSampleFileName("");
    setReferenceText("");
    setSampleFeedback(null);
    setForm((current) => ({ ...current, config_json: { ...current.config_json, sample_source: "" } }));
  };

  const clearRecordingTimers = () => {
    if (recordingTimerRef.current !== null) {
      window.clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (recordingTickRef.current !== null) {
      window.clearInterval(recordingTickRef.current);
      recordingTickRef.current = null;
    }
  };

  const showSampleFeedback = (message: string, kind: FeedbackKind, toast = true) => {
    const text = message.trim();
    if (!text) return;
    setSampleFeedback({ message: text, kind });
    if (toast) emitToast(text, kind);
  };

  useEffect(() => {
    if (!editingId) {
      resetSampleSelection();
      return;
    }
    const current = voicesQuery.data?.find((item) => item.id === editingId);
    if (!current) return;
    setForm({
      name: current.name,
      voice_type: current.voice_type,
      is_default: current.is_default,
      is_enabled: current.is_enabled,
      config_json: {
        ...current.config_json,
        voice_name: String(current.config_json.voice_name ?? current.name),
        sample_source: String(current.config_json.sample_source ?? "")
      }
    });
    setSampleFileName(String(current.config_json.sample_source ?? ""));
    setReferenceText(String(current.config_json.clone_reference_text ?? ""));
    setPendingSampleFile(null);
  }, [editingId, voicesQuery.data]);

  useEffect(() => {
    return () => {
      clearRecordingTimers();
    };
  }, []);

  const readAudioDuration = (file: File) =>
    new Promise<number>((resolve, reject) => {
      const objectUrl = URL.createObjectURL(file);
      const audio = new Audio();
      audio.preload = "metadata";
      audio.onloadedmetadata = () => {
        const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
        URL.revokeObjectURL(objectUrl);
        resolve(duration);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(objectUrl);
        reject(new Error("无法读取音频元数据"));
      };
      audio.src = objectUrl;
    });

  const prepareSampleFile = async (file: File) => {
    let duration: number | null = null;
    try {
      duration = await readAudioDuration(file);
      if (duration > MAX_SAMPLE_SECONDS) {
        showSampleFeedback(
          `样本时长 ${duration.toFixed(1)} 秒，超过 ${MAX_SAMPLE_SECONDS} 秒上限。请截取 ${RECOMMENDED_SAMPLE_SECONDS_TEXT} 秒单人清晰语音后重试。`,
          "error"
        );
        setPendingSampleFile(null);
        return false;
      }
    } catch {
      showSampleFeedback("无法读取音频时长，将继续上传并由后端校验。", "info");
    }
    setPendingSampleFile(file);
    setSampleFileName(file.name);
    setForm((current) => ({ ...current, config_json: { ...current.config_json, sample_source: file.name } }));
    if (duration !== null) {
      showSampleFeedback(`已选择样本：${file.name}（${duration.toFixed(1)} 秒）`, "info", false);
    } else {
      showSampleFeedback(`已选择样本：${file.name}`, "info", false);
    }
    return true;
  };

  const prepareRecordedFile = (file: File, durationSeconds: number) => {
    if (durationSeconds > MAX_SAMPLE_SECONDS) {
      showSampleFeedback(`录音时长 ${durationSeconds.toFixed(1)} 秒，超过 ${MAX_SAMPLE_SECONDS} 秒上限，请重录。`, "error");
      setPendingSampleFile(null);
      return false;
    }
    setPendingSampleFile(file);
    setSampleFileName(file.name);
    setForm((current) => ({ ...current, config_json: { ...current.config_json, sample_source: file.name } }));
    showSampleFeedback(`录音样本已就绪：${durationSeconds.toFixed(1)} 秒`, "info", false);
    return true;
  };

  const getErrorMessage = (error: unknown) => {
    if (typeof error === "string") return error;
    if (error && typeof error === "object") {
      const maybe = error as { message?: string; response?: { data?: { detail?: unknown } } };
      const detail = maybe.response?.data?.detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        const lines = detail
          .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg?: unknown }).msg ?? "") : ""))
          .filter(Boolean);
        if (lines.length) return lines.join("；");
      }
      if (typeof maybe.message === "string" && maybe.message.trim()) return maybe.message;
    }
    return "上传失败，请稍后重试。";
  };

  const uploadSampleForVoice = async (voiceId: string, file: File, sourceType: "upload" | "record") => {
    try {
      const resp = await api.uploadVoiceSample(voiceId, file, file.name, sourceType, {
        clone: true,
        reference_text: referenceText.trim() || undefined
      });
      const message = resp.clone_uri
        ? (resp.message || "样本上传并克隆完成")
        : (resp.clone_error || resp.message || "样本上传完成，但克隆失败");
      const kind: FeedbackKind = resp.clone_uri ? "success" : "error";
      showSampleFeedback(message, kind);
      setSampleFileName(file.name);
      if (resp.clone_reference_text) setReferenceText(resp.clone_reference_text);
      if (!resp.clone_uri && file.name.toLowerCase().endsWith(".wav") && !referenceText.trim()) {
        showSampleFeedback(`${message} 建议先填写与音频完全一致的参考文本再重试；若仍失败，请把 WAV 转成单声道 16-bit PCM。`, kind, false);
      }
      setPendingSampleFile(null);
      await queryClient.invalidateQueries({ queryKey: ["voices"] });
    } catch (error) {
      showSampleFeedback(getErrorMessage(error), "error");
      throw error;
    }
  };

  const createMutation = useMutation({
    mutationFn: () => api.createVoice(sanitizeVoicePayload(form, { keepSampleState: Boolean(pendingSampleFile) })),
    onSuccess: async (data) => {
      if (pendingSampleFile) {
        await uploadSampleForVoice(data.id, pendingSampleFile, "upload");
      }
      setEditingId(data.id);
      await queryClient.invalidateQueries({ queryKey: ["voices"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });
  const updateMutation = useMutation({
    mutationFn: () => api.updateVoice(editingId, form),
    onSuccess: async () => {
      if (editingId && pendingSampleFile) {
        await uploadSampleForVoice(editingId, pendingSampleFile, "upload");
      }
      await queryClient.invalidateQueries({ queryKey: ["voices"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });
  const cloneMutation = useMutation({
    mutationFn: (id: string) => api.cloneVoice(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["voices"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });
  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.renameVoice(id, name),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["voices"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });
  const previewMutation = useMutation({
    mutationFn: (id: string) => api.previewVoice(id, previewText),
    onSuccess: (data) => {
      const mime = data.audio_mime || "audio/wav";
      const audio = new Audio(`data:${mime};base64,${data.audio_base64}`);
      void audio.play();
    }
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteVoice(id),
    onSuccess: async () => {
      setEditingId("");
      await queryClient.invalidateQueries({ queryKey: ["voices"] });
      await queryClient.invalidateQueries({ queryKey: ["chains"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });

  const uploadPendingSample = async () => {
    if (!pendingSampleFile) {
      showSampleFeedback("请先选择样本文件", "info");
      return;
    }
    if (!editingId) {
      showSampleFeedback("请先创建或选中一个音色，再上传样本", "error");
      return;
    }
    await uploadSampleForVoice(editingId, pendingSampleFile, "upload");
  };

  const stopRecording = () => {
    clearRecordingTimers();
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  };

  const startRecording = async () => {
    if (recording) return;
    const micError = getMicSupportError();
    if (micError) {
      showSampleFeedback(micError, "error");
      return;
    }
    if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
      showSampleFeedback("当前浏览器不支持在线录制，请改用本地上传。", "error");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
      const supportedMime = mimeCandidates.find((item) => MediaRecorder.isTypeSupported(item));
      const recorder = supportedMime ? new MediaRecorder(stream, { mimeType: supportedMime }) : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recordChunksRef.current = [];
      recordingStartAtRef.current = Date.now();
      setRecordingSeconds(0);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        clearRecordingTimers();
        recorderRef.current = null;
        setRecording(false);
        setRecordingSeconds(0);

        if (!recordChunksRef.current.length) {
          showSampleFeedback("录音失败，未采集到音频数据。", "error");
          return;
        }

        const durationSeconds = Math.max(0.1, (Date.now() - recordingStartAtRef.current) / 1000);
        const mimeType = recorder.mimeType || "audio/webm";
        const extension = mimeType.includes("mp4") ? "m4a" : "webm";
        const blob = new Blob(recordChunksRef.current, { type: mimeType });
        const file = new File([blob], `record-${Date.now()}.${extension}`, { type: mimeType });

        const accepted = prepareRecordedFile(file, durationSeconds);
        if (!accepted) return;

        if (editingId) {
          await uploadSampleForVoice(editingId, file, "record");
        } else {
          showSampleFeedback("录音已完成，请先创建或选中一个音色后再上传。", "info");
        }
      };

      recorder.start();
      setRecording(true);
      showSampleFeedback("录音已开始，请保持单人清晰发音。", "info");

      recordingTickRef.current = window.setInterval(() => {
        setRecordingSeconds(Math.floor((Date.now() - recordingStartAtRef.current) / 1000));
      }, 1000);

      recordingTimerRef.current = window.setTimeout(() => {
        showSampleFeedback(`录音达到 ${MAX_SAMPLE_SECONDS} 秒上限，已自动停止。建议样本时长 ${RECOMMENDED_SAMPLE_SECONDS_TEXT} 秒。`, "info");
        stopRecording();
      }, MAX_SAMPLE_SECONDS * 1000);
    } catch {
      clearRecordingTimers();
      setRecording(false);
      showSampleFeedback("无法开启麦克风，请检查浏览器录音权限。", "error");
    }
  };

  return (
    <PageShell title="音色管理" subtitle="系统音色、默认音色、试听、重命名、克隆，以及录制 / 上传样本统一管理。">
      <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">{editingId ? "编辑音色" : "新增音色"}</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">默认音色会自动绑定到新会话。样本上传后会写入当前音色配置。</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                className="action-btn action-btn-secondary"
                type="button"
                onClick={() => {
                  setEditingId("");
                  setForm(DEFAULT_VOICE_FORM);
                  resetSampleSelection();
                }}
              >
                新建音色
              </button>
              {editingId ? <span className="info-chip">编辑中</span> : null}
            </div>
          </div>

          <div className="grid gap-3">
            <label className="text-sm text-[var(--muted)]">
              音色名称
              <input className="field-input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              音色类型
              <select className="field-input mt-1" value={form.voice_type} onChange={(e) => setForm({ ...form, voice_type: e.target.value })}>
                <option value="system">system</option>
                <option value="custom">custom</option>
              </select>
            </label>
            <label className="text-sm text-[var(--muted)]">
              试听音色标识
              <input className="field-input mt-1" value={String(form.config_json.voice_name)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, voice_name: e.target.value } })} />
            </label>
            <label className="flex items-center gap-2 rounded-[18px] border border-[var(--line)] bg-[#f8fcfb] px-3 py-3 text-sm text-[var(--ink)]">
              <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              设为默认音色
            </label>
            <label className="flex items-center gap-2 rounded-[18px] border border-[var(--line)] bg-[#f8fcfb] px-3 py-3 text-sm text-[var(--ink)]">
              <input type="checkbox" checked={form.is_enabled} onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })} />
              音色可用
            </label>
          </div>

          <div className="mt-5 rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
            <h4 className="text-sm font-semibold text-[var(--ink)]">音色样本</h4>
            <p className="mt-1 text-xs text-[var(--muted)]">建议 {RECOMMENDED_SAMPLE_SECONDS_TEXT} 秒，最大 {MAX_SAMPLE_SECONDS} 秒，仅单人清晰语音。</p>
            {recording ? <p className="mt-1 text-xs text-[#0f766e]">录音中：{recordingSeconds}s / {MAX_SAMPLE_SECONDS}s</p> : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <button className={`action-btn ${recording ? "action-btn-danger" : "action-btn-secondary"}`} onClick={() => (recording ? stopRecording() : void startRecording())}>
                {recording ? "停止录制" : "在线录制样本"}
              </button>
              <label className="action-btn action-btn-secondary">
                本地上传样本
                <input
                  hidden
                  type="file"
                  accept="audio/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.currentTarget.value = "";
                    if (!file) return;
                    void (async () => {
                      const accepted = await prepareSampleFile(file);
                      if (!accepted) return;
                      if (editingId) {
                        await uploadSampleForVoice(editingId, file, "upload");
                      } else {
                        showSampleFeedback("样本已选择。请先创建或选中音色，再点击“上传到当前音色”。", "info");
                      }
                    })();
                  }}
                />
              </label>
              <button className="action-btn action-btn-primary" onClick={() => void uploadPendingSample()}>
                上传到当前音色
              </button>
            </div>
            <label className="mt-3 block text-sm text-[var(--muted)]">
              参考文本（可选，留空则自动识别）
              <textarea className="field-input mt-1 min-h-[96px]" value={referenceText} onChange={(e) => setReferenceText(e.target.value)} placeholder="建议填写和样本音频完全一致的文字，这样克隆更稳定。" />
            </label>
            <div className="mt-3 text-sm text-[var(--muted)]">当前样本: {sampleFileName || "尚未选择样本"}</div>
            {sampleFeedback ? (
              <div className={`mt-2 text-xs ${sampleFeedback.kind === "error" ? "text-[#b42318]" : sampleFeedback.kind === "success" ? "text-[#0f766e]" : "text-[var(--muted)]"}`}>
                {sampleFeedback.message}
              </div>
            ) : null}
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <button className="action-btn action-btn-primary" onClick={() => (editingId ? updateMutation.mutate() : createMutation.mutate())}>{editingId ? "保存音色" : "创建音色"}</button>
            {editingId ? <button className="action-btn action-btn-secondary" onClick={() => renameMutation.mutate({ id: editingId, name: form.name })}>仅重命名</button> : null}
          </div>
        </article>

        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">音色列表与试听</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">支持试听、克隆、删除限制提示和默认音色切换。</p>
            </div>
            <span className="info-chip">共 {voicesQuery.data?.length ?? 0} 个音色</span>
          </div>

          <label className="mb-4 block text-sm text-[var(--muted)]">
            试听文本
            <textarea className="field-input mt-1 min-h-[100px]" value={previewText} onChange={(e) => setPreviewText(e.target.value)} />
          </label>

          <div className="scroll-area max-h-[54vh] space-y-3 overflow-auto pr-1">
            {(voicesQuery.data ?? []).map((voice) => (
              <div key={voice.id} className="rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-base font-semibold text-[var(--ink)]">{voice.name}</h4>
                      {voice.is_default ? <span className="info-chip info-chip-strong">默认音色</span> : null}
                      <span className={`info-chip ${voice.is_enabled ? "info-chip-strong" : ""}`}>{voice.is_enabled ? "已启用" : "已停用"}</span>
                    </div>
                    <div className="mt-2 text-sm text-[var(--muted)]">{voice.voice_type} · 样本来源: {String(voice.config_json.sample_source ?? "系统内置")}</div>
                    {voice.config_json.clone_uri ? (
                      <div className="mt-1 text-xs text-[var(--muted)]">已克隆: {String(voice.config_json.clone_uri)}</div>
                    ) : null}
                    {voice.config_json.clone_error ? (
                      <div className="mt-1 text-xs text-[#b54708]">克隆失败: {String(voice.config_json.clone_error)}</div>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="action-btn action-btn-secondary" onClick={() => setEditingId(voice.id)}>编辑</button>
                    <button className="action-btn action-btn-secondary" onClick={() => previewMutation.mutate(voice.id)}>试听</button>
                    <button className="action-btn action-btn-secondary" onClick={() => cloneMutation.mutate(voice.id)}>克隆</button>
                    <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认删除该音色吗？如果它被链路或会话使用，会自动回退到默认音色。") && deleteMutation.mutate(voice.id)}>删除</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>
      </div>
    </PageShell>
  );
}
