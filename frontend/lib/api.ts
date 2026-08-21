// Typed fetch client for the self-service account API.
//
// Two things make this different from a plain JSON client:
//  1. It talks to `/account/*` (the user surface). Auth bootstrap (login/register/logout)
//     stays on `/admin/auth/*` — those mint a user-scoped token and are shared with the
//     admin console. A user-scoped token is rejected from every other `/admin/*` route.
//  2. Payloads are obfuscated with an AES-GCM envelope (see lib/crypto). After login we hold
//     a per-session key (`enc_key`); authenticated `/account/*` calls send `X-Enc: 1` with a
//     base64url ciphertext body and receive the response the same way, so nothing readable
//     shows up in the Network tab. This is obfuscation, never the access boundary — the
//     server enforces scope/RBAC regardless.

import { cryptoAvailable, decryptEnvelope, encryptEnvelope } from "./crypto";
import type {
  AccountOverview,
  ApiKey,
  ApiKeyCreated,
  BreakdownGroup,
  CreditBalance,
  CreditTransaction,
  Invoice,
  Overview,
  Page,
  Plan,
  Project,
  QuotaStatus,
  RequestDetail,
  RequestLog,
  Subscription,
  TimeseriesPoint,
  TokenResponse,
  UsageByModelGroup,
  UsageSummary,
  User,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TOKEN_KEY = "gw_token";
const ENC_KEY = "gw_enc_key";

// Auth-bootstrap endpoints are never enveloped: login/register have no key yet, and logout
// is harmless in plaintext. Everything else authenticated under /account (or /admin) is.
const AUTH_PREFIX = "/admin/auth/";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export function getEncKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ENC_KEY);
}

export function setEncKey(key: string | null | undefined): void {
  if (typeof window === "undefined") return;
  if (key) window.localStorage.setItem(ENC_KEY, key);
  else window.localStorage.removeItem(ENC_KEY);
}

export function clearEncKey(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(ENC_KEY);
}

export class ApiError extends Error {
  status: number;
  code?: string;
  type?: string;
  constructor(message: string, status: number, code?: string, type?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.type = type;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

function qs(params?: Query): string {
  if (!params) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Query;
  auth?: boolean; // default true
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, auth = true } = opts;
  const headers: Record<string, string> = {};
  const encKey = getEncKey();

  // Envelope when we have a key, the call is authenticated, and it targets an enveloped
  // surface that isn't an auth-bootstrap endpoint.
  const enveloped =
    auth &&
    !!encKey &&
    cryptoAvailable() &&
    (path.startsWith("/account") || path.startsWith("/admin")) &&
    !path.startsWith(AUTH_PREFIX);

  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let outBody: BodyInit | undefined;
  if (body !== undefined) {
    const json = JSON.stringify(body);
    // Keep Content-Type: application/json so FastAPI parses the DECRYPTED body as JSON.
    headers["Content-Type"] = "application/json";
    if (enveloped) {
      const enc = await encryptEnvelope(encKey as string, json);
      if (enc !== null) {
        outBody = enc;
        headers["X-Enc"] = "1";
      } else {
        outBody = json; // crypto unexpectedly unavailable → plaintext (server still accepts)
      }
    } else {
      outBody = json;
    }
  } else if (enveloped) {
    // No request body, but still opt in so the RESPONSE comes back enveloped.
    headers["X-Enc"] = "1";
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${qs(query)}`, { method, headers, body: outBody });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Is the backend running?`,
      0,
      "network_error",
    );
  }

  if (res.status === 204) return undefined as T;

  let text = await res.text();
  // Decrypt if the server enveloped its response (its own 401/400 envelope errors are plain).
  if (text && res.headers.get("X-Enc") === "1" && encKey) {
    try {
      text = await decryptEnvelope(encKey, text);
    } catch {
      throw new ApiError("Failed to decrypt the server response.", res.status, "bad_envelope");
    }
  }

  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const env = data as { error?: { message?: string; code?: string; type?: string } };
    const err = env?.error;
    throw new ApiError(
      err?.message || res.statusText || "Request failed",
      res.status,
      err?.code,
      err?.type,
    );
  }

  return data as T;
}

