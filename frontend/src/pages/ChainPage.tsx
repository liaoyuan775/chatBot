import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";
import { emitToast } from "../store/toastBus";
import type { ChainConfig, ModelRecord } from "../types/domain";

const requiredModelFields = [
  { key: "llm_model", label: "LLM 模型", type: "llm" }
] as const;

const optionalModelFields = [
  { key: "asr_model", label: "ASR 模型（可选）", type: "asr" },
  { key: "tts_model", label: "TTS 模型（可选）", type: "tts" },
  { key: "image_model", label: "Image 模型（可选）", type: "image" }
] as const;

const retrievalModelFields = [
  { key: "embedding_model", label: "Embedding 模块", type: "embedding" },
  { key: "rerank_model", label: "Rerank 模块", type: "rerank" }
] as const;

const modelFields = [...requiredModelFields, ...optionalModelFields, ...retrievalModelFields] as const;

const fieldLabelMap: Record<string, string> = {
  llm_model: "主对话模型",
  asr_model: "ASR 模块",
  tts_model: "TTS 模块",
  image_model: "Image 扩展模型",
  embedding_model: "Embedding 模块",
  rerank_model: "Rerank 模块",
  voice_runtime_mode: "执行模式"
};

function deriveChainMode(mapping: Record<string, string> | undefined): "integrated" | "split" {
  const explicitMode = String(mapping?.voice_runtime_mode ?? "").trim().toLowerCase();
  if (explicitMode === "split-chain" || explicitMode === "split") return "split";
  if (explicitMode === "integrated-realtime" || explicitMode === "integrated") return "integrated";
  const hasSplitStage = Boolean(mapping?.asr_model?.trim() || mapping?.tts_model?.trim());
  return hasSplitStage ? "split" : "integrated";
}

function describeChainMode(mode: "integrated" | "split") {
  return mode === "split"
    ? "可拆分链路：ASR / LLM / TTS 可按阶段配置，检索继续结合 Embedding / Rerank。"
    : "一体化链路：主模型承担实时语音主流程，检索继续结合 Embedding / Rerank。";
}

function fieldLabel(key: string) {
  return fieldLabelMap[key] ?? key;
}

function emptyMapping() {
  return {
    asr_model: "",
    llm_model: "",
    embedding_model: "",
    rerank_model: "",
    tts_model: "",
    image_model: "",
    voice_runtime_mode: "integrated-realtime"
  };
}

function pickPreferredModel(models: ModelRecord[], type: string) {
  const scoped = models.filter((item) => item.model_type === type);
  return scoped.find((item) => item.is_enabled)?.model_name ?? scoped[0]?.model_name ?? "";
}

function suggestedMapping(models: ModelRecord[]) {
  return {
    asr_model: "",
    llm_model: pickPreferredModel(models, "llm"),
    embedding_model: "",
    rerank_model: "",
    tts_model: "",
    image_model: "",
    voice_runtime_mode: "integrated-realtime"
  };
}

