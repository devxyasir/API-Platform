# LLM Gateway

A small, self-hosted, **OpenAI- and Anthropic-compatible** API gateway in front of
**your own** upstream LLM account (e.g. your personal OpenAI key). Point any SDK,
editor, or tool that speaks the OpenAI or Anthropic wire format at this gateway and
get local API keys, per-key/per-project rate limits, token accounting, request logs,
analytics, and an admin dashboard on top of a single upstream credential.

> **This is for personal / local use of an account you are authorized to use.**
> It is not a reselling platform. Your real upstream credential lives only in the
> server environment and is never exposed to API consumers or the dashboard.

- **Backend** — FastAPI (Python 3.14-friendly), SQLAlchemy 2.0 async, SQLite by
  default (Postgres optional), optional Redis, JWT admin auth, hashed API keys.
- **Frontend** — Next.js 14 dashboard (App Router, TypeScript, Tailwind) for keys,
  users, projects, models, rate limits, analytics, audit log, and health.

---

## Contents

- [Architecture](#architecture)
- [Quick start (Docker Compose)](#quick-start-docker-compose)
- [Manual setup](#manual-setup)
- [Environment variables](#environment-variables)
- [First admin & bootstrap](#first-admin--bootstrap)
- [Using it from an IDE / SDK](#using-it-from-an-ide--sdk)
- [API surface](#api-surface)
- [Security model](#security-model)
- [Testing](#testing)
- [Security advisories (frontend)](#security-advisories-frontend)
- [Project layout](#project-layout)

---

## Architecture

```
  your editor / SDK                     dashboard (browser)
  (OpenAI or Anthropic client)          Next.js @ :3000
        │  sk_...  (gateway API key)          │  JWT (admin/user login)
        ▼                                     ▼
  ┌───────────────────────── FastAPI gateway @ :8000 ─────────────────────────┐
  │  /v1/*   OpenAI + Anthropic compatible   │   /admin/*   dashboard API      │
  │  api-key auth, rate limits, token count  │   JWT auth, RBAC                │
  │                    provider adapter (the ONLY code that talks upstream)    │
  └───────────────────────────────────┬────────────────────────────────────────┘
                                       │  your real UPSTREAM_API_KEY (server env only)
                                       ▼
                            upstream (api.openai.com/v1, …)

  state: SQLite (default) or Postgres   ·   rate limiting: in-memory or Redis
```

The **provider adapter** is the only part of the system that knows how to talk to
the upstream. `/v1/*` is authenticated with gateway API keys (`sk_...`); `/admin/*`
is authenticated with a JWT from a dashboard login. The two never mix — an API key
can never reach an admin endpoint.

---

## Quick start (Docker Compose)

Brings up the full stack: gateway API + dashboard + Postgres + Redis.

```bash
# 1. Configure secrets and your upstream key
cp backend/.env.example backend/.env
#    edit backend/.env — set JWT_SECRET, API_KEY_PEPPER, IP_HASH_SALT,
#    UPSTREAM_API_KEY, and (optionally) ADMIN_EMAIL / ADMIN_PASSWORD

# 2. Launch
docker compose up --build
```

- Dashboard → <http://localhost:3000>
- Gateway API → <http://localhost:8000>  (OpenAI base URL: `http://localhost:8000/v1`)
- API docs (Swagger) → <http://localhost:8000/docs>

Compose overrides a few values from `backend/.env` so the containers can find each
other: `DATABASE_URL` → Postgres, `REDIS_URL` → Redis, `AUTO_CREATE_TABLES=false`
(the container applies **Alembic migrations** on startup via its entrypoint), and
`CORS_ORIGINS` → the dashboard origin. Generate strong secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> The dashboard's API URL is baked into the browser bundle at build time via the
> `NEXT_PUBLIC_API_BASE_URL` build arg (default `http://localhost:8000`). If you
> expose the gateway on a different host/port, rebuild the frontend with that value.

---

## Manual setup

### Backend

Requires Python 3.11+ (tested on 3.14). From `backend/`:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# optional: Postgres driver + faster tokenizer
# pip install -r requirements-optional.txt

cp .env.example .env      # then edit secrets + UPSTREAM_API_KEY

# Run it
uvicorn app.main:app --reload --port 8000
```

With the defaults (`AUTO_CREATE_TABLES=true`, SQLite) the schema is created on
first boot — no migration step needed. If you prefer Alembic (required for
Postgres in production), set `AUTO_CREATE_TABLES=false` and run:

```bash
alembic upgrade head
```

### Frontend

Requires Node 18+. From `frontend/`:

```bash
cd frontend
npm install

# point the dashboard at your gateway (defaults to http://localhost:8000)
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000   # Windows: set NEXT_PUBLIC_API_BASE_URL=...

npm run dev        # http://localhost:3000  (development)
# or, for production:
npm run build && npm run start
```

Open <http://localhost:3000> and register the first account — it becomes the admin.

---

## Environment variables

All backend config lives in `backend/.env` (see `backend/.env.example`). The three
secrets **must** be replaced before exposing the service.

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `development` / `production`. |
| `APP_NAME` | `LLM Gateway` | Shown in health + dashboard. |
| `DEBUG` | `true` | Set `false` in production. |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated dashboard origins. |
| **`JWT_SECRET`** | — | **Required.** Signs dashboard JWTs. |
| **`API_KEY_PEPPER`** | — | **Required.** Server-side pepper mixed into API-key hashes. |
| **`IP_HASH_SALT`** | — | **Required.** Salt for hashing client IPs (raw IPs are never stored). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Dashboard session length. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./gateway.db` | Postgres: `postgresql+asyncpg://user:pass@host:5432/db`. |
| `AUTO_CREATE_TABLES` | `true` | `true` = create schema on boot; `false` = use Alembic. |
| `REDIS_URL` | *(empty)* | Empty → in-memory rate limiter. `redis://host:6379/0` to enable. |
| `UPSTREAM_PROVIDER` | `openai` | Upstream adapter to use. |
| `UPSTREAM_BASE_URL` | `https://api.openai.com/v1` | Your upstream's base URL. |
| **`UPSTREAM_API_KEY`** | — | **Your own** upstream credential. Server-only; never exposed. |
| `UPSTREAM_AUTH_MODE` | `bearer` | How the upstream key is sent. |
| `UPSTREAM_TIMEOUT` | `120` | Upstream request timeout (seconds). |
| `UPSTREAM_MAX_RETRIES` | `2` | Upstream retry attempts. |
| `LOG_REQUEST_CONTENT` | `false` | **Off by default.** When `true`, logs prompt/response bodies. |
| `LOG_LEVEL` | `INFO` | Standard logging level. |
| `LOG_JSON` | `false` | `true` for structured JSON logs. |
| `ADMIN_EMAIL` | *(empty)* | Optional: seed an admin on first startup. |
| `ADMIN_PASSWORD` | *(empty)* | Optional: password for the seeded admin. |
| `ADMIN_NAME` | `Administrator` | Optional: display name for the seeded admin. |

The frontend reads a single build-time variable, `NEXT_PUBLIC_API_BASE_URL`
(default `http://localhost:8000`), which points the browser at the gateway.

---

## First admin & bootstrap

There are two ways to get an admin account:

1. **First registered user wins.** The very first account created through the
   dashboard (or `POST /admin/auth/register`) is promoted to **admin/owner**; every
   subsequent registration is a regular developer account.
2. **Seeded admin.** If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set, an admin is
   created automatically on first startup so you can log in without registering.

After logging in, create gateway API keys from the **API Keys** page and hand those
`sk_...` keys to your tools.

---

## Using it from an IDE / SDK

The gateway speaks both the **OpenAI** and **Anthropic** wire formats, so most tools
work by changing only the base URL and the API key.

**Base URLs**

| Format | Base URL | Endpoint |
|---|---|---|
| OpenAI | `http://localhost:8000/v1` | `POST /chat/completions`, `GET /models` |
| Anthropic | `http://localhost:8000/v1` | `POST /messages` |

Use a gateway key (`sk_...`) from the dashboard as the API key — **not** your
upstream credential. The gateway attaches the real upstream key server-side.

**OpenAI Python SDK**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk_your_gateway_key",   # created in the dashboard
)
resp = client.chat.completions.create(
    model="gpt-4o-mini",             # a model id enabled in the Models page
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.choices[0].message.content)
```

**Anthropic Python SDK**

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://localhost:8000",   # SDK appends /v1/messages itself
    api_key="sk_your_gateway_key",
)
msg = client.messages.create(
    model="gpt-4o-mini",
    max_tokens=256,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(msg.content)
```

**curl (OpenAI, streaming)**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk_your_gateway_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","stream":true,
       "messages":[{"role":"user","content":"Say hi"}]}'
```

**Editor / tool setup** — anywhere a tool lets you set a "custom OpenAI base URL"
(Cursor, Continue, Zed, aider, LibreChat, etc.):

- **Base URL / API base:** `http://localhost:8000/v1`
- **API key:** a `sk_...` key from the dashboard
- **Model:** any model id you enabled on the **Models** page

The dashboard's **Settings** page shows the exact base URLs for your deployment.

---

## API surface

**Consumer API — `/v1/*`** (gateway API key):

- `POST /v1/chat/completions` — OpenAI-compatible chat (supports `stream=true`)
- `POST /v1/messages` — Anthropic-compatible messages
- `GET /v1/models`, `GET /v1/models/{id}` — enabled models
- `GET /v1/usage` — your token usage
- `POST /v1/conversations`, `GET /v1/conversations`, `GET /v1/conversations/{id}`

**Admin API — `/admin/*`** (dashboard JWT): auth, users, projects, API keys,
models, requests, usage/analytics, rate limits, provider, audit.

**Health** (unauthenticated): `GET /health`, `GET /health/live`, `GET /health/ready`.

Interactive docs are served at `/docs` (Swagger) and `/redoc`.

---

## Security model

- **API keys are never stored raw** — only a prefix (for display) and a peppered
  hash. The full key is shown **once**, at creation time.
- **Passwords are hashed** with bcrypt; plaintext is never stored.
- **Upstream credentials never leave the server** — they're read from the
  environment, injected by the provider adapter, and masked everywhere in the
  dashboard/API. Consumers cannot read them.
- **Consumer vs. admin isolation** — a `sk_...` API key can only reach `/v1/*`; it
  can never call an `/admin/*` endpoint.
- **Request-content logging is off by default** (`LOG_REQUEST_CONTENT=false`).
  Prompt/response bodies are only stored if you explicitly opt in.
- **No secrets in logs** — authorization headers and upstream cookies are not
  logged or stored; client IPs are hashed with `IP_HASH_SALT`.
- **No internal stack traces to consumers** — errors are returned as a structured
  `{ "error": { message, type, code } }` envelope.

---

## Testing

Backend tests use pytest:

```bash
cd backend
pip install -r requirements.txt
pytest
```

Frontend type-check / build:

```bash
cd frontend
npm run build      # type-checks and compiles all routes
```

---

## Security advisories (frontend)

The dashboard pins **Next.js 14.2.x** (latest patch). After patching the earlier
*critical* advisory, `npm audit` still reports **two high-severity advisories** that
span the entire Next 14.x line plus a build-time `postcss` issue. They concern
features this dashboard does **not** use — `next/image`, rewrites, middleware, i18n,
Server Actions, a custom server, `beforeInteractive` scripts, and CSP nonces
(DoS / SSRF / cache-poisoning / XSS); the `postcss` issue is build-time only.

The only `npm audit fix --force` remedy is **`next@16`**, a **two-major** upgrade
that also requires **React 19** and would be a breaking change to a currently-green
build. This project intentionally stays on 14.2.x. If you want a clean `npm audit`,
plan a deliberate upgrade:

```bash
cd frontend
npm install next@latest react@latest react-dom@latest
npm run build     # then fix any breaking changes (App Router / React 19)
```

Because the dashboard is meant to run locally / behind your own network, the
residual advisories are low-risk here — but upgrade if you expose it publicly.

---

## Project layout

```
.
├── docker-compose.yml        # full stack: backend + frontend + postgres + redis
├── backend/
│   ├── app/                  # FastAPI app (api/, providers, models, schemas, …)
│   │   ├── main.py           # app factory + router mounts + lifespan
│   │   ├── bootstrap.py      # seeds admin + default models on startup
│   │   └── config.py         # env-driven settings
│   ├── alembic/              # database migrations
│   ├── tests/                # pytest suite
│   ├── Dockerfile
│   ├── docker-entrypoint.sh  # runs `alembic upgrade head` then starts uvicorn
│   ├── requirements.txt      # default (SQLite + in-memory) deps
│   ├── requirements-optional.txt   # Postgres driver, faster tokenizer
│   └── .env.example
└── frontend/
    ├── app/                  # Next.js App Router (login + (dashboard) pages)
    ├── components/           # UI kit, sidebar, charts
    ├── lib/                  # api client, auth context, hooks, types, formatting
    ├── Dockerfile
    └── package.json
```
