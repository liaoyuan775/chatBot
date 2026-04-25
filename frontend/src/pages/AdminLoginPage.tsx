import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function AdminLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const nextPath = (location.state as { from?: string } | null)?.from ?? "/providers";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(username, password);
      navigate(nextPath, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen px-4 py-8">
      <div className="mx-auto max-w-[520px] soft-card-strong p-6">
        <div className="mb-6">
          <h1 className="font-display text-[1.8rem] text-[var(--ink)]">管理员登录</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            当前系统已切换为单租户试运行模式。聊天页可继续使用，管理端需管理员登录后访问。
          </p>
        </div>

        <form className="grid gap-4" onSubmit={handleSubmit}>
          <label className="text-sm text-[var(--muted)]">
            用户名
            <input className="field-input mt-1" value={username} onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="text-sm text-[var(--muted)]">
            密码
            <input className="field-input mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error ? <div className="rounded-[14px] border border-[var(--line)] bg-white/90 px-3 py-2 text-sm text-[var(--danger)]">{error}</div> : null}
          <button className="action-btn action-btn-primary" disabled={submitting || !username.trim() || !password.trim()} type="submit">
            {submitting ? "登录中..." : "登录管理端"}
          </button>
        </form>
      </div>
    </div>
  );
}
