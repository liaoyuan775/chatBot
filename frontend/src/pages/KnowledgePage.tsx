import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageShell } from "../components/PageShell";

export function KnowledgePage() {
  const queryClient = useQueryClient();
  const basesQuery = useQuery({ queryKey: ["knowledge-bases"], queryFn: api.listKnowledgeBases });
  const switchQuery = useQuery({ queryKey: ["knowledge-switch"], queryFn: api.getKnowledgeSwitch });
  const retrievalConfigQuery = useQuery({ queryKey: ["retrieval-config"], queryFn: api.getRetrievalConfig });

  const [selectedBaseId, setSelectedBaseId] = useState<string>("");
  const docsQuery = useQuery({
    queryKey: ["knowledge-docs", selectedBaseId],
    queryFn: () => api.listKnowledgeDocs(selectedBaseId || undefined)
  });

  const [baseForm, setBaseForm] = useState({ name: "", description: "", is_default: false });
  const [editingBaseId, setEditingBaseId] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [testQuestion, setTestQuestion] = useState("系统支持哪些功能？");
  const [uploadNotice, setUploadNotice] = useState("");
  const [retrievalConfig, setRetrievalConfig] = useState({
    top_k: 3,
    similarity_threshold: 0,
    rag_timeout_ms: 1500,
    no_result_message: "未查询到相关知识，我将为您进行通用解答。",
    embedding_provider: "siliconflow",
    embedding_model: "BAAI/bge-m3",
    rerank_provider: "siliconflow",
    rerank_model: "BAAI/bge-reranker-v2-m3"
  });

  useEffect(() => {
    if (retrievalConfigQuery.data) setRetrievalConfig(retrievalConfigQuery.data);
  }, [retrievalConfigQuery.data]);

  useEffect(() => {
    const bases = basesQuery.data ?? [];
    if (!bases.length) return;
    if (!selectedBaseId || !bases.some((item) => item.id === selectedBaseId)) {
      const defaultBase = bases.find((item) => item.is_default) ?? bases[0];
      setSelectedBaseId(defaultBase.id);
    }
  }, [basesQuery.data, selectedBaseId]);

  const createBaseMutation = useMutation({
    mutationFn: () => api.createKnowledgeBase(baseForm),
    onSuccess: async () => {
      setBaseForm({ name: "", description: "", is_default: false });
      setEditingBaseId("");
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    }
  });
  const updateBaseMutation = useMutation({
    mutationFn: () => api.updateKnowledgeBase(editingBaseId, baseForm),
    onSuccess: async () => {
      setBaseForm({ name: "", description: "", is_default: false });
      setEditingBaseId("");
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    }
  });
  const deleteBaseMutation = useMutation({
    mutationFn: (id: string) => api.deleteKnowledgeBase(id),
    onSuccess: async () => {
      setEditingBaseId("");
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      await queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] });
    }
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedFile) throw new Error("请选择文件");
      return api.createKnowledgeDoc({ file: selectedFile, knowledge_base_id: selectedBaseId || undefined });
    },
    onSuccess: async () => {
      setUploadNotice("文档上传并解析完成");
      setSelectedFile(null);
      await queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] });
    }
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteKnowledgeDoc(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] })
  });
  const reparseMutation = useMutation({
    mutationFn: (id: string) => api.reparseKnowledgeDoc(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] })
  });
  const retrievalMutation = useMutation({
    mutationFn: () => api.retrievalTest(testQuestion, retrievalConfig.top_k, retrievalConfig.similarity_threshold, selectedBaseId || undefined)
  });
  const toggleSwitchMutation = useMutation({
    mutationFn: (enabled: boolean) => api.updateKnowledgeSwitch(enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-switch"] })
  });
  const saveRetrievalConfig = useMutation({
    mutationFn: () => api.updateRetrievalConfig(retrievalConfig),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["retrieval-config"] })
  });

  const existingNames = useMemo(() => new Set((docsQuery.data ?? []).map((doc) => doc.file_name)), [docsQuery.data]);

  const startEditBase = (id: string) => {
    const target = (basesQuery.data ?? []).find((item) => item.id === id);
    if (!target) return;
    setEditingBaseId(id);
    setBaseForm({ name: target.name, description: target.description ?? "", is_default: target.is_default });
  };

  return (
    <PageShell title="知识库管理" subtitle="支持多知识库新增/编辑/删除，并按知识库维度上传、检索与重解析文档。">
      <div className="grid gap-4 xl:grid-cols-[460px_1fr]">
        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between rounded-[20px] border border-[var(--line)] bg-[#f7fbfa] px-4 py-3 text-sm">
            <div>
              <div className="font-semibold text-[var(--ink)]">知识库全局开关</div>
              <div className="text-xs text-[var(--muted)]">关闭后，对话将跳过知识库检索。</div>
            </div>
            <button
              className={`action-btn ${switchQuery.data?.enabled ? "action-btn-primary" : "action-btn-secondary"}`}
              onClick={() => toggleSwitchMutation.mutate(!switchQuery.data?.enabled)}
            >
              {switchQuery.data?.enabled ? "已开启" : "已关闭"}
            </button>
          </div>

          <div className="rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--ink)]">知识库列表</h3>
              <span className="info-chip">共 {basesQuery.data?.length ?? 0} 个</span>
            </div>
            <div className="max-h-52 space-y-2 overflow-auto pr-1">
              {(basesQuery.data ?? []).map((base) => (
                <div key={base.id} className={`rounded-[14px] border p-2 ${selectedBaseId === base.id ? "border-[var(--primary)] bg-[var(--primary-soft)]/45" : "border-[var(--line)] bg-white"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <button className="text-left" onClick={() => setSelectedBaseId(base.id)}>
                      <div className="text-sm font-semibold text-[var(--ink)]">{base.name}</div>
                      <div className="text-xs text-[var(--muted)]">{base.description || "暂无描述"}</div>
                    </button>
                    <div className="flex gap-1">
                      {base.is_default ? <span className="info-chip info-chip-strong">默认</span> : null}
                      <button className="rounded-full border border-[var(--line)] px-2 py-1 text-xs" onClick={() => startEditBase(base.id)}>编辑</button>
                      <button
                        className="rounded-full border border-[var(--line)] px-2 py-1 text-xs text-[var(--danger)]"
                        onClick={() => window.confirm("确认删除该知识库吗？") && deleteBaseMutation.mutate(base.id)}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-3 grid gap-2">
              <input className="field-input" placeholder="知识库名称" value={baseForm.name} onChange={(e) => setBaseForm({ ...baseForm, name: e.target.value })} />
              <textarea className="field-input min-h-[84px]" placeholder="知识库描述" value={baseForm.description} onChange={(e) => setBaseForm({ ...baseForm, description: e.target.value })} />
              <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
                <input type="checkbox" checked={baseForm.is_default} onChange={(e) => setBaseForm({ ...baseForm, is_default: e.target.checked })} />
                设为默认知识库
              </label>
              <div className="flex flex-wrap gap-2">
                <button className="action-btn action-btn-primary" disabled={!baseForm.name.trim()} onClick={() => (editingBaseId ? updateBaseMutation.mutate() : createBaseMutation.mutate())}>
                  {editingBaseId ? "保存修改" : "新增知识库"}
                </button>
                {editingBaseId ? (
                  <button
                    className="action-btn action-btn-secondary"
                    onClick={() => {
                      setEditingBaseId("");
                      setBaseForm({ name: "", description: "", is_default: false });
                    }}
                  >
                    取消编辑
                  </button>
                ) : null}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
            <h3 className="text-sm font-semibold text-[var(--ink)]">文档上传与覆盖提醒</h3>
            <div className="mt-2 text-xs text-[var(--muted)]">当前支持 `txt / md / pdf / pptx / docx` 文档上传。</div>
            <label className="text-sm text-[var(--muted)]">
              上传到知识库
              <select className="field-input mt-1" value={selectedBaseId} onChange={(e) => setSelectedBaseId(e.target.value)}>
                {(basesQuery.data ?? []).map((base) => <option key={base.id} value={base.id}>{base.name}</option>)}
              </select>
            </label>
            <input
              type="file"
              accept=".txt,.md,.markdown,.pdf,.pptx,.docx"
              className="field-input mt-3"
              onChange={(e) => {
                const file = e.target.files?.[0] ?? null;
                setSelectedFile(file);
                if (file && existingNames.has(file.name)) {
                  setUploadNotice(`检测到同名文件 ${file.name}，上传后将执行覆盖替换。`);
                } else {
                  setUploadNotice(file ? `待上传: ${file.name}` : "");
                }
              }}
            />
            {uploadNotice ? <div className="mt-3 rounded-[16px] border border-[var(--line)] bg-[#fbfdfd] px-3 py-2 text-sm text-[var(--muted)]">{uploadNotice}</div> : null}
            <button className="action-btn action-btn-primary mt-3" disabled={!selectedFile || uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>
              {uploadMutation.isPending ? "上传中..." : "上传并解析"}
            </button>
          </div>

          <div className="mt-4 rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
            <h3 className="text-sm font-semibold text-[var(--ink)]">检索参数设置（可手动配置）</h3>
            <div className="mt-3 grid gap-3">
              <label className="text-sm text-[var(--muted)]">
                Top K
                <input className="field-input mt-1" type="number" value={retrievalConfig.top_k} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, top_k: Number(e.target.value) })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                相似度阈值
                <input className="field-input mt-1" type="number" step="0.1" value={retrievalConfig.similarity_threshold} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, similarity_threshold: Number(e.target.value) })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                RAG 总超时（毫秒）
                <input className="field-input mt-1" type="number" min={100} value={retrievalConfig.rag_timeout_ms} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, rag_timeout_ms: Number(e.target.value) })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                Embedding Provider
                <input className="field-input mt-1" value={retrievalConfig.embedding_provider} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, embedding_provider: e.target.value })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                Embedding Model
                <input className="field-input mt-1" value={retrievalConfig.embedding_model} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, embedding_model: e.target.value })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                Rerank Provider
                <input className="field-input mt-1" value={retrievalConfig.rerank_provider} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, rerank_provider: e.target.value })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                Rerank Model
                <input className="field-input mt-1" value={retrievalConfig.rerank_model} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, rerank_model: e.target.value })} />
              </label>
              <label className="text-sm text-[var(--muted)]">
                无结果话术
                <textarea className="field-input mt-1 min-h-[90px]" value={retrievalConfig.no_result_message} onChange={(e) => setRetrievalConfig({ ...retrievalConfig, no_result_message: e.target.value })} />
              </label>
              <button className="action-btn action-btn-secondary" onClick={() => saveRetrievalConfig.mutate()}>保存检索参数</button>
            </div>
          </div>

          <div className="mt-4 rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
            <h3 className="text-sm font-semibold text-[var(--ink)]">检索测试</h3>
            <textarea className="field-input mt-3 min-h-[100px]" value={testQuestion} onChange={(e) => setTestQuestion(e.target.value)} />
            <button className="action-btn action-btn-primary mt-3" onClick={() => retrievalMutation.mutate()}>执行检索测试</button>
            {retrievalMutation.data ? (
              <pre className="mt-3 max-h-56 overflow-auto rounded-[16px] border border-[var(--line)] bg-[#fbfdfd] p-3 text-xs leading-6">{JSON.stringify(retrievalMutation.data, null, 2)}</pre>
            ) : null}
          </div>
        </article>

        <article className="soft-card p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--ink)]">文档列表</h3>
              <p className="mt-1 text-xs text-[var(--muted)]">支持按知识库查看文档状态，支持重新解析和删除。</p>
            </div>
            <span className="info-chip">共 {docsQuery.data?.length ?? 0} 份文档</span>
          </div>

          <div className="scroll-area max-h-[72vh] space-y-3 overflow-auto pr-1">
            {(docsQuery.data ?? []).map((doc) => (
              <div key={doc.id} className="rounded-[20px] border border-[var(--line)] bg-white/92 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold text-[var(--ink)]">{doc.file_name}</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="info-chip">知识库: {doc.knowledge_base_name || "未归类"}</span>
                      <span className="info-chip">类型: {doc.file_type}</span>
                      <span className={`info-chip ${doc.parse_status === "parsed" ? "info-chip-strong" : ""}`}>状态: {doc.parse_status}</span>
                      <span className="info-chip">切片: {doc.chunk_count}</span>
                      <span className="info-chip">大小: {Math.max(1, Math.round(doc.size_bytes / 1024))} KB</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="action-btn action-btn-secondary" onClick={() => reparseMutation.mutate(doc.id)}>重新解析</button>
                    <button className="action-btn action-btn-danger" onClick={() => window.confirm("确认删除该知识库文档吗？") && deleteMutation.mutate(doc.id)}>删除</button>
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
