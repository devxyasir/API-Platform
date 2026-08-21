"use client";

// Client-side auth: holds the JWT + current user, exposes login/register/logout.
// The token and the per-session envelope key live in localStorage (via lib/api) so they
// survive reloads; both are cleared together on logout or a failed session resolve.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, clearEncKey, clearToken, getToken, setEncKey, setToken } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean; // true while we resolve the stored token on first mount
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, name: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function forget() {
  clearToken();
  clearEncKey();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On first mount, if a token exists, resolve the current user. The stored envelope key
  // (if any) lets api.me() ride the encrypted channel transparently.
  useEffect(() => {
    let active = true;
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((u) => {
        if (active) setUser(u);
      })
      .catch(() => {
        forget();
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    setEncKey(res.enc_key); // enable the encrypted channel for subsequent calls
    setUser(res.user);
    return res.user;
  }, []);

  const register = useCallback(
    async (email: string, password: string, name: string) => {
      const res = await api.register(email, password, name);
      setToken(res.access_token);
      setEncKey(res.enc_key);
      setUser(res.user);
      return res.user;
    },
    [],
  );

  const logout = useCallback(() => {
    // Best-effort server logout; the token + key are cleared locally regardless.
    api.logout().catch(() => undefined);
    forget();
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.me());
    } catch {
      forget();
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
