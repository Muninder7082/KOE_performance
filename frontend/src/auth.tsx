import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { get, post, setCsrfToken, setUnauthorizedHandler } from "./api";
import { setAppTimezone } from "./format";
import type { SettingsResponse, User } from "./types";

type AuthState = {
  user: User | null;
  loading: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}

async function loadTimezone() {
  try {
    const s = await get<SettingsResponse>("/api/settings");
    setAppTimezone(s.settings.timezone);
  } catch {
    /* keep default */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await get<{ user: User; csrf_token: string }>("/api/auth/me");
      setCsrfToken(me.csrf_token);
      await loadTimezone();
      setUser(me.user);
    } catch {
      setUser(null);
      setCsrfToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setCsrfToken(null);
    });
    refresh();
  }, [refresh]);

  const login = async (email: string, password: string) => {
    const res = await post<{ user: User; csrf_token: string }>("/api/auth/login", { email, password });
    setCsrfToken(res.csrf_token);
    await loadTimezone();
    setUser(res.user);
  };

  const logout = async () => {
    try {
      await post("/api/auth/logout");
    } finally {
      setCsrfToken(null);
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, isAdmin: user?.role === "admin", login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
