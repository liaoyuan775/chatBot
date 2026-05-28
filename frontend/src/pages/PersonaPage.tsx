import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";
import { emitToast } from "../store/toastBus";

export function PersonaPage() {
  const queryClient = useQueryClient();
  const personasQuery = useQuery({ queryKey: ["personas"], queryFn: api.listPersonas });
  const [editingId, setEditingId] = useState("");
  const [previewPrompt, setPreviewPrompt] = useState("请用 2 句话介绍你的回答风格。");
  const [previewReply, setPreviewReply] = useState("");
  const [form, setForm] = useState({
    name: "专业知识助手",
    is_default: true,
    config_json: {
      role: "assistant",
      style: "严谨专业",
      tone: "温和清晰",
      strictness: "high",
      allow_question_back: false,
      unknown_answer: "这个问题我暂时没有可靠依据，我可以继续为你查证。"
    }
  });

  useEffect(() => {
    if (!editingId) return;
    const current = personasQuery.data?.find((item) => item.id === editingId);
    if (!current) return;
    setForm({
      name: current.name,
      is_default: current.is_default,
      config_json: {
        role: String(current.config_json.role ?? "assistant"),
        style: String(current.config_json.style ?? "严谨专业"),
        tone: String(current.config_json.tone ?? "温和清晰"),
        strictness: String(current.config_json.strictness ?? "high"),
        allow_question_back: Boolean(current.config_json.allow_question_back),
        unknown_answer: String(current.config_json.unknown_answer ?? "这个问题我暂时没有可靠依据，我可以继续为你查证。")
      }
    });
  }, [editingId, personasQuery.data]);

  const createMutation = useMutation({
    mutationFn: () => api.createPersona(form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["personas"] })
  });
  const updateMutation = useMutation({
    mutationFn: () => api.updatePersona(editingId, form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["personas"] })
  });
  const copyMutation = useMutation({
    mutationFn: (id: string) => api.copyPersona(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["personas"] })
  });
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewMutation = useMutation({
    mutationFn: (id: string) => api.previewPersona(id, previewPrompt),
    onMutate: () => {
      setPreviewReply("");
      setPreviewLoading(true);
    },
    onSuccess: (data) => {
      setPreviewReply(data.reply);
      setPreviewLoading(false);
    },
    onError: (error: unknown) => {
      setPreviewLoading(false);
      const message = error instanceof Error ? error.message : "预览请求失败";
      setPreviewReply(`[预览失败] ${message}`);
      emitToast(`人格预览失败: ${message}`, "error");
    }
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deletePersona(id),
    onSuccess: async () => {
      setEditingId("");
      await queryClient.invalidateQueries({ queryKey: ["personas"] });
      await queryClient.invalidateQueries({ queryKey: ["chains"] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  });

  return (
    <PageShell title="人格配置" subtitle="角色定位、语气风格、回复约束与实时问答预览，全部收拢到这一页。">
      <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">{editingId ? "编辑人格" : "新建人格"}</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">默认人格会在新会话创建时自动继承。</p>
            </div>
            {editingId ? <span className="info-chip">编辑中</span> : null}
          </div>

          <div className="grid gap-3">
            <label className="text-sm text-[var(--muted)]">
              人格名称
              <input className="field-input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              角色定位
              <input className="field-input mt-1" value={String(form.config_json.role)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, role: e.target.value } })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              风格标签
              <input className="field-input mt-1" value={String(form.config_json.style)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, style: e.target.value } })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              语气
              <input className="field-input mt-1" value={String(form.config_json.tone)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, tone: e.target.value } })} />
            </label>
            <label className="text-sm text-[var(--muted)]">
              严谨程度
              <select className="field-input mt-1" value={String(form.config_json.strictness)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, strictness: e.target.value } })}>
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
              </select>
            </label>
            <label className="flex items-center gap-2 rounded-[18px] border border-[var(--line)] bg-[#f8fcfb] px-3 py-3 text-sm text-[var(--ink)]">
              <input type="checkbox" checked={Boolean(form.config_json.allow_question_back)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, allow_question_back: e.target.checked } })} />
              允许反问用户
            </label>
            <label className="flex items-center gap-2 rounded-[18px] border border-[var(--line)] bg-[#f8fcfb] px-3 py-3 text-sm text-[var(--ink)]">
              <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              设为默认人格
            </label>
            <label className="text-sm text-[var(--muted)]">
              未知问题话术
              <textarea className="field-input mt-1 min-h-[120px]" value={String(form.config_json.unknown_answer)} onChange={(e) => setForm({ ...form, config_json: { ...form.config_json, unknown_answer: e.target.value } })} />
            </label>
            <div className="flex flex-wrap gap-2">
              <button className="action-btn action-btn-primary" onClick={() => (editingId ? updateMutation.mutate() : createMutation.mutate())}>{editingId ? "保存人格" : "创建人格"}</button>
              <button className="action-btn action-btn-secondary" onClick={() => { setEditingId(""); setPreviewReply(""); }}>取消编辑</button>
            </div>
          </div>
        </article>

        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">人格列表与预览</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">复制、删除、实时问答预览都在右侧完成。</p>
            </div>
            <span className="info-chip">共 {personasQuery.data?.length ?? 0} 个</span>
          </div>

          <label className="mb-4 block text-sm text-[var(--muted)]">
            预览问题
            <textarea className="field-input mt-1 min-h-[90px]" value={previewPrompt} onChange={(e) => setPreviewPrompt(e.target.value)} />
          </label>

          <div className="scroll-area max-h-[46vh] space-y-3 overflow-auto pr-1">
            {(personasQuery.data ?? []).map((persona) => (
              <div key={persona.id} className="rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-base font-semibold text-[var(--ink)]">{persona.name}</h4>
                      {persona.is_default ? <span className="info-chip info-chip-strong">默认人格</span> : null}
                    </div>
                    <div className="mt-2 text-sm text-[var(--muted)]">风格: {String(persona.config_json.style ?? "未设置")} · 语气: {String(persona.config_json.tone ?? "未设置")}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="action-btn action-btn-secondary" onClick={() => setEditingId(persona.id)}>编辑</button>
                    <button className="action-btn action-btn-secondary" onClick={() => copyMutation.mutate(persona.id)}>复制</button>
                    <button className="action-btn action-btn-secondary" onClick={() => previewMutation.mutate(persona.id)}>预览</button>
                    <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认删除该人格吗？") && deleteMutation.mutate(persona.id)}>删除</button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-[20px] border border-[var(--line)] bg-[#fbfdfd] p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--ink)]">
              <span>实时问答预览结果</span>
              {previewLoading ? <span className="text-xs text-[var(--muted)]">加载中...</span> : null}
            </div>
            <textarea className="field-input min-h-[160px]" value={previewReply} onChange={(e) => setPreviewReply(e.target.value)} placeholder={previewLoading ? "正在请求大模型..." : "点击某个人格卡片上的\"预览\"，这里会显示实时回答。"} />
          </div>
        </article>
      </div>
    </PageShell>
  );
}