export function ChainPage() {
  const queryClient = useQueryClient();
  const modelsQuery = useQuery({ queryKey: ["models"], queryFn: () => api.listModels() });
  const chainsQuery = useQuery({ queryKey: ["chains"], queryFn: api.listChains });
  const personasQuery = useQuery({ queryKey: ["personas"], queryFn: api.listPersonas });
  const voicesQuery = useQuery({ queryKey: ["voices"], queryFn: api.listVoices });

  const [editingId, setEditingId] = useState<string>("");
  const [validationState, setValidationState] = useState<Record<string, { is_valid: boolean; errors: string[] }>>({});
  const [form, setForm] = useState({
    name: "默认链路",
    is_default: true,
    persona_id: "",
    voice_id: "",
    mapping_json: emptyMapping()
  });

  useEffect(() => {
    if (!editingId) return;
    const current = chainsQuery.data?.find((item) => item.id === editingId);
    if (!current) return;
    setForm({
      name: current.name,
      is_default: current.is_default,
      persona_id: current.persona_id ?? "",
      voice_id: current.voice_id ?? "",
      mapping_json: {
        ...emptyMapping(),
        ...current.mapping_json
      }
    });
  }, [chainsQuery.data, editingId]);

  useEffect(() => {
    if (editingId) return;
    const models = modelsQuery.data ?? [];
    if (!models.length) return;
    const nextSuggested = suggestedMapping(models);
    setForm((current) => {
      const hasManualSelection = modelFields.some((field) => String(current.mapping_json[field.key] ?? "").trim());
      if (hasManualSelection) return current;
      const changed = modelFields.some(
        (field) => String(current.mapping_json[field.key] ?? "") !== String(nextSuggested[field.key] ?? "")
      );
      if (!changed) return current;
      return {
        ...current,
        mapping_json: {
          ...current.mapping_json,
          ...nextSuggested
        }
      };
    });
  }, [editingId, modelsQuery.data]);

  const createMutation = useMutation({
    mutationFn: () => api.createChain({ ...form, persona_id: form.persona_id || null, voice_id: form.voice_id || null }),
    onSuccess: async (data) => {
      const errors = Array.isArray(data?.errors) ? data.errors.map((item: unknown) => String(item)) : [];
      if (data?.is_valid) {
        emitToast("链路保存成功且已通过校验。", "success");
      } else if (errors.length) {
        emitToast(renderValidationSummary(errors), "error");
      }
      setEditingId("");
      setForm({ name: "默认链路", is_default: true, persona_id: "", voice_id: "", mapping_json: emptyMapping() });
      await queryClient.invalidateQueries({ queryKey: ["chains"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });
  const updateMutation = useMutation({
    mutationFn: () => api.updateChain(editingId, { ...form, persona_id: form.persona_id || null, voice_id: form.voice_id || null }),
    onSuccess: async (data) => {
      const errors = Array.isArray(data?.errors) ? data.errors.map((item: unknown) => String(item)) : [];
      if (data?.is_valid) {
        emitToast("链路修改成功且已通过校验。", "success");
      } else if (errors.length) {
        emitToast(renderValidationSummary(errors), "error");
      }
      setEditingId("");
      setForm({ name: "默认链路", is_default: true, persona_id: "", voice_id: "", mapping_json: emptyMapping() });
      await queryClient.invalidateQueries({ queryKey: ["chains"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });
  const validateMutation = useMutation({
    mutationFn: (id: string) => api.validateChain(id),
    onSuccess: async (data, chainId) => {
      const errors = Array.isArray(data?.errors) ? data.errors.map((item: unknown) => String(item)) : [];
      const isValid = Boolean(data?.is_valid);
      setValidationState((current) => ({ ...current, [chainId]: { is_valid: isValid, errors } }));
      if (isValid) {
        emitToast("链路校验通过，可正常使用。", "success");
      } else {
        const chain = chainsQuery.data?.find((item) => item.id === chainId);
        emitToast(renderValidationSummary(errors, chain), "error");
      }
      await queryClient.invalidateQueries({ queryKey: ["chains"] });
    }
  });
  const copyMutation = useMutation({
    mutationFn: (id: string) => api.copyChain(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chains"] })
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteChain(id),
    onSuccess: async () => {
      setEditingId("");
      await queryClient.invalidateQueries({ queryKey: ["chains"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });

  const modelsByType = useMemo(() => {
    const all = modelsQuery.data ?? [];
    return modelFields.reduce<Record<string, typeof all>>((acc, field) => {
      acc[field.type] = all.filter((model) => model.model_type === field.type);
      return acc;
    }, {});
  }, [modelsQuery.data]);

  const currentChainMode = deriveChainMode(form.mapping_json);
  const currentChainSummary = describeChainMode(currentChainMode);

  const renderValidationSummary = (errors: string[], chain?: ChainConfig) => {
    const mode = deriveChainMode(chain?.mapping_json);
    const prefix = mode === "split" ? "可拆分链路校验失败" : "一体化链路校验失败";
    return `${prefix}：${errors.join("；") || "至少需要主对话模型，且已配置模块必须启用。"}`;
  };

  return (
    <PageShell title="链路配置" subtitle="统一管理一体化链路与可拆分链路，并绑定人格、音色与检索模块。">
      <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">{editingId ? "编辑链路" : "新建链路"}</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">一体化链路由主模型承担实时语音主流程；可拆分链路可分别配置 ASR / LLM / TTS。两类链路都会继续结合 Embedding / Rerank。</p>
            </div>
            {editingId ? <span className="info-chip">编辑中</span> : <span className="info-chip info-chip-strong">新建模式</span>}
          </div>

          <div className="grid gap-3">
            <label className="text-sm text-[var(--muted)]">
              链路名称
              <input className="field-input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              绑定人格
              <select className="field-input mt-1" value={form.persona_id} onChange={(e) => setForm({ ...form, persona_id: e.target.value })}>
                <option value="">不绑定人格</option>
                {(personasQuery.data ?? []).map((persona) => <option key={persona.id} value={persona.id}>{persona.name}</option>)}
              </select>
            </label>
            <label className="text-sm text-[var(--muted)]">
              绑定音色
              <select className="field-input mt-1" value={form.voice_id} onChange={(e) => setForm({ ...form, voice_id: e.target.value })}>
                <option value="">不绑定音色</option>
                {(voicesQuery.data ?? []).map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 rounded-[18px] border border-[var(--line)] bg-[#f8fcfb] px-3 py-3 text-sm text-[var(--ink)]">
              <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              设为默认链路
            </label>
            <label className="text-sm text-[var(--muted)]">
              链路执行模式
              <select
                className="field-input mt-1"
                value={String(form.mapping_json.voice_runtime_mode || "integrated-realtime")}
                onChange={(e) => setForm({ ...form, mapping_json: { ...form.mapping_json, voice_runtime_mode: e.target.value } })}
              >
                <option value="integrated-realtime">一体化链路（Integrated）</option>
                <option value="split-chain">拆分链路（Split）</option>
              </select>
            </label>

            <div className="rounded-[18px] border border-[var(--line)] bg-[#f8fcfb] px-3 py-3 text-sm text-[var(--ink)]">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`info-chip ${currentChainMode === "integrated" ? "info-chip-strong" : ""}`}>{currentChainMode === "integrated" ? "一体化链路" : "可拆分链路"}</span>
                <span className="text-xs text-[var(--muted)]">{currentChainSummary}</span>
              </div>
            </div>

            <div className="grid gap-3">
              <div className="text-xs font-medium uppercase tracking-[0.14em] text-[var(--muted)]">主对话模型</div>
              {requiredModelFields.map((field) => (
                <label key={field.key} className="text-sm text-[var(--muted)]">
                  {field.label}
                  <select
                    className="field-input mt-1"
                    value={form.mapping_json[field.key]}
                    onChange={(e) => setForm({ ...form, mapping_json: { ...form.mapping_json, [field.key]: e.target.value } })}
                  >
                    <option value="">请选择 {field.label}</option>
                    {(modelsByType[field.type] ?? []).map((model) => (
                      <option key={model.id} value={model.model_name}>{model.alias || model.model_name}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>

            <div className="grid gap-3">
              <div className="text-xs font-medium uppercase tracking-[0.14em] text-[var(--muted)]">语音拆分模块</div>
              <div className="text-xs text-[var(--muted)]">一体化链路可留空 ASR / TTS；可拆分链路则按阶段单独指定。</div>
              {optionalModelFields.map((field) => (
                <label key={field.key} className="text-sm text-[var(--muted)]">
                  {field.label}
                  <select
                    className="field-input mt-1"
                    value={form.mapping_json[field.key]}
                    onChange={(e) => setForm({ ...form, mapping_json: { ...form.mapping_json, [field.key]: e.target.value } })}
                  >
                    <option value="">留空则走系统回退配置</option>
                    {(modelsByType[field.type] ?? []).map((model) => (
                      <option key={model.id} value={model.model_name}>{model.alias || model.model_name}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>

            <div className="rounded-[18px] border border-[var(--line)] bg-[#fbfdfd] px-3 py-3 text-sm text-[var(--muted)]">
              <div className="font-medium text-[var(--ink)]">检索模块</div>
              <div className="mt-1">无论是一体化链路还是可拆分链路，知识检索都会继续结合 Embedding / Rerank 配置。</div>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {retrievalModelFields.map((field) => (
                  <div key={field.key} className="rounded-[14px] border border-[var(--line)] bg-white px-3 py-2">
                    <div className="text-xs text-[var(--muted)]">{field.label}</div>
                    <div className="mt-1 text-[var(--ink)]">{form.mapping_json[field.key] || "未在链路中单独配置"}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button className="action-btn action-btn-primary" onClick={() => (editingId ? updateMutation.mutate() : createMutation.mutate())}>{editingId ? "保存链路" : "创建链路"}</button>
              <button className="action-btn action-btn-secondary" onClick={() => { setEditingId(""); setForm({ name: "默认链路", is_default: true, persona_id: "", voice_id: "", mapping_json: emptyMapping() }); }}>重置表单</button>
            </div>
          </div>
        </article>

        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">链路列表</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">支持校验、复制、删除、设默认，并查看一体化/可拆分链路状态。</p>
            </div>
            <span className="info-chip">共 {chainsQuery.data?.length ?? 0} 条链路</span>
          </div>

          <div className="scroll-area max-h-[70vh] space-y-3 overflow-auto pr-1">
            {(chainsQuery.data ?? []).map((chain) => (
              <div key={chain.id} className="rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-base font-semibold text-[var(--ink)]">{chain.name}</h4>
                      {chain.is_default ? <span className="info-chip info-chip-strong">默认链路</span> : null}
                      <span className={`info-chip ${chain.is_valid ? "info-chip-strong" : ""}`}>{chain.is_valid ? "链路可用" : "待校验/不可用"}</span>
                      <span className={`info-chip ${deriveChainMode(chain.mapping_json) === "integrated" ? "info-chip-strong" : ""}`}>
                        {deriveChainMode(chain.mapping_json) === "split" ? "可拆分链路" : "一体化链路"}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-[var(--muted)]">{describeChainMode(deriveChainMode(chain.mapping_json))}</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="info-chip">人格: {chain.persona_id || "未绑定"}</span>
                      <span className="info-chip">音色: {chain.voice_id || "未绑定"}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="action-btn action-btn-secondary" onClick={() => setEditingId(chain.id)}>编辑</button>
                    <button className="action-btn action-btn-secondary" onClick={() => validateMutation.mutate(chain.id)}>校验</button>
                    <button className="action-btn action-btn-secondary" onClick={() => copyMutation.mutate(chain.id)}>复制</button>
                    <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认删除该链路吗？") && deleteMutation.mutate(chain.id)}>删除</button>
                  </div>
                </div>
                {validationState[chain.id] && !validationState[chain.id].is_valid ? (
                  <div className="mt-3 rounded-[12px] border border-[#fecdca] bg-[#fff4ed] px-3 py-2 text-xs text-[#b42318]">
                    校验原因：{renderValidationSummary(validationState[chain.id].errors, chain)}
                  </div>
                ) : null}
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {Object.entries(chain.mapping_json).map(([key, value]) => (
                    <div key={key} className="rounded-[16px] border border-[var(--line)] bg-[#fbfdfd] px-3 py-2 text-sm">
                      <div className="text-xs text-[var(--muted)]">{fieldLabel(key)}</div>
                      <div className="mt-1 font-medium text-[var(--ink)]">{value || "未配置"}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </article>
      </div>
    </PageShell>
  );
}