export const api = {
  // ---- Auth (shared bootstrap, mints a user-scoped token) -----------------
  login: (email: string, password: string) =>
    request<TokenResponse>("/admin/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  register: (email: string, password: string, name: string) =>
    request<TokenResponse>("/admin/auth/register", {
      method: "POST",
      body: { email, password, name },
      auth: false,
    }),
  me: () => request<User>("/account/me"),
  updateProfile: (body: { name?: string }) =>
    request<User>("/account/me", { method: "PATCH", body }),
  logout: () => request<void>("/admin/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/account/change-password", {
      method: "POST",
      body: { current_password, new_password },
    }),

  // ---- Home dashboard -----------------------------------------------------
  accountOverview: () => request<AccountOverview>("/account/overview"),

  // ---- API keys -----------------------------------------------------------
  listKeys: () => request<ApiKey[]>("/account/api-keys"),
  createKey: (body: {
    name: string;
    scopes?: string[];
    project_id?: string | null;
    expires_in_days?: number | null;
    rpm_limit?: number | null;
    tpm_limit?: number | null;
  }) => request<ApiKeyCreated>("/account/api-keys", { method: "POST", body }),
  revokeKey: (id: string) =>
    request<ApiKey>(`/account/api-keys/${id}/revoke`, { method: "POST" }),
  rotateKey: (id: string) =>
    request<ApiKeyCreated>(`/account/api-keys/${id}/rotate`, { method: "POST" }),
  deleteKey: (id: string) =>
    request<void>(`/account/api-keys/${id}`, { method: "DELETE" }),

  // ---- Projects -----------------------------------------------------------
  listProjects: () => request<Project[]>("/account/projects"),
  createProject: (body: Partial<Project>) =>
    request<Project>("/account/projects", { method: "POST", body }),
  updateProject: (id: string, body: Partial<Project>) =>
    request<Project>(`/account/projects/${id}`, { method: "PATCH", body }),
  deleteProject: (id: string) =>
    request<void>(`/account/projects/${id}`, { method: "DELETE" }),

  // ---- Requests -----------------------------------------------------------
  listRequests: (query?: Query) =>
    request<Page<RequestLog>>("/account/requests", { query }),
  getRequest: (id: string) => request<RequestDetail>(`/account/requests/${id}`),

  // ---- Analytics ----------------------------------------------------------
  overview: (query?: Query) => request<Overview>("/account/analytics/overview", { query }),
  timeseries: (query?: Query) =>
    request<{ points: TimeseriesPoint[] }>("/account/analytics/timeseries", { query }),
  breakdown: (query?: Query) =>
    request<{ groups: BreakdownGroup[] }>("/account/analytics/breakdown", { query }),

  // ---- Usage & quota ------------------------------------------------------
  quota: () => request<QuotaStatus>("/account/usage/quota"),
  usageSummary: (query?: Query) =>
    request<UsageSummary>("/account/usage/summary", { query }),
  usageByModel: (query?: Query) =>
    request<{ range: { since: string; until: string }; groups: UsageByModelGroup[] }>(
      "/account/usage/by-model",
      { query },
    ),

  // ---- Billing (read-only) ------------------------------------------------
  subscription: () => request<Subscription | null>("/account/billing/subscription"),
  credits: () => request<CreditBalance>("/account/billing/credits"),
  creditLedger: (query?: Query) =>
    request<Page<CreditTransaction>>("/account/billing/credits/ledger", { query }),
  invoices: (query?: Query) =>
    request<Page<Invoice>>("/account/billing/invoices", { query }),
  getInvoice: (id: string) => request<Invoice>(`/account/billing/invoices/${id}`),
  plans: () => request<Plan[]>("/account/billing/plans"),
};
