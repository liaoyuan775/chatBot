import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedAdminRoute({ children }: { children: ReactElement }) {
  const { loading, authenticated } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="p-8 text-sm text-[var(--muted)]">正在检查管理员登录状态...</div>;
  }
  if (!authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
