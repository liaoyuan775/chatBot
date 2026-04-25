import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import { api } from "../api/client";

type AuthState = {
  loading: boolean;
  authenticated: boolean;
  username: string;
  refresh: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState("");

  const refresh = async () => {
    setLoading(true);
    try {
      const result = await api.adminMe();
      setAuthenticated(Boolean(result.authenticated));
      setUsername(result.user?.username ?? "");
    } catch {
      setAuthenticated(false);
      setUsername("");
    } finally {
      setLoading(false);
    }
  };

  const login = async (user: string, password: string) => {
    await api.adminLogin({ username: user, password });
    await refresh();
  };

  const logout = async () => {
    await api.adminLogout();
    setAuthenticated(false);
    setUsername("");
  };

  useEffect(() => {
    void refresh();
  }, []);

  const value = useMemo<AuthState>(
    () => ({ loading, authenticated, username, refresh, login, logout }),
    [authenticated, loading, username]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
