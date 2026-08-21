// Shared API types mirroring the backend Pydantic schemas.
//
// This is the USER app: every type here maps to a self-service `/account/*` response.
// Admin-only shapes (models, providers, rate-limit configs, audit, platform stats) live in
// the separate admin console and are intentionally absent — a normal session never sees them.

export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  status: string;
  plan: string;
  account_type?: string;
  admin_role?: string | null;
  admin_permissions?: string[];
  primary_org_id?: string | null;
  quota_tokens?: number | null;
  credits: number;
  email_verified: boolean;
  last_login?: string | null;
  created_at?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type?: string;
  expires_in: number;
  scope?: string;
  // Per-session AES-GCM key (standard base64). Present when payload obfuscation is enabled;
  // the client uses it directly to envelope `/account/*` traffic.
  enc_key?: string | null;
  user: User;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  user_id: string;
  project_id?: string | null;
  scopes: string[];
  status: string;
  rpm_limit?: number | null;
  tpm_limit?: number | null;
  last_used_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  key: string; // shown only once
}

export interface RequestLog {
  id: string;
  user_id?: string | null;
  project_id?: string | null;
  api_key_id?: string | null;
  model?: string | null;
  upstream_model?: string | null;
  endpoint: string;
  method: string;
  api_format: string;
  provider: string;
  status: string;
  status_code: number;
  stream: boolean;
  started_at: string;
  completed_at?: string | null;
  latency_ms: number;
  ttft_ms?: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  token_count_source: string;
  provider_request_id?: string | null;
  error_type?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface RequestDetail extends RequestLog {
  ip_hash?: string | null;
  user_agent?: string | null;
  request_content?: string | null;
  response_content?: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// `/account/analytics/overview` — the caller's own summary metrics (no platform-wide counts).
export interface Overview {
  range: { since: string; until: string };
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  rate_limited_requests: number;
  provider_errors: number;
  error_rate: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  avg_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
}

export interface TimeseriesPoint {
  ts: string;
  requests: number;
  errors: number;
  tokens: number;
  avg_latency_ms: number;
}

export interface BreakdownGroup {
  key: string;
  requests: number;
  tokens: number;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  owner_id: string;
  rpm_limit?: number | null;
  tpm_limit?: number | null;
  concurrency_limit?: number | null;
  monthly_token_quota?: number | null;
  allowed_models: string[];
  archived: boolean;
  created_at: string;
}

// ---- Usage & quota (`/account/usage/*`) -----------------------------------

export interface QuotaStatus {
  metric: string;
  limit: number | null;
  used: number;
  remaining: number | null;
  unlimited: boolean;
  period_start: string;
}

export interface UsageSummary {
  range?: { since: string; until: string };
  requests: number;
  total_tokens: number;
  cost_usd: number;
  credits_used: number;
}

export interface UsageByModelGroup {
  model: string;
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

// `/account/overview` — the home dashboard in one call.
export interface AccountOverview {
  user: User;
  organization_id: string | null;
  plan_slug: string | null;
  credit_balance: number;
  quota: QuotaStatus;
  usage_30d: UsageSummary;
  active_api_keys: number;
  projects_count: number;
}

// ---- Billing (`/account/billing/*`, read-only) ----------------------------

export interface Subscription {
  id: string;
  organization_id: string;
  plan_id: string;
  status: string;
  provider: string;
  current_period_start: string;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  trial_status: string;
  trial_start?: string | null;
  trial_end?: string | null;
  created_at: string;
  plan_slug?: string | null;
  plan_name?: string | null;
}

export interface CreditTransaction {
  id: string;
  organization_id: string;
  user_id?: string | null;
  type: string;
  amount: number;
  balance_after: number;
  reason: string;
  reference_id?: string | null;
  expires_at?: string | null;
  created_by?: string | null;
  ts: string;
}

export interface CreditBalance {
  organization_id: string;
  balance: number;
}

export interface InvoiceLineItem {
  description?: string;
  model?: string;
  quantity?: number;
  amount_usd?: number;
  [k: string]: unknown;
}

export interface Invoice {
  id: string;
  organization_id: string;
  subscription_id?: string | null;
  number: string;
  status: string;
  period_start: string;
  period_end: string;
  plan_fee_usd: number;
  usage_usd: number;
  credits_applied_usd: number;
  total_usd: number;
  line_items: InvoiceLineItem[];
  issued_at?: string | null;
  paid_at?: string | null;
  created_at: string;
}

export interface Plan {
  id: string;
  slug: string;
  name: string;
  description: string;
  active: boolean;
  archived: boolean;
  is_public: boolean;
  price_monthly_usd: number;
  price_yearly_usd: number;
  monthly_credits: number;
  trial_days: number;
  sort_order: number;
  created_at: string;
  limits: Record<string, number | null>;
  features: Record<string, unknown>;
  models: string[];
}
