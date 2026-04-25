import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: api.listSettings });
  const databaseQuery = useQuery({ queryKey: ["database-status"], queryFn: api.getDatabaseStatus, refetchInterval: 30000 });
  const [ttsRate, setTtsRate] = useState(1.0);
  const [retryCount, setRetryCount] = useState(2);
  const [displayMode, setDisplayMode] = useState("text");

  useEffect(() => {
    const voiceParams = settingsQuery.data?.find((item) => item.setting_key === "voice_params")?.setting_value;
    const exceptionRules = settingsQuery.data?.find((item) => item.setting_key === "exception_rules")?.setting_value;
    if (voiceParams?.tts_rate) setTtsRate(Number(voiceParams.tts_rate));
    if (exceptionRules?.retry_count !== undefined) setRetryCount(Number(exceptionRules.retry_count));
    if (exceptionRules?.display_mode) setDisplayMode(String(exceptionRules.display_mode));
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.updateSetting("voice_params", { tts_rate: ttsRate, play_mode: "auto" });
      await api.updateSetting("exception_rules", { retry_count: retryCount, display_mode: displayMode });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] })
  });

  const restoreDefaults = useMutation({
    mutationFn: api.restoreDefaults,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
      await queryClient.invalidateQueries({ queryKey: ["knowledge-switch"] });
      await queryClient.invalidateQueries({ queryKey: ["retrieval-config"] });
    }
  });

  const clearHistory = useMutation({ mutationFn: api.clearHistory, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }) });
  const clearLongMemory = useMutation({ mutationFn: api.clearLongMemory });
  const clearKnowledgeVectors = useMutation({
    mutationFn: api.clearKnowledgeVectors,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] })
  });

  const settingsPreview = useMemo(() => JSON.stringify(settingsQuery.data ?? [], null, 2), [settingsQuery.data]);

  return (
    <PageShell title="系统配置" subtitle="数据库状态、语音参数、异常策略、危险操作清理与恢复系统默认值都在这一页完成。">
      <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <article className="space-y-4">
          <div className="soft-card p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">数据库状态卡</h3>
            <div className="rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-[var(--ink)]">数据库连接</div>
                  <div className="mt-1 text-xs text-[var(--muted)]">启动后持续轮询，方便确认系统是否稳定连接到专用数据库。</div>
                </div>
                <span className={`info-chip ${databaseQuery.data?.status === "connected" ? "info-chip-strong" : ""}`}>{databaseQuery.data?.status ?? "unknown"}</span>
              </div>
              {databaseQuery.data?.reason ? <div className="mt-3 text-xs text-[var(--danger)]">{databaseQuery.data.reason}</div> : null}
            </div>
          </div>

          <div className="soft-card p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">语音与异常策略</h3>
            <div className="grid gap-3">
              <label className="text-sm text-[var(--muted)]">
                TTS 语速
                <input className="field-input mt-1" type="number" step="0.1" min={0.5} max={2} value={ttsRate} onChange={(e) => setTtsRate(Number(e.target.value))} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                最大重试次数
                <input className="field-input mt-1" type="number" min={0} max={5} value={retryCount} onChange={(e) => setRetryCount(Number(e.target.value))} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                异常提示方式
                <select className="field-input mt-1" value={displayMode} onChange={(e) => setDisplayMode(e.target.value)}>
                  <option value="text">text</option>
                  <option value="dialog">dialog</option>
                </select>
              </label>
              <div className="flex flex-wrap gap-2">
                <button className="action-btn action-btn-primary" onClick={() => saveMutation.mutate()}>保存系统配置</button>
                <button className="action-btn action-btn-secondary" onClick={() => restoreDefaults.mutate()}>恢复系统默认</button>
              </div>
            </div>
          </div>

          <div className="soft-card p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">高危清理面板</h3>
            <div className="grid gap-2">
              <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认清空所有对话历史吗？") && clearHistory.mutate()}>清理对话历史</button>
              <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认清空长期记忆吗？") && clearLongMemory.mutate()}>清理长期记忆</button>
              <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认清理知识库向量与文档吗？") && clearKnowledgeVectors.mutate()}>清理知识库向量</button>
            </div>
          </div>
        </article>

        <article className="soft-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">当前系统配置快照</h3>
          <div className="rounded-[20px] border border-[var(--line)] bg-[#fbfdfd] p-4">
            <pre className="scroll-area max-h-[72vh] overflow-auto whitespace-pre-wrap text-xs leading-6">{settingsPreview}</pre>
          </div>
        </article>
      </div>
    </PageShell>
  );
}
