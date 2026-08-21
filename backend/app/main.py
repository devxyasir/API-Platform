"""Application entry point: wires configuration, middleware, routers and lifespan.

Run locally with:  uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.account import analytics as account_analytics
from app.api.account import api_keys as account_api_keys
from app.api.account import billing as account_billing
from app.api.account import profile as account_profile
from app.api.account import projects as account_projects
from app.api.account import requests as account_requests
from app.api.account import usage as account_usage
from app.api.admin import api_keys as admin_api_keys
from app.api.admin import audit as admin_audit
from app.api.admin import auth as admin_auth
from app.api.admin import billing as admin_billing
from app.api.admin import credits as admin_credits
from app.api.admin import models as admin_models
from app.api.admin import organizations as admin_organizations
from app.api.admin import overview as admin_overview
from app.api.admin import plans as admin_plans
from app.api.admin import projects as admin_projects
from app.api.admin import provider as admin_provider
from app.api.admin import rate_limits as admin_rate_limits
from app.api.admin import requests as admin_requests
from app.api.admin import security as admin_security
from app.api.admin import subscriptions as admin_subscriptions
from app.api.admin import usage as admin_usage
from app.api.admin import users as admin_users
from app.api.v1 import chat as v1_chat
from app.api.v1 import conversations as v1_conversations
from app.api.v1 import messages as v1_messages
from app.api.v1 import models as v1_models
from app.api.v1 import usage as v1_usage
from app.config import settings
from app.database import SessionLocal, create_all
from app.errors import install_exception_handlers
from app.logging_config import configure_logging, get_logger
from app.middleware.envelope import EnvelopeMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.providers import registry
from app.rate_limit import backend as rate_backend
from app.workers.scheduler import scheduler

configure_logging()
logger = get_logger("app.main")

OPENAPI_TAGS = [
    {"name": "Chat", "description": "OpenAI-compatible chat completions (/v1)."},
    {"name": "Messages", "description": "Anthropic-compatible messages (/v1)."},
    {"name": "Models", "description": "Model registry."},
    {"name": "Conversations", "description": "Stored conversations (/v1)."},
    {"name": "Usage", "description": "Usage summaries for API consumers."},
    {"name": "Authentication", "description": "Dashboard login & account."},
    {"name": "Account", "description": "Self-service: your profile & dashboard."},
    {"name": "Account API Keys", "description": "Self-service: your API keys."},
    {"name": "Account Projects", "description": "Self-service: your projects."},
    {"name": "Account Usage", "description": "Self-service: your usage & quota."},
    {"name": "Account Analytics", "description": "Self-service: your analytics."},
    {"name": "Account Requests", "description": "Self-service: your request history."},
    {"name": "Account Billing", "description": "Self-service: your subscription, credits & invoices."},
    {"name": "Overview", "description": "Admin overview & platform analytics."},
    {"name": "Users", "description": "User administration."},
    {"name": "Organizations", "description": "Organizations & members."},
    {"name": "Projects", "description": "Projects / workspaces."},
    {"name": "Plans", "description": "Subscription-plan catalogue."},
    {"name": "Subscriptions", "description": "Organization subscriptions & plan history."},
    {"name": "Credits", "description": "Credit ledger & balances."},
    {"name": "Billing", "description": "Invoices & billing simulation."},
    {"name": "API Keys", "description": "API key lifecycle."},
    {"name": "Requests", "description": "Request explorer."},
    {"name": "Analytics", "description": "Usage analytics & metrics."},
    {"name": "Rate Limits", "description": "Rate-limit configuration & events."},
    {"name": "Security", "description": "Security & risk events."},
    {"name": "Provider", "description": "Upstream provider status & settings."},
    {"name": "Audit", "description": "Security audit log."},
    {"name": "Health", "description": "Liveness & readiness probes."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup_begin", extra={"env": settings.app_env})
    registry.startup()
    if settings.auto_create_tables:
        await create_all()
    async with SessionLocal() as session:
        from app.bootstrap import run_bootstrap
        await run_bootstrap(session)
    scheduler.start()
    logger.info("startup_complete")
    try:
        yield
    finally:
        logger.info("shutdown_begin")
        await scheduler.stop()
        await registry.shutdown()
        await rate_backend.close()
        logger.info("shutdown_complete")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "A self-hosted, OpenAI/Anthropic-compatible gateway to your own OpenAI account, "
        "with API keys, rate limiting, usage accounting and a management dashboard."
    ),
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Middleware -------------------------------------------------------------
# Stack (outermost → innermost):  RequestContext → CORS → Envelope → app.
# - RequestContext (outer): request id, decoy/security headers, access log — stamps the
#   final (possibly encrypted) response.
# - CORS: preflight + CORS headers.
# - Envelope (inner, closest to routes): decrypts opted-in dashboard request bodies and
#   encrypts their responses. Innermost so it sees plain JSON from the routes and so the
#   OpenAI/Anthropic /v1 surface (which it ignores) is never buffered.
app.add_middleware(EnvelopeMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-Enc", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
)
app.add_middleware(RequestContextMiddleware)

install_exception_handlers(app)

# --- Routers ----------------------------------------------------------------
# OpenAI/Anthropic-compatible consumer API.
app.include_router(v1_chat.router, prefix="/v1")
app.include_router(v1_messages.router, prefix="/v1")
app.include_router(v1_models.router, prefix="/v1")
app.include_router(v1_conversations.router, prefix="/v1")
app.include_router(v1_usage.router, prefix="/v1")

# Management dashboard API (JWT-authenticated).
app.include_router(admin_auth.router, prefix="/admin")
app.include_router(admin_overview.router, prefix="/admin")
app.include_router(admin_users.router, prefix="/admin")
app.include_router(admin_organizations.router, prefix="/admin")
app.include_router(admin_projects.router, prefix="/admin")
app.include_router(admin_plans.router, prefix="/admin")
app.include_router(admin_subscriptions.router, prefix="/admin")
app.include_router(admin_credits.router, prefix="/admin")
app.include_router(admin_billing.router, prefix="/admin")
app.include_router(admin_api_keys.router, prefix="/admin")
app.include_router(admin_models.router, prefix="/admin")
app.include_router(admin_requests.router, prefix="/admin")
app.include_router(admin_usage.router, prefix="/admin")
app.include_router(admin_rate_limits.router, prefix="/admin")
app.include_router(admin_security.router, prefix="/admin")
app.include_router(admin_provider.router, prefix="/admin")
app.include_router(admin_audit.router, prefix="/admin")

# Self-service account API (user-scoped). Every endpoint is strictly scoped to the
# authenticated caller and their personal organization — the only non-/v1 surface a
# normal user session may reach. Admin-scoped sessions may use it for their own data too.
app.include_router(account_profile.router, prefix="/account")
app.include_router(account_api_keys.router, prefix="/account")
app.include_router(account_projects.router, prefix="/account")
app.include_router(account_usage.router, prefix="/account")
app.include_router(account_analytics.router, prefix="/account")
app.include_router(account_requests.router, prefix="/account")
app.include_router(account_billing.router, prefix="/account")

# Operational probes.
app.include_router(health.router)


@app.get("/", tags=["Health"], summary="Service metadata")
async def root():
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {"openai": "/v1", "anthropic": "/v1/messages", "admin": "/admin", "health": "/health"},
    }
