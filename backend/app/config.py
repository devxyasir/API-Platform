"""Application configuration loaded from environment variables (.env)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "LLM Gateway"
    debug: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Secrets ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    api_key_pepper: str = "change-me-pepper"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./gateway.db"
    auto_create_tables: bool = True
    db_echo: bool = False

    # --- Redis ---
    redis_url: str = ""

    # --- Upstream provider ---
    upstream_provider: str = "openai"
    upstream_base_url: str = "https://api.openai.com/v1"
    upstream_api_key: str = ""
    upstream_auth_mode: Literal["bearer", "header", "none"] = "bearer"
    upstream_auth_header: str = "Authorization"
    upstream_timeout: float = 120.0
    upstream_max_retries: int = 2

    # --- Notrack upstream (anonymous debate API, https://notrack.ai) ---
    # Keyless service: no auth is sent. Debate knobs mirror the dispatch body.
    notrack_base_url: str = "https://notrack.ai"
    notrack_mode: str = "usual"
    notrack_persona: str = "normal"
    notrack_max_turns: int = 6

    # --- Privacy / logging ---
    log_request_content: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    ip_hash_salt: str = "change-me-ip-salt"
    # How long raw request logs (RequestLog) are retained before the cleanup worker
    # deletes them. Usage/aggregate/audit/credit/invoice rows are NEVER deleted (§48).
    raw_request_retention_days: int = 90

    # --- Security / obfuscation (dashboard surfaces only; /v1 stays OpenAI-compatible) ---
    # AES-GCM payload envelope for the dashboard/console APIs. When a client opts in
    # (X-Enc: 1), request and response bodies travel as ciphertext instead of JSON, so
    # the Network tab shows opaque blobs. This is obfuscation layered on top of TLS +
    # server-side authorization — NOT a substitute for either (a user with the running
    # app can still derive their own key). The real access boundary is the server.
    payload_encryption_enabled: bool = True
    # Response fingerprint: strip the real Server/X-Powered-By and emit decoys so an
    # attacker can't tell the stack is FastAPI/Python/uvicorn.
    decoy_headers_enabled: bool = True
    decoy_server: str = "cloudflare"
    decoy_powered_by: str = "PHP/8.4.22"

    # --- Default plan limits ---
    default_rpm: int = 60
    default_rph: int = 1000
    default_rpd: int = 10000
    default_tpm: int = 100000
    default_tpd: int = 2_000_000
    default_concurrency: int = 5
    global_concurrency: int = 100

    # --- Accounts / subscriptions / billing ---
    # Plan slug assigned to newly registered accounts; the very first user (deployment
    # owner) gets `first_user_plan_slug` instead.
    default_plan_slug: str = "free"
    first_user_plan_slug: str = "enterprise"
    # Real pre-flight gate on a plan's monthly_token_quota (the rate-limiter's tpm/tpd are
    # soft/peek-only, so quota cannot rely on it — see chat_service enforcement).
    token_quota_enforced: bool = True
    # When true, requests are additionally gated on the organization's credit balance and
    # each completed request consumes credits alongside a ledger entry. Off for personal use.
    credits_enforced: bool = False
    # Credit cost model: how many tokens one credit covers. credits_used for a request is
    # ceil(total_tokens / credit_tokens_per_unit). Credits stay a SEPARATE unit from tokens
    # and money (§58); this is only the conversion used to charge the ledger.
    credit_tokens_per_unit: int = 1000
    # Start new subscriptions in a trial when the chosen plan defines trial_days > 0.
    trial_enabled: bool = False
    # Billing simulation (no real payment provider is contacted).
    billing_provider: Literal["manual"] = "manual"
    billing_currency: str = "USD"

    # --- First-party chat product ---
    # System prompt prepended to every first-party chat (the /account/chat surface).
    chat_system_prompt: str = (
        "You are a helpful, friendly assistant. Answer clearly and concisely, "
        "use Markdown for formatting, and prefer fenced code blocks for code."
    )
    # Default public model used when a request names none / the user has no preference.
    # NOTE: this is a real, safety-aligned model on the deployment owner's own account.
    chat_default_model: str = "gpt-4o-mini"
    # Embeddings power long-term memory + semantic recall. All recall is best-effort:
    # if disabled or the upstream is unavailable, chat still works without it.
    embeddings_enabled: bool = True
    embedding_model: str = "text-embedding-3-small"
    recall_top_k_memories: int = 5
    recall_top_k_snippets: int = 4
    # Rolling summarization kicks in once a conversation exceeds this many messages,
    # so even low-context models keep a coherent thread.
    summary_trigger_messages: int = 20
    # Auto-extract durable memories from finished turns (best-effort, metered).
    memory_extraction_enabled: bool = True
    # Context budget = model.context_window - reserved_output - margin. Optional blocks
    # (memories, recall, summary) are dropped first when the budget is tight.
    reserved_output_tokens: int = 1024
    context_margin_tokens: int = 512
    # Attachments (markitdown doc/image->text; images as vision parts only when the model
    # supports vision). Auto-disabled at runtime if the markitdown import fails.
    attachments_enabled: bool = True
    max_attachment_bytes: int = 10 * 1024 * 1024
    max_attachment_text_chars: int = 200_000

    # --- Bootstrap admin ---
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrator"

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins or self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def use_redis(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL used by Alembic migrations."""
        url = self.database_url
        url = url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
