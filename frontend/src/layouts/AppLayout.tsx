import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { useAuth } from "../auth/AuthContext";

const LAST_CONFIG_ROUTE_KEY = "chatbot-last-config-route";
const DEFAULT_CONFIG_ROUTE = "/context";
const VALID_CONFIG_ROUTES = new Set(["/context", "/providers", "/chains", "/personas", "/voices", "/knowledge", "/settings"]);

const configNavItems = [
  { to: "/context", label: "上下文管理", caption: "三级记忆规则", icon: "忆" },
  { to: "/providers", label: "厂商与模型", caption: "厂商、模型、可用性", icon: "模" },
  { to: "/chains", label: "链路配置", caption: "主副链模板与绑定", icon: "链" },
  { to: "/personas", label: "人格配置", caption: "角色风格与预览", icon: "人" },
  { to: "/voices", label: "音色管理", caption: "试听、克隆、默认项", icon: "声" },
  { to: "/knowledge", label: "知识库管理", caption: "上传、检索、重解析", icon: "知" },
  { to: "/settings", label: "系统配置", caption: "数据库、策略、清理", icon: "系" }
];

function resolveConfigRoute(raw: string | null) {
  if (!raw) return DEFAULT_CONFIG_ROUTE;
  const pathname = raw.split("?")[0].split("#")[0];
  return VALID_CONFIG_ROUTES.has(pathname) ? pathname : DEFAULT_CONFIG_ROUTE;
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { authenticated, username, logout } = useAuth();
  const isChatMode = location.pathname.startsWith("/chat");

  useEffect(() => {
    if (!isChatMode) {
      window.localStorage.setItem(LAST_CONFIG_ROUTE_KEY, resolveConfigRoute(location.pathname));
    }
  }, [isChatMode, location.pathname]);

  const switchMode = () => {
    if (isChatMode) {
      const target = resolveConfigRoute(window.localStorage.getItem(LAST_CONFIG_ROUTE_KEY));
      navigate(target);
      return;
    }
    navigate("/chat");
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen px-3 py-3 md:px-5 md:py-4">
      <div className="mx-auto max-w-[1560px] fade-up">
        <header className="glass mb-3 flex items-center justify-between rounded-[24px] border border-[var(--line)] px-4 py-3 shadow-[0_10px_30px_rgba(19,57,63,0.08)] md:px-5">
          <div>
            <h1 className="font-display text-lg text-[var(--ink)] md:text-xl">智能多模态语音聊天机器人</h1>
            <p className="text-xs text-[var(--muted)]">{isChatMode ? "对话模式" : "配置模式"} · 通过循环图标切换</p>
          </div>
          <div className="flex items-center gap-2">
            {authenticated ? (
              <>
                <div className="hidden rounded-full border border-[var(--line)] bg-white/75 px-3 py-1 text-xs text-[var(--muted)] md:block">
                  管理员：{username || "admin"}
                </div>
                {!isChatMode ? (
                  <button className="action-btn action-btn-secondary px-3 py-2 text-xs" onClick={() => void handleLogout()} title="退出管理端">
                    退出登录
                  </button>
                ) : null}
              </>
            ) : null}
            <button
              className="rotate-switch-btn"
              title={isChatMode ? "切换到配置模式" : "切换到对话模式"}
              onClick={switchMode}
            >
              ↻
            </button>
          </div>
        </header>

        {isChatMode ? (
          <main className="min-h-[calc(100vh-92px)]">
            <Outlet />
          </main>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[290px_1fr]">
            <aside className="config-nav-shell p-3">
              <div className="config-nav-head">
                <div>
                  <div className="text-sm font-semibold text-[var(--ink)]">控制台导航</div>
                  <div className="text-xs text-[var(--muted)]">8 大面板完整联动</div>
                </div>
                <button className="rotate-switch-btn rotate-switch-mini" onClick={switchMode} title="切换到对话模式">
                  ↻
                </button>
              </div>

              <nav className="mt-3 grid gap-2">
                {configNavItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => clsx("config-nav-item", isActive && "config-nav-item-active")}
                  >
                    <span className="config-nav-icon">{item.icon}</span>
                    <span className="min-w-0">
                      <span className="block truncate text-[16px] font-semibold leading-6">{item.label}</span>
                      <span className="block truncate text-xs text-[var(--muted)]">{item.caption}</span>
                    </span>
                  </NavLink>
                ))}
              </nav>
            </aside>

            <main className="soft-card-strong min-h-[calc(100vh-98px)] p-4 md:p-5">
              <Outlet />
            </main>
          </div>
        )}
      </div>
    </div>
  );
}
