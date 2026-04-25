import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";
import { useChatStore } from "../store/chatStore";

export function ContextPage() {
  const queryClient = useQueryClient();
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const [activeTab, setActiveTab] = useState<"short" | "mid" | "long">("short");
  const [exportText, setExportText] = useState("");
  const configQuery = useQuery({ queryKey: ["memory-config"], queryFn: api.getMemoryConfig });
  const contextQuery = useQuery({
    queryKey: ["context", activeSessionId],
    queryFn: () => api.getSessionContext(activeSessionId!),
    enabled: Boolean(activeSessionId)
  });
  const [form, setForm] = useState({ short_turns: 6, mid_turns: 8, long_turns: 12 });

  useEffect(() => {
    if (configQuery.data) setForm(configQuery.data);
  }, [configQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => api.updateMemoryConfig(form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memory-config"] })
  });
  const clearMutation = useMutation({
    mutationFn: () => api.clearSessionContext(activeSessionId!),
    onSuccess: async () => {
      if (activeSessionId) await queryClient.invalidateQueries({ queryKey: ["context", activeSessionId] });
    }
  });
  const compressMutation = useMutation({
    mutationFn: () => api.compressSessionContext(activeSessionId!),
    onSuccess: async () => {
      if (activeSessionId) await queryClient.invalidateQueries({ queryKey: ["context", activeSessionId] });
    }
  });
  const exportMutation = useMutation({
    mutationFn: () => api.exportSessionContext(activeSessionId!),
    onSuccess: (data) => setExportText(data.content)
  });

  const currentItems = useMemo(() => {
    if (!contextQuery.data) return [];
    if (activeTab === "short") return contextQuery.data.short_term;
    if (activeTab === "mid") return contextQuery.data.mid_summary;
    return Array.from({ length: contextQuery.data.long_count }, (_, index) => ({ index: index + 1, label: `长期记忆片段 ${index + 1}` }));
  }, [activeTab, contextQuery.data]);

  return (
    <PageShell
      title="上下文管理"
      subtitle="三级记忆的配置、查看、压缩、导出与清理集中在这一页，便于按文档要求手动介入上下文。"
      actions={<span className="info-chip">当前会话: {activeSessionId ?? "未选择"}</span>}
    >
      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <article className="soft-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">三级记忆配置</h3>
          <div className="grid gap-3">
            <label className="text-sm text-[var(--muted)]">
              短期原文保留轮数
              <input className="field-input mt-1" type="number" value={form.short_turns} onChange={(e) => setForm({ ...form, short_turns: Number(e.target.value) })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              中期摘要保留轮数
              <input className="field-input mt-1" type="number" value={form.mid_turns} onChange={(e) => setForm({ ...form, mid_turns: Number(e.target.value) })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              长期记忆保留轮数
              <input className="field-input mt-1" type="number" value={form.long_turns} onChange={(e) => setForm({ ...form, long_turns: Number(e.target.value) })} />
            </label>
            <div className="rounded-[20px] border border-[var(--line)] bg-[#f8fcfb] p-3 text-sm text-[var(--muted)]">
              默认建议值为 6 / 8 / 12，既保证上下文连续性，也避免实时通话时上下文膨胀过快。
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="action-btn action-btn-primary" onClick={() => saveMutation.mutate()}>保存配置</button>
              <button className="action-btn action-btn-secondary" onClick={() => setForm({ short_turns: 6, mid_turns: 8, long_turns: 12 })}>恢复默认</button>
            </div>
          </div>

          <div className="mt-5 rounded-[20px] border border-[var(--line)] bg-white/85 p-4">
            <h4 className="text-sm font-semibold text-[var(--ink)]">手动管理动作</h4>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="action-btn action-btn-secondary" disabled={!activeSessionId} onClick={() => compressMutation.mutate()}>手动压缩上下文</button>
              <button className="action-btn action-btn-secondary" disabled={!activeSessionId} onClick={() => exportMutation.mutate()}>导出当前上下文</button>
              <button
                className="action-btn action-btn-danger"
                disabled={!activeSessionId}
                onClick={() => {
                  if (window.confirm("确认清空当前会话上下文吗？")) clearMutation.mutate();
                }}
              >
                清空当前上下文
              </button>
            </div>
          </div>
        </article>

        <article className="soft-card p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">当前会话详情</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">短期原文、中期摘要、长期记忆数量均可直接查看。</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className={`tab-btn ${activeTab === "short" ? "tab-btn-active" : ""}`} onClick={() => setActiveTab("short")}>短期原文</button>
              <button className={`tab-btn ${activeTab === "mid" ? "tab-btn-active" : ""}`} onClick={() => setActiveTab("mid")}>中期摘要</button>
              <button className={`tab-btn ${activeTab === "long" ? "tab-btn-active" : ""}`} onClick={() => setActiveTab("long")}>长期记忆</button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="metric-card"><div className="metric-label">短期条目</div><div className="metric-value">{contextQuery.data?.short_term.length ?? 0}</div></div>
            <div className="metric-card"><div className="metric-label">中期摘要</div><div className="metric-value">{contextQuery.data?.mid_summary.length ?? 0}</div></div>
            <div className="metric-card"><div className="metric-label">长期记忆</div><div className="metric-value">{contextQuery.data?.long_count ?? 0}</div></div>
          </div>

          <div className="scroll-area mt-4 max-h-[320px] space-y-3 overflow-auto pr-1">
            {currentItems.length ? (
              currentItems.map((item, index) => (
                <div key={index} className="rounded-[18px] border border-[var(--line)] bg-white/90 p-3 text-sm leading-7 text-[var(--ink)]">
                  <pre className="whitespace-pre-wrap break-words">{JSON.stringify(item, null, 2)}</pre>
                </div>
              ))
            ) : (
              <div className="rounded-[18px] border border-dashed border-[var(--line)] p-8 text-center text-sm text-[var(--muted)]">
                当前标签还没有内容，先在对话中心发起几轮对话会更容易看到效果。
              </div>
            )}
          </div>

          <div className="mt-4 rounded-[20px] border border-[var(--line)] bg-[#fbfdfd] p-4">
            <div className="mb-2 text-sm font-semibold text-[var(--ink)]">导出预览</div>
            <textarea className="field-input min-h-[180px]" value={exportText} onChange={(e) => setExportText(e.target.value)} placeholder="点击“导出当前上下文”后在这里查看导出文本。" />
          </div>
        </article>
      </div>
    </PageShell>
  );
}
