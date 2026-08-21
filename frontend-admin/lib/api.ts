// Typed fetch client for the admin control plane (/admin/*).
//
// Two things happen at the single `request<T>()` choke point:
//  1. Bearer auth — the admin-scoped JWT from localStorage.
//  2. Payload envelope — when the server issued an `enc_key` at admin-login and WebCrypto is
//     available, request/response bodies are AES-GCM enveloped (X-Enc: 1) so console JSON never
//     appears as readable text in the Network tab. This is obfuscation on top of TLS + server
//     RBAC, never the access boundary: every /admin/* call is authorized server-side regardless.
//
// The `{error:{message,type,code}}` envelope is parsed into ApiError.

import type {
  AdminOverview,
  ApiKey,
  ApiKeyCreated,
  AuditEntry,
  BreakdownGroup,
  CreditBalance,
  CreditTransaction,
  Growth,
  HealthCheckResult,
  HealthSnapshot,
  Invoice,
  LimitOverride,
  Model,
  ModelPrice,
  OrgMember,
  Organization,
  Overview,
  Page,
  Plan,
  PlanDistribution,
  PlanHistory,
  Project,
  Provider,
  ProviderCircuit,
  RateLimitConfig,
  RateLimitEvent,
  RequestDetail,
  RequestLog,
  RiskEvent,
  SecurityEvent,
  Subscription,
  TimeseriesPoint,
  TokenResponse,
  User,
  UserDetail,
  UserStats,
} from "./types";
import { cryptoAvailable, decryptEnvelope, encryptEnvelope } from "./crypto";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TOKEN_KEY = "gw_admin_token";
const ENC_KEY = "gw_admin_enc_key";
// Auth endpoints are never enveloped (they establish the key) — keep them plaintext.
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
  const token = auth ? getToken() : null;
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const encKey = getEncKey();
  const enveloped =
    auth &&
    !!token &&
    !!encKey &&
    cryptoAvailable() &&
    path.startsWith("/admin") &&
    !path.startsWith(AUTH_PREFIX);

  let outBody: string | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    const plaintext = JSON.stringify(body);
    if (enveloped) {
      const sealed = await encryptEnvelope(encKey!, plaintext);
      if (sealed !== null) {
        outBody = sealed;
        headers["X-Enc"] = "1";
      } else {
        outBody = plaintext; // crypto unavailable at runtime — fall back to plaintext
      }
    } else {
      outBody = plaintext;
    }
  } else if (enveloped) {
    // Bodiless request (GET/POST-no-body): still ask the server to envelope its response.
    headers["X-Enc"] = "1";
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${qs(query)}`, {
      method,
      headers,
      body: outBody,
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Is the backend running?`,
      0,
      "network_error",
    );
  }

  if (res.status === 204) return undefined as T;

  let text = await res.text();

  // Decrypt an enveloped response before parsing.
  if (text && res.headers.get("X-Enc") === "1" && encKey) {
    try {
      text = await decryptEnvelope(encKey, text);
    } catch {
      throw new ApiError("Could not decrypt the server response.", res.status, "bad_envelope");
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
  // ---- Auth ---------------------------------------------------------------
  // Admin console login mints an ADMIN-scoped session; non-admins are rejected server-side.
  login: (email: string, password: string) =>
    request<TokenResponse>("/admin/auth/admin-login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  me: () => request<User>("/admin/auth/me"),
  logout: () => request<void>("/admin/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/admin/auth/change-password", {
      method: "POST",
      body: { current_password, new_password },
    }),

  // ---- Admin overview (§35-37) --------------------------------------------
  adminOverview: () => request<AdminOverview>("/admin/overview"),
  growth: (days?: number) => request<Growth>("/admin/overview/growth", { query: { days } }),
  planDistribution: () => request<PlanDistribution[]>("/admin/overview/plan-distribution"),

  // ---- Analytics (platform-wide) ------------------------------------------
  overview: (query?: Query) => request<Overview>("/admin/analytics/overview", { query }),
  timeseries: (query?: Query) =>
    request<{ bucket: string; points: TimeseriesPoint[] }>("/admin/analytics/timeseries", { query }),
  breakdown: (query?: Query) =>
    request<{ field: string; groups: BreakdownGroup[] }>("/admin/analytics/breakdown", { query }),

  // ---- Requests -----------------------------------------------------------
  listRequests: (query?: Query) => request<Page<RequestLog>>("/admin/requests", { query }),
  getRequest: (id: string) => request<RequestDetail>(`/admin/requests/${id}`),

  // ---- Users --------------------------------------------------------------
  listUsers: (query?: Query) => request<Page<User>>("/admin/users", { query }),
  createUser: (body: {
    email: string;
    password: string;
    name: string;
    role?: string;
    plan?: string;
  }) => request<User>("/admin/users", { method: "POST", body }),
  getUser: (id: string) => request<User>(`/admin/users/${id}`),
  updateUser: (id: string, body: Partial<User>) =>
    request<User>(`/admin/users/${id}`, { method: "PATCH", body }),
  deleteUser: (id: string) => request<void>(`/admin/users/${id}`, { method: "DELETE" }),
  userDetail: (id: string) => request<UserDetail>(`/admin/users/${id}/detail`),
  userStats: (id: string, days?: number) =>
    request<UserStats>(`/admin/users/${id}/stats`, { query: { days } }),
  // User lifecycle actions (§22)
  suspendUser: (id: string, reason?: string) =>
    request<User>(`/admin/users/${id}/suspend`, { method: "POST", body: { reason } }),
  unsuspendUser: (id: string, reason?: string) =>
    request<User>(`/admin/users/${id}/unsuspend`, { method: "POST", body: { reason } }),
  disableUser: (id: string, reason?: string) =>
    request<User>(`/admin/users/${id}/disable`, { method: "POST", body: { reason } }),
  restrictUser: (id: string, reason?: string) =>
    request<User>(`/admin/users/${id}/restrict`, { method: "POST", body: { reason } }),
  revokeAllKeys: (id: string) =>
    request<{ revoked: number }>(`/admin/users/${id}/revoke-all-keys`, { method: "POST" }),
  quotaReset: (id: string, body: { metric?: string; period?: string; reason?: string }) =>
    request<unknown>(`/admin/users/${id}/quota-reset`, { method: "POST", body }),
  grantUserCredits: (id: string, body: { amount: number; reason?: string; type?: string; expires_at?: string | null }) =>
    request<unknown>(`/admin/users/${id}/credits`, { method: "POST", body }),
  setAdminRole: (id: string, body: { admin_role?: string | null; admin_permissions?: string[] }) =>
    request<User>(`/admin/users/${id}/admin-role`, { method: "POST", body }),

  // ---- Organizations ------------------------------------------------------
  listOrganizations: (query?: Query) =>
    request<Page<Organization>>("/admin/organizations", { query }),
  createOrganization: (body: { name: string; owner_id: string; slug?: string | null }) =>
    request<Organization>("/admin/organizations", { method: "POST", body }),
  getOrganization: (id: string) => request<Organization>(`/admin/organizations/${id}`),
  updateOrganization: (id: string, body: { name?: string | null }) =>
    request<Organization>(`/admin/organizations/${id}`, { method: "PATCH", body }),
  setOrgStatus: (id: string, body: { status: string; reason?: string }) =>
    request<Organization>(`/admin/organizations/${id}/status`, { method: "POST", body }),
  listOrgMembers: (id: string) => request<OrgMember[]>(`/admin/organizations/${id}/members`),
  addOrgMember: (id: string, body: { user_id: string; role?: string }) =>
    request<OrgMember>(`/admin/organizations/${id}/members`, { method: "POST", body }),
  updateOrgMember: (id: string, userId: string, body: { role: string }) =>
    request<OrgMember>(`/admin/organizations/${id}/members/${userId}`, { method: "PATCH", body }),
  removeOrgMember: (id: string, userId: string) =>
    request<void>(`/admin/organizations/${id}/members/${userId}`, { method: "DELETE" }),

  // ---- Plans --------------------------------------------------------------
  listPlans: (query?: Query) => request<Plan[]>("/admin/plans", { query }),
  createPlan: (body: Partial<Plan> & { slug: string; name: string }) =>
    request<Plan>("/admin/plans", { method: "POST", body }),
  getPlan: (id: string) => request<Plan>(`/admin/plans/${id}`),
  updatePlan: (id: string, body: Partial<Plan>) =>
    request<Plan>(`/admin/plans/${id}`, { method: "PATCH", body }),
  archivePlan: (id: string) => request<Plan>(`/admin/plans/${id}/archive`, { method: "POST" }),

  // ---- Subscriptions ------------------------------------------------------
  listSubscriptions: (query?: Query) =>
    request<Page<Subscription>>("/admin/subscriptions", { query }),
  createSubscription: (body: {
    organization_id: string;
    plan_id: string;
    trial?: boolean | null;
    reason?: string;
  }) => request<Subscription>("/admin/subscriptions", { method: "POST", body }),
  getSubscription: (id: string) => request<Subscription>(`/admin/subscriptions/${id}`),
  cancelSubscription: (id: string, at_period_end = true) =>
    request<Subscription>(`/admin/subscriptions/${id}/cancel`, {
      method: "POST",
      body: { at_period_end },
    }),
  changeSubscriptionPlan: (id: string, body: { plan_id: string; reason?: string; grant_credits?: boolean }) =>
    request<Subscription>(`/admin/subscriptions/${id}/change-plan`, { method: "POST", body }),
  setSubscriptionStatus: (id: string, status: string) =>
    request<Subscription>(`/admin/subscriptions/${id}/status`, { method: "POST", body: { status } }),
  subscriptionHistory: (orgId: string, query?: Query) =>
    request<Page<PlanHistory>>(`/admin/subscriptions/history/${orgId}`, { query }),

  // ---- Credits ------------------------------------------------------------
  creditBalance: (orgId: string) =>
    request<CreditBalance>(`/admin/credits/${orgId}/balance`),
  creditLedger: (orgId: string, query?: Query) =>
    request<Page<CreditTransaction>>(`/admin/credits/${orgId}/ledger`, { query }),
  grantCredits: (orgId: string, body: { amount: number; reason?: string; type?: string; expires_at?: string | null }) =>
    request<CreditTransaction>(`/admin/credits/${orgId}/grant`, { method: "POST", body }),
  refundCredits: (orgId: string, body: { amount: number; reason?: string }) =>
    request<CreditTransaction>(`/admin/credits/${orgId}/refund`, { method: "POST", body }),
  adjustCredits: (orgId: string, body: { delta: number; reason: string }) =>
    request<CreditTransaction>(`/admin/credits/${orgId}/adjust`, { method: "POST", body }),

  // ---- Billing / invoices -------------------------------------------------
  listInvoices: (query?: Query) => request<Page<Invoice>>("/admin/billing/invoices", { query }),
  getInvoice: (id: string) => request<Invoice>(`/admin/billing/invoices/${id}`),
  generateInvoice: (body: {
    organization_id: string;
    period_start: string;
    period_end: string;
    subscription_id?: string | null;
    plan_fee_usd?: number;
  }) => request<Invoice>("/admin/billing/invoices/generate", { method: "POST", body }),
  markInvoicePaid: (id: string) =>
    request<Invoice>(`/admin/billing/invoices/${id}/mark-paid`, { method: "POST" }),
  voidInvoice: (id: string) =>
    request<Invoice>(`/admin/billing/invoices/${id}/void`, { method: "POST" }),

  // ---- Security & risk ----------------------------------------------------
  listSecurityEvents: (query?: Query) =>
    request<Page<SecurityEvent>>("/admin/security/events", { query }),
  resolveSecurityEvent: (id: string, status?: string) =>
    request<SecurityEvent>(`/admin/security/events/${id}/resolve`, { method: "POST", body: { status } }),
  listRiskEvents: (query?: Query) => request<Page<RiskEvent>>("/admin/security/risk", { query }),
  reviewRiskEvent: (id: string, status?: string) =>
    request<RiskEvent>(`/admin/security/risk/${id}/review`, { method: "POST", body: { status } }),
  runRiskSweeps: () => request<unknown>("/admin/security/risk/run-sweeps", { method: "POST" }),

  // ---- API keys -----------------------------------------------------------
  listKeys: (query?: Query) => request<ApiKey[]>("/admin/api-keys", { query }),
  getKey: (id: string) => request<ApiKey>(`/admin/api-keys/${id}`),
  revokeKey: (id: string) => request<ApiKey>(`/admin/api-keys/${id}/revoke`, { method: "POST" }),
  deleteKey: (id: string) => request<void>(`/admin/api-keys/${id}`, { method: "DELETE" }),

  // ---- Models -------------------------------------------------------------
  listModels: () => request<Model[]>("/admin/models"),
  createModel: (body: Partial<Model>) =>
    request<Model>("/admin/models", { method: "POST", body }),
  getModel: (id: string) => request<Model>(`/admin/models/${id}`),
  updateModel: (id: string, body: Partial<Model>) =>
    request<Model>(`/admin/models/${id}`, { method: "PATCH", body }),
  deleteModel: (id: string) => request<void>(`/admin/models/${id}`, { method: "DELETE" }),
  listModelPrices: () => request<ModelPrice[]>("/admin/models/prices"),
  modelPriceHistory: (id: string) => request<ModelPrice[]>(`/admin/models/${id}/prices`),
  setModelPrice: (id: string, body: { input_price_per_1m: number; output_price_per_1m: number }) =>
    request<ModelPrice>(`/admin/models/${id}/prices`, { method: "PUT", body }),

  // ---- Projects -----------------------------------------------------------
  listProjects: (query?: Query) => request<Project[]>("/admin/projects", { query }),
  createProject: (owner_id: string, body: Partial<Project>) =>
    request<Project>("/admin/projects", { method: "POST", body, query: { owner_id } }),
  getProject: (id: string) => request<Project>(`/admin/projects/${id}`),
  updateProject: (id: string, body: Partial<Project>) =>
    request<Project>(`/admin/projects/${id}`, { method: "PATCH", body }),
  deleteProject: (id: string) => request<void>(`/admin/projects/${id}`, { method: "DELETE" }),

  // ---- Rate limits --------------------------------------------------------
  planDefaults: () =>
    request<Record<string, Record<string, number>>>("/admin/rate-limits/plan-defaults"),
  listRateConfigs: (query?: Query) =>
    request<RateLimitConfig[]>("/admin/rate-limits/configs", { query }),
  upsertRateConfig: (body: Partial<RateLimitConfig>) =>
    request<RateLimitConfig>("/admin/rate-limits/configs", { method: "PUT", body }),
  deleteRateConfig: (id: string) =>
    request<void>(`/admin/rate-limits/configs/${id}`, { method: "DELETE" }),
  rateEvents: (query?: Query) =>
    request<RateLimitEvent[]>("/admin/rate-limits/events", { query }),
  listLimitOverrides: (query?: Query) =>
    request<LimitOverride[]>("/admin/rate-limits/overrides", { query }),
  createLimitOverride: (body: {
    scope_type: string;
    scope_id?: string;
    metric: string;
    value?: number | null;
    expires_at?: string | null;
    reason?: string;
  }) => request<LimitOverride>("/admin/rate-limits/overrides", { method: "POST", body }),
  deleteLimitOverride: (id: string) =>
    request<void>(`/admin/rate-limits/overrides/${id}`, { method: "DELETE" }),

  // ---- Provider -----------------------------------------------------------
  listProviders: () => request<Provider[]>("/admin/provider"),
  providerStatus: () => request<ProviderCircuit[]>("/admin/provider/status"),
  updateProvider: (id: string, body: Partial<Provider>) =>
    request<Provider>(`/admin/provider/${id}`, { method: "PATCH", body }),
  providerHealthCheck: (id: string) =>
    request<HealthCheckResult>(`/admin/provider/${id}/health-check`, { method: "POST" }),

  // ---- Audit --------------------------------------------------------------
  listAudit: (query?: Query) => request<Page<AuditEntry>>("/admin/audit", { query }),

  // ---- Health -------------------------------------------------------------
  health: () => request<HealthSnapshot>("/health", { auth: false }),
};
