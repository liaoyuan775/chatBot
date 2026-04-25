import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";

const builtInPresets: Record<string, string> = {
  dashscope: "https://dashscope.aliyuncs.com",
  volcengine: "https://ark.cn-beijing.volces.com/api/v3",
  siliconflow: "https://api.siliconflow.cn",
  openai: "https://api.openai.com/v1",
  glm: "https://open.bigmodel.cn/api/paas/v4",
  kimi: "https://api.moonshot.cn/v1",
  minimax: "https://api.minimax.chat/v1"
};

export function ProviderModelPage() {
  const queryClient = useQueryClient();
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const templatesQuery = useQuery({ queryKey: ["provider-templates"], queryFn: api.listProviderTemplates });
  const modelsQuery = useQuery({ queryKey: ["models"], queryFn: () => api.listModels() });

  const [providerName, setProviderName] = useState("dashscope");
  const [baseUrl, setBaseUrl] = useState(builtInPresets.dashscope);
  const [apiKey, setApiKey] = useState("");
  const [filterType, setFilterType] = useState("all");
  const [filterProvider, setFilterProvider] = useState("all");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [detailModelId, setDetailModelId] = useState<string>("");
  const [renameDraft, setRenameDraft] = useState<Record<string, string>>({});

  const templateMap = useMemo(() => {
    const fromApi = Object.fromEntries((templatesQuery.data ?? []).map((item) => [item.provider_name, item.base_url]));
    return { ...builtInPresets, ...fromApi };
  }, [templatesQuery.data]);

  const providerOptions = useMemo(() => {
    return Array.from(new Set([...
      Object.keys(templateMap),
      ...(providersQuery.data ?? []).map((item) => item.provider_name)
    ])).sort((a, b) => a.localeCompare(b));
  }, [providersQuery.data, templateMap]);

  const detailQuery = useQuery({
    queryKey: ["model-detail", detailModelId],
    queryFn: () => api.getModelDetail(detailModelId),
    enabled: Boolean(detailModelId)
  });

  const saveProvider = useMutation({
    mutationFn: () => api.upsertProvider(providerName, { api_key: apiKey || undefined, base_url: baseUrl, timeout_seconds: 20 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
      setApiKey("");
    }
  });
  const testProvider = useMutation({
    mutationFn: () => api.testProvider(providerName),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["providers"] })
  });
  const syncModels = useMutation({
    mutationFn: () => api.syncProviderModels(providerName),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["models"] });
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    }
  });
  const disableProvider = useMutation({
    mutationFn: () => api.disableProvider(providerName),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["models"] });
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    }
  });
  const deleteProvider = useMutation({
    mutationFn: () => api.deleteProvider(providerName),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["models"] });
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    }
  });
  const toggleModel = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.updateModelStatus(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["models"] })
  });
  const renameModel = useMutation({
    mutationFn: ({ id, alias }: { id: string; alias: string }) => api.renameModel(id, alias),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["models"] })
  });
  const batchStatus = useMutation({
    mutationFn: ({ ids, enabled }: { ids: string[]; enabled: boolean }) => api.batchUpdateModelStatus(ids, enabled),
    onSuccess: async () => {
      setSelectedModelIds([]);
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    }
  });

  const filteredModels = useMemo(() => {
    const keyword = searchKeyword.trim().toLowerCase();
    return (modelsQuery.data ?? []).filter((model) => {
      if (filterType !== "all" && model.model_type !== filterType) return false;
      if (filterProvider !== "all" && model.provider_name !== filterProvider) return false;
      if (keyword) {
        const candidate = `${model.model_name} ${model.alias ?? ""} ${model.provider_name}`.toLowerCase();
        if (!candidate.includes(keyword)) return false;
      }
      return true;
    });
  }, [filterProvider, filterType, modelsQuery.data, searchKeyword]);

  const grouped = useMemo(
    () =>
      filteredModels.reduce<Record<string, typeof filteredModels>>((acc, model) => {
        if (!acc[model.model_type]) acc[model.model_type] = [];
        acc[model.model_type]?.push(model);
        return acc;
      }, {}),
    [filteredModels]
  );

  const providerStatuses = providersQuery.data ?? [];

  return (
    <PageShell
      title="厂商与模型管理"
      subtitle="支持 DashScope、Volcengine、SiliconFlow、GLM、Kimi、MiniMax、OpenAI 等平台。"
      actions={<span className="info-chip">模型总数: {modelsQuery.data?.length ?? 0}</span>}
    >
      <div className="grid gap-4 xl:grid-cols-[380px_1fr_320px]">
        <article className="soft-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">厂商配置区</h3>
          <div className="grid gap-3">
            <label className="text-sm text-[var(--muted)]">
              厂商
              <select
                className="field-input mt-1"
                value={providerName}
                onChange={(e) => {
                  const next = e.target.value;
                  setProviderName(next);
                  setBaseUrl(templateMap[next] ?? "");
                }}
              >
                {providerOptions.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-[var(--muted)]">
              Base URL
              <input className="field-input mt-1" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              API Key
              <input
                className="field-input mt-1"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="输入后仅后端加密保存"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button className="action-btn action-btn-primary" onClick={() => saveProvider.mutate()}>
                保存配置
              </button>
              <button className="action-btn action-btn-secondary" onClick={() => testProvider.mutate()}>
                测试连通
              </button>
              <button className="action-btn action-btn-secondary" onClick={() => syncModels.mutate()}>
                同步模型
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="action-btn action-btn-secondary" onClick={() => disableProvider.mutate()}>
                禁用厂商
              </button>
              <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认删除该厂商配置吗？") && deleteProvider.mutate()}>
                删除厂商
              </button>
            </div>
          </div>

          <div className="mt-4 space-y-2">
            {providerStatuses.map((provider) => (
              <div key={provider.id} className="relative rounded-[18px] border border-[var(--line)] bg-white/90 p-3 pr-28 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-[var(--ink)]">{provider.provider_name}</div>
                    <div className="mt-1 text-xs text-[var(--muted)]">{provider.base_url}</div>
                    <div className="mt-1 text-xs text-[var(--muted)]">
                      Key: {provider.api_key_masked || "未配置"}
                    </div>
                  </div>
                </div>
                <span className={`info-chip provider-status-chip absolute right-3 top-3 ${provider.status === "connected" ? "info-chip-strong" : ""}`}>{provider.status}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="soft-card p-4">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">模型列表管理区</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">支持类型过滤、厂商过滤、批量启用/禁用、模型别名与详情查看。</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                className="field-input min-w-[220px]"
                placeholder="搜索模型名/别名"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
              />
              <select className="field-input min-w-[140px]" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                <option value="all">全部类型</option>
                {["llm", "asr", "tts", "embedding", "rerank", "image"].map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <select className="field-input min-w-[160px]" value={filterProvider} onChange={(e) => setFilterProvider(e.target.value)}>
                <option value="all">全部厂商</option>
                {providerOptions.map((provider) => (
                  <option key={provider} value={provider}>
                    {provider}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <button className="action-btn action-btn-secondary" disabled={!selectedModelIds.length} onClick={() => batchStatus.mutate({ ids: selectedModelIds, enabled: true })}>
              批量启用
            </button>
            <button className="action-btn action-btn-secondary" disabled={!selectedModelIds.length} onClick={() => batchStatus.mutate({ ids: selectedModelIds, enabled: false })}>
              批量禁用
            </button>
            <span className="info-chip">已选择 {selectedModelIds.length} 个模型</span>
          </div>

          <div className="scroll-area max-h-[68vh] space-y-4 overflow-auto pr-1">
            {Object.entries(grouped).map(([type, items]) => (
              <div key={type} className="rounded-[20px] border border-[var(--line)] bg-white/92 p-3">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">{type}</div>
                  <span className="info-chip">{items.length} 个模型</span>
                </div>
                <div className="space-y-3">
                  {items.map((model) => (
                    <div key={model.id} className="rounded-[18px] border border-[var(--line)] p-3">
                      <div className="flex items-start justify-between gap-3">
                        <label className="flex items-start gap-3">
                          <input
                            className="mt-1"
                            type="checkbox"
                            checked={selectedModelIds.includes(model.id)}
                            onChange={() =>
                              setSelectedModelIds((current) =>
                                current.includes(model.id) ? current.filter((item) => item !== model.id) : [...current, model.id]
                              )
                            }
                          />
                          <div>
                            <div className="font-semibold text-[var(--ink)]">{model.alias || model.model_name}</div>
                            <div className="mt-1 text-xs text-[var(--muted)]">
                              {model.provider_name} · {model.is_available ? "可用" : "不可用"}
                            </div>
                          </div>
                        </label>
                        <div className="flex flex-wrap gap-2">
                          <button className="rounded-full border border-[var(--line)] px-3 py-1 text-xs" onClick={() => setDetailModelId(model.id)}>
                            详情
                          </button>
                          <button className="rounded-full border border-[var(--line)] px-3 py-1 text-xs" onClick={() => toggleModel.mutate({ id: model.id, enabled: !model.is_enabled })}>
                            {model.is_enabled ? "停用" : "启用"}
                          </button>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <input
                          className="field-input"
                          value={renameDraft[model.id] ?? model.alias ?? ""}
                          onChange={(e) => setRenameDraft((current) => ({ ...current, [model.id]: e.target.value }))}
                          placeholder="设置模型别名"
                        />
                        <button className="action-btn action-btn-secondary" onClick={() => renameModel.mutate({ id: model.id, alias: renameDraft[model.id] ?? model.alias ?? model.model_name })}>
                          保存别名
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="soft-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">模型详情</h3>
          {detailQuery.data ? (
            <div className="space-y-3 text-sm">
              <div className="rounded-[18px] border border-[var(--line)] bg-white/92 p-3">
                <div className="font-semibold text-[var(--ink)]">{detailQuery.data.alias || detailQuery.data.model_name}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span className="info-chip">厂商: {detailQuery.data.provider_name}</span>
                  <span className="info-chip">类型: {detailQuery.data.model_type}</span>
                  <span className={`info-chip ${detailQuery.data.is_enabled ? "info-chip-strong" : ""}`}>
                    {detailQuery.data.is_enabled ? "已启用" : "已禁用"}
                  </span>
                </div>
              </div>
              <div className="rounded-[18px] border border-[var(--line)] bg-[#fbfdfd] p-3">
                <div className="mb-2 text-xs font-semibold tracking-[0.2em] text-[var(--muted)]">元数据</div>
                <pre className="max-h-[52vh] overflow-auto whitespace-pre-wrap text-xs leading-6">{JSON.stringify(detailQuery.data.metadata_json ?? {}, null, 2)}</pre>
              </div>
            </div>
          ) : (
            <div className="rounded-[18px] border border-dashed border-[var(--line)] p-8 text-center text-sm text-[var(--muted)]">
              从中间列表选择一个模型，就能查看它的同步元数据和当前状态。
            </div>
          )}
        </article>
      </div>
    </PageShell>
  );
}
