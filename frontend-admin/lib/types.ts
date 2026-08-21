// Shared API types mirroring the backend Pydantic schemas (admin console).

export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  status: string;
  plan: string;
  account_type: string;
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

export interface Model {
  id: string;
  public_id: string;
  display_name: string;
  description: string;
  provider: string;
  upstream_model: string;
  enabled: boolean;
  supports_streaming: boolean;
  context_window: number;
  max_output_tokens?: number | null;
  aliases: string[];
  is_default: boolean;
  input_price_per_1m: number;
  output_price_per_1m: number;
}

export interface ModelPrice {
  id: string;
  model_public_id: string;
  input_price_per_1m: number;
  output_price_per_1m: number;
  effective_from: string;
  effective_until?: string | null;
  created_by?: string | null;
  ts: string;
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
  active_users?: number;
  active_api_keys?: number;
  total_users?: number;
  total_api_keys?: number;
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

export interface RateLimitConfig {
  id: string;
  scope_type: string;
  scope_id: string;
  rpm?: number | null;
  rph?: number | null;
  rpd?: number | null;
  tpm?: number | null;
  tpd?: number | null;
  concurrency?: number | null;
}

export interface RateLimitEvent {
  id: string;
  user_id?: string | null;
  project_id?: string | null;
  api_key_id?: string | null;
  limit_type: string;
  scope: string;
  limit_value: number;
  ts: string;
}

export interface LimitOverride {
  id: string;
  scope_type: string;
  scope_id: string;
  metric: string;
  value?: number | null;
  expires_at?: string | null;
  reason: string;
  created_by?: string | null;
  created_at: string;
}

export interface Provider {
  id: string;
  name: string;
  provider_type: string;
  enabled: boolean;
  base_url: string;
  auth_mode: string;
  key_masked: string;
  timeout: number;
  max_retries: number;
  model_mapping: Record<string, unknown>;
  last_status: string;
  last_latency_ms?: number | null;
  last_checked_at?: string | null;
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

export interface AuditEntry {
  id: string;
  actor_id?: string | null;
  actor_email?: string | null;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  meta: Record<string, unknown>;
  ip_hash?: string | null;
  ts: string;
}

export interface HealthSnapshot {
  status: string;
  app: string;
  env: string;
  time: string;
  database: string;
  cache: string;
  upstream_circuit: string;
}

export interface UserStats extends Overview {
  top_models: BreakdownGroup[];
  top_endpoints: BreakdownGroup[];
  last_active: string | null;
}

export interface ProviderCircuit {
  provider: string;
  circuit_state: string;
  consecutive_failures: number;
}

export interface HealthCheckResult {
  provider: string;
  healthy: boolean;
  latency_ms: number | null;
  checked_at: string;
}

// ---- Organizations --------------------------------------------------------
export interface Organization {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  status: string;
  is_personal: boolean;
  credit_balance: number;
  created_at: string;
}

export interface OrgMember {
  id: string;
  organization_id: string;
  user_id: string;
  role: string;
  status: string;
  joined_at: string;
}

// ---- Plans & subscriptions ------------------------------------------------
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
  limits?: Record<string, number | null>;
  features?: Record<string, unknown>;
  models?: string[];
}

export interface PlanHistory {
  id: string;
  organization_id: string;
  user_id?: string | null;
  old_plan?: string | null;
  new_plan: string;
  changed_by?: string | null;
  reason: string;
  ts: string;
}

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

// ---- Credits & billing ----------------------------------------------------
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
  amount_usd?: number;
  [key: string]: unknown;
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
  line_items?: InvoiceLineItem[];
  issued_at?: string | null;
  paid_at?: string | null;
  created_at: string;
}

// ---- Security & risk ------------------------------------------------------
export interface SecurityEvent {
  id: string;
  user_id?: string | null;
  organization_id?: string | null;
  type: string;
  status: string;
  severity: string;
  ip_hash?: string | null;
  user_agent?: string | null;
  meta?: Record<string, unknown>;
  resolved_at?: string | null;
  resolved_by?: string | null;
  ts: string;
}

export interface RiskEvent {
  id: string;
  user_id?: string | null;
  organization_id?: string | null;
  type: string;
  severity: string;
  score: number;
  status: string;
  detail?: Record<string, unknown>;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  ts: string;
}

// ---- Quota / usage summaries ----------------------------------------------
export interface QuotaStatus {
  metric: string;
  limit: number | null;
  used: number;
  remaining: number | null;
  unlimited: boolean;
  period_start: string;
}

export interface UsageSummary {
  requests: number;
  total_tokens: number;
  cost_usd: number;
  credits_used: number;
}

// ---- Admin overview (§35-37) ----------------------------------------------
export interface AdminOverview {
  users: { total: number; active: number };
  organizations: { total: number };
  subscriptions: { active: number };
  revenue: { estimated_mrr_usd: number; credit_liability: number };
  usage_30d: UsageSummary;
  queues: { open_security_events: number; open_risk_events: number };
}

export interface PlanDistribution {
  plan_slug: string;
  plan_name: string;
  subscriptions: number;
}

export interface GrowthPoint {
  date: string;
  new_users: number;
}

export interface Growth {
  since: string;
  days: number;
  series: GrowthPoint[];
  total_new: number;
}

// ---- User detail (§21/§44) ------------------------------------------------
export interface UserDetail {
  user: User;
  organization?: Organization | null;
  subscription?: Subscription | null;
  plan_slug?: string | null;
  plan_name?: string | null;
  credit_balance?: number;
  quota?: QuotaStatus | null;
  usage_30d?: UsageSummary | null;
  projects_count?: number;
  api_keys_count?: number;
  effective_permissions?: string[];
}
