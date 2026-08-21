"use client";

// Client-side auth for the ADMIN console. Holds the admin-scoped JWT + current user and
// exposes login/logout/refresh. The token + payload key live in localStorage (via lib/api)
// so the session survives reloads.
//
// This console is LOGIN-ONLY: there is no registration. The first platform admin is created
// by registering in the main user app (first user auto-becomes super_admin) and then signing
// in here through /admin/auth/admin-login, which mints an admin-scoped session.
//
// Defence in depth: the server already rejects non-admins at admin-login and gates every
// /admin/* route by scope + RBAC. On top of that we refuse to *render* the console for any
// identity that isn't a platform admin — so even a smuggled user-scoped token shows nothing.

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

// A platform admin is anyone with the coarse admin role or a granular admin_role assignment.
// This mirrors admin_service.is_platform_admin on the server; it is a UI gate, not the
// access boundary (the server authorizes every request regardless of what we render).
export function isPlatformAdmin(u: User | null | undefined): boolean {
  return !!u && (u.role === "admin" || !!u.admin_role);
}

interface AuthState {
  user: User | null;
  loading: boolean; // true while we resolve the stored token on first mount
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Drop every trace of the session: token + payload key + in-memory user.
  const forget = useCallback(() => {
    clearToken();
    clearEncKey();
    setUser(null);
  }, []);

  // On first mount, if a token exists, resolve the current user — but only accept it if the
  // identity is a platform admin. A non-admin token is forgotten immediately.
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
        if (!active) return;
        if (isPlatformAdmin(u)) {
          setUser(u);
        } else {
          clearToken();
          clearEncKey();
          setUser(null);
        }
      })
      .catch(() => {
        clearToken();
        clearEncKey();
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
    // Guard against any identity that somehow authenticated but isn't a platform admin.
    if (!isPlatformAdmin(res.user)) {
      throw new Error("This account does not have admin access.");
    }
    setToken(res.access_token);
    setEncKey(res.enc_key); // enables the payload envelope on subsequent /admin calls
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    // Best-effort server logout; the local session is cleared regardless.
    api.logout().catch(() => undefined);
    forget();
  }, [forget]);

  const refresh = useCallback(async () => {
    try {
      const u = await api.me();
      if (isPlatformAdmin(u)) setUser(u);
      else forget();
    } catch {
      forget();
    }
  }, [forget]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
