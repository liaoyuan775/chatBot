import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { PageShell } from "../components/PageShell";

export function SettingsPage() {
  const { username } = useAuth();
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: api.listSettings });
  const databaseQuery = useQuery({ queryKey: ["database-status"], queryFn: api.getDatabaseStatus, refetchInterval: 30000 });
  const diagnosticsQuery = useQuery({ queryKey: ["admin-diagnostics"], queryFn: api.getDiagnostics, refetchInterval: 30000 });
  const auditLogsQuery = useQuery({ queryKey: ["admin-audit-logs"], queryFn: api.listAuditLogs, refetchInterval: 30000 });
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
  const diagnosticsPreview = useMemo(() => JSON.stringify(diagnosticsQuery.data ?? {}, null, 2), [diagnosticsQuery.data]);
  const providerRows = Array.isArray(diagnosticsQuery.data?.providers)
    ? (diagnosticsQuery.data.providers as Array<Record<string, unknown>>)
    : [];
  const recentFailures = Array.isArray((diagnosticsQuery.data?.recent_chain_errors as Record<string, unknown> | undefined)?.top_failures)
    ? (((diagnosticsQuery.data?.recent_chain_errors as Record<string, unknown> | undefined)?.top_failures as Array<Record<string, unknown>>))
    : [];
  const auditLogs = Array.isArray(auditLogsQuery.data) ? auditLogsQuery.data : [];
  const recentChainErrors = (diagnosticsQuery.data?.recent_chain_errors as Record<string, unknown> | undefined) ?? {};

  return (
    <PageShell title="系统配置" subtitle="这里既是系统设置面板，也是单租户试运行版的运行诊断中心。">
      <div className="grid gap-4 2xl:grid-cols-[420px_1fr]">
        <article className="space-y-4">
          <div className="soft-card p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">管理端状态</h3>
            <div className="grid gap-3 rounded-[20px] border border-[var(--line)] bg-white/92 p-4 text-sm text-[var(--muted)]">
              <div className="flex items-center justify-between gap-3">
                <span>当前管理员</span>
                <span className="info-chip info-chip-strong">{username || "admin"}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>运行诊断</span>
                <span className={`info-chip ${diagnosticsQuery.isError ? "" : "info-chip-strong"}`}>
                  {diagnosticsQuery.isLoading ? "加载中" : diagnosticsQuery.isError ? "异常" : "正常"}
                </span>
              </div>
              <div className="text-xs">管理端已接入最小登录保护、操作审计和运行诊断，适合单租户试运行阶段的日常维护。</div>
            </div>
          </div>

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

        <article className="grid gap-4">
          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <section className="soft-card p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-[var(--ink)]">运行诊断总览</h3>
                <span className="info-chip">{String(diagnosticsQuery.data?.status ?? "unknown")}</span>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-[18px] border border-[var(--line)] bg-white/90 p-4">
                  <div className="text-xs text-[var(--muted)]">会话消息总数</div>
                  <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">{String(diagnosticsQuery.data?.message_total ?? 0)}</div>
                </div>
                <div className="rounded-[18px] border border-[var(--line)] bg-white/90 p-4">
                  <div className="text-xs text-[var(--muted)]">系统设置项</div>
                  <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">{String(diagnosticsQuery.data?.settings_count ?? 0)}</div>
                </div>
                <div className="rounded-[18px] border border-[var(--line)] bg-white/90 p-4">
                  <div className="text-xs text-[var(--muted)]">近期链路失败数</div>
                  <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">{String(recentChainErrors.failure_count ?? 0)}</div>
                </div>
                <div className="rounded-[18px] border border-[var(--line)] bg-white/90 p-4">
                  <div className="text-xs text-[var(--muted)]">近期平均耗时</div>
                  <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">{String(recentChainErrors.avg_latency_ms ?? 0)} ms</div>
                </div>
              </div>
              {recentFailures.length ? (
                <div className="mt-4 rounded-[18px] border border-[var(--line)] bg-[#fbfdfd] p-4">
                  <div className="mb-2 text-sm font-semibold text-[var(--ink)]">最近失败摘要</div>
                  <div className="grid gap-2 text-xs text-[var(--muted)]">
                    {recentFailures.map((item, index) => (
                      <div key={`${item.reason ?? "unknown"}-${index}`} className="flex items-center justify-between gap-3 rounded-[14px] bg-white px-3 py-2">
                        <span className="truncate">{String(item.reason ?? "unknown")}</span>
                        <span className="info-chip">{String(item.count ?? 0)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>

            <section className="soft-card p-4">
              <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">Provider 健康概览</h3>
              <div className="grid gap-2">
                {providerRows.length ? (
                  providerRows.map((provider, index) => (
                    <div key={`${String(provider.provider_name ?? "provider")}-${index}`} className="rounded-[18px] border border-[var(--line)] bg-white/90 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-[var(--ink)]">{String(provider.provider_name ?? "-")}</div>
                          <div className="text-xs text-[var(--muted)]">{String(provider.base_url ?? "-")}</div>
                        </div>
                        <span className={`info-chip ${provider.status === "configured" ? "info-chip-strong" : ""}`}>{String(provider.status ?? "unknown")}</span>
                      </div>
                      <div className="mt-2 text-xs text-[var(--muted)]">
                        timeout={String(provider.timeout_seconds ?? "-")}s · api_key={provider.has_api_key ? "已配置" : "未配置"}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[18px] border border-dashed border-[var(--line)] bg-white/70 p-4 text-sm text-[var(--muted)]">
                    暂无 provider 诊断信息
                  </div>
                )}
              </div>
            </section>
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <section className="soft-card p-4">
              <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">最近审计日志</h3>
              <div className="grid gap-2">
                {auditLogs.length ? (
                  auditLogs.map((item, index) => (
                    <div key={String(item.id ?? index)} className="rounded-[18px] border border-[var(--line)] bg-white/90 p-3 text-xs text-[var(--muted)]">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold text-[var(--ink)]">{String(item.action ?? "action")}</span>
                        <span>{String(item.created_at ?? "")}</span>
                      </div>
                      <div className="mt-1">用户：{String(item.admin_username ?? "-")} · 目标：{String(item.target ?? "-")}</div>
                      <div className="mt-1">请求：{String(item.method ?? "-")} {String(item.path ?? "-")} · 状态：{String(item.status_code ?? "-")}</div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[18px] border border-dashed border-[var(--line)] bg-white/70 p-4 text-sm text-[var(--muted)]">
                    暂无审计日志
                  </div>
                )}
              </div>
            </section>

            <section className="soft-card p-4">
              <h3 className="mb-3 text-sm font-semibold text-[var(--ink)]">系统与诊断快照</h3>
              <div className="grid gap-4">
                <div className="rounded-[20px] border border-[var(--line)] bg-[#fbfdfd] p-4">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">System Settings</div>
                  <pre className="scroll-area max-h-[26vh] overflow-auto whitespace-pre-wrap text-xs leading-6">{settingsPreview}</pre>
                </div>
                <div className="rounded-[20px] border border-[var(--line)] bg-[#fbfdfd] p-4">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Diagnostics Snapshot</div>
                  <pre className="scroll-area max-h-[26vh] overflow-auto whitespace-pre-wrap text-xs leading-6">{diagnosticsPreview}</pre>
                </div>
              </div>
            </section>
          </div>
        </article>
      </div>
    </PageShell>
  );
}
