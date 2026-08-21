# Chat Product — Build Status & Handoff

> First-party ChatGPT/Claude-style chat product on top of the gateway, for **personal/local
> use of the owner's OWN OpenAI account** (not reselling). Upstream = owner's authorized
> OpenAI API via `UPSTREAM_API_KEY` / `UPSTREAM_BASE_URL`.
>
> **Status as of 2026-08-21:** Phase 1 complete, Phase 2 ~80% complete. **The whole system
> runs today** (backend boots, migrates fresh+existing to head `0003`, `/health` OK; both
> frontends `npm run build` green). The remaining work below is paused by request and does
> not affect runnability — nothing unfinished is wired into an import path.

Full original plan: `C:\Users\Arham\.claude\plans\typed-tickling-pumpkin.md`.

---

## How to run (verified working)

```bash
# Backend  (Python 3.14 venv already at backend/.venv)
cd backend
./.venv/Scripts/python.exe -m alembic upgrade head          # fresh or existing → 0003
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload # serves /health, /v1/*, /account/*, /admin/*

# Frontends (Node 24, deps already installed)
cd frontend        && npm run dev      # user dashboard (port 3000)
cd frontend-admin  && npm run dev      # admin console
```

Set `UPSTREAM_API_KEY` (owner's own OpenAI key) in `backend/.env` for real completions.
Chat/recall/attachments all degrade gracefully when the upstream or optional deps are absent.

---

## SECURITY CARVE-OUTS (must always hold)

- **notrack**: `notrack_provider.py` stays untouched and reachable on `/v1`, but is **never**
  offered in public chat. `notrack-c` is seeded `public_chat=False` (bootstrap.py L47-54).
  Default free public model = `gpt-4o-mini`. Do **not** build anything to evade AI safety
  (no prompt-rewriting-to-evade) — the shared trace showed the upstream evading safety.
- Never store raw API keys / plaintext passwords / upstream credentials. Don't log secrets or
  request content by default (`log_request_content` stays `False`). Never expose upstream creds
  to API consumers. Never let an API key reach admin endpoints. **The provider adapter is the
  ONLY code that talks to an upstream.** Usage/audit/credit rows are append-only; soft-archive.

---

## Architecture: session → pipeline bridge (Option A, implemented)

The `/account/chat/*` surface is **session-authed** (dashboard JWT `gw_token`). It resolves a
hidden per-user `is_system` `ApiKey` (provisioned lazily) into an `AuthContext` via
`build_context_for_key`, then reuses the **untouched** `chat_service.prepare/stream/complete`
pipeline. Chat-product gates (`chat_enabled`, `public_chat`, `monthly_chat_messages`) live in a
thin orchestration layer **above** `prepare`, so `/v1` stays byte-identical.

- The system key is **invisible** (`list_api_keys(include_system=False)`), **unmanageable**
  (`get_key_or_404` 404s on it), and **uncounted** (profile overview filters it out).
- `monthly_chat_messages` = count of **success** `UsageRecord` rows on that system key
  (append-only billing truth, never a mutable counter).

### KEY DECISION — summary/extraction/embeddings are OUT-OF-BAND (unmetered)

`chat_messages_in_period` counts *every* success `UsageRecord` on the system key, and
`UsageRecord` has **no `endpoint` column** (verified) to distinguish internal calls. Therefore
**summary, memory-extraction and embedding calls must NOT go through `chat_service` / the system
key** — doing so would inflate the user's monthly message count (each turn would count as 2-3).
They call the OpenAI provider **directly** (`registry.get("openai").chat(...)` / `.embed(...)`),
best-effort, and are not metered as chat turns. This is correct for personal use: they are
internal maintenance, not user-visible messages. (Embeddings already go direct via
`embedding_service`.) Record this if revisiting metering.

---

## DONE

### Phase 1 — data model / migration / config / bootstrap  ✅ (all verified)
- `models/enums.py`: `monthly_chat_messages` in `LIMIT_METRICS` (not in the per-minute limitset).
- `models/api_key.py`: `is_system: bool` (default False, indexed).
- `models/model.py`: `public_chat` (indexed) + `supports_vision`.
- `models/user_settings.py`: `UserSettings` (custom_instructions_about/style, preferred_model,
  memory_enabled, personalization_enabled; id `uset`).
- `models/memory.py`: `UserMemory` (content, source_conversation_id, salience, embedding JSON,
  active; id `mem`) + `Embedding` (owner_type message|conversation_summary, owner_id,
  conversation_id, content, embedding JSON list[float], model; id `emb`).
- `models/__init__.py`: all three registered.
- `config.py`: `chat_system_prompt`, `chat_default_model="gpt-4o-mini"`, `embeddings_enabled`,
  `embedding_model="text-embedding-3-small"`, `recall_top_k_memories=5`, `recall_top_k_snippets=4`,
  `summary_trigger_messages=20`, `memory_extraction_enabled`, `reserved_output_tokens=1024`,
  `context_margin_tokens=512`, `attachments_enabled`, `max_attachment_bytes=10MB`,
  `max_attachment_text_chars=200_000`.
- `alembic/versions/0003_chat_product.py`: creates user_settings/user_memories/embeddings,
  batch-adds api_keys.is_system + models.public_chat/supports_vision with server_default backfill.
  **Verified: fresh upgrade AND existing DB both converge to `0003`.**
- `bootstrap.py`: gpt-4o & gpt-4o-mini seeded `public_chat=True` (4o also `supports_vision`);
  notrack-c `public_chat=False`; every plan `chat_enabled=True`; capped `monthly_chat_messages`
  (free 200 / starter 2000 / pro 20000 / enterprise 100000; custom unlimited). Idempotent
  "ensure" upgrade steps for existing DBs (`ensured_chat_model_defaults` / `ensured_chat_plan_defaults`).
- `requirements-optional.txt`: `markitdown>=0.0.1a2` (optional; NOT installed; guarded import to come).

### Phase 2 — bridge, provider embed, core services  🟡 (services below done)
- `dependencies.py`: `build_context_for_key(session, key, *, touch_last_used=True)` extracted from
  `get_api_context` (identical enforcement); `get_chat_context` dep (JWT → system key → context).
  **Bug fixed:** `get_chat_context` was defined before `get_current_user`, so its `Depends(...)`
  default raised `NameError` at import — moved it to after `get_current_user`.
- `services/api_key_service.py`: `SYSTEM_KEY_NAME`/`SYSTEM_KEY_SCOPES`, `get_or_create_system_key`
  (idempotent, org-stamped, raw secret discarded, reactivates if disabled), `list_api_keys` /
  `get_key_or_404` with `include_system` hiding.
- `api/account/profile.py`: active-key count filters `is_system == False`.
- `providers/base.py`: `embed(texts, *, model)` default `NotImplementedError` (notrack refuses).
- `providers/openai_provider.py`: `embed()` — POST `/embeddings`, same auth/retry/backoff as `chat`.
- `services/usage_service.py`: `chat_messages_in_period(session, *, api_key_id, since, until=None)`.
- `errors.py`: `ChatQuotaExceededError` (429, `chat_message_quota_exceeded`).
- `services/quota_service.py`: `check_chat_messages(...)` (429) + `chat_message_status(...)`.
- `services/conversation_service.py`: `rename_conversation`, `touch_conversation` (explicit
  `updated_at = utcnow()` so the sidebar reorders on new messages), `get_summary` / `set_summary`
  (rolling summary stored in `Conversation.meta` JSON — reassigned so JSON change is detected).
- `services/user_settings_service.py` (**new**): `get_or_create`, `update` (whitelist + caps).
- `services/embedding_service.py` (**new**): `embed_texts` / `embed_one` (best-effort, OpenAI-only,
  returns None on failure), pure-Python `cosine`, `top_k` (min_score filter).

---

## REMAINING (paused — resume here)

### Phase 2 (finish) — two services left
- **`services/memory_service.py`** (build in this order):
  1. `build_context(session, *, user, conv, model, settings_row, history, latest_user_content) -> list[dict]`
     — token-budgeted packing, the core of "works even for low-context models".
     - `budget = max(floor, model.context_window − settings.reserved_output_tokens − settings.context_margin_tokens)`.
     - **Always keep** base system prompt + the current user turn. Count a vision image part as a
       flat surcharge (~1000 tok).
     - Assemble ONE system message in reading order: base prompt → personalization (custom
       instructions, if `personalization_enabled`) → recalled memories → recall snippets → rolling
       summary. Then recent history (newest-first until budget hit), then the current turn.
     - **Drop order when tight:** recall snippets → memories → summary → oldest history. Never drop
       system or current turn. Personalization is high-priority (small, keep early).
     - Embed the current user text once (best-effort via `embedding_service`); rank active
       `UserMemory` (top `recall_top_k_memories`) and cross-chat `Embedding` snippets
       (top `recall_top_k_snippets`, **exclude the current conversation**). No query vector → fall
       back to salience/recency for memories, skip snippet recall.
  2. `maybe_summarize(user_id, conv_id, model_upstream)` — fresh `SessionLocal()`; if
     `len(messages) ≥ summary_trigger_messages` and enough new since `summary_upto`, call the
     provider **directly** to summarize older messages, store via `conversation_service.set_summary`.
  3. `extract_memories(user_id, conv_id, model_upstream)` — gated by a `meta["memories_upto"]`
     counter (~every 6 messages); provider-direct JSON extraction; dedupe vs existing (normalized
     text); insert `UserMemory` (+ embedding); cap total per user (~200). Best-effort.
  4. `embed_turn(user_id, conv_id, items: list[tuple[msg_id, text]])` — fresh session, batch embed,
     store `Embedding` rows (owner_type `message`, with conversation_id). Gated by
     `embeddings_enabled` + `memory_enabled`.
  5. CRUD: `list_memories`, `get_memory_or_404`, `add_memory` (embeds inline best-effort),
     `update_memory` (re-embed on content change), `delete_memory` (hard delete — user privacy).
  - Internal helper `_complete_text(system, user, *, model_upstream, max_tokens)` wrapping
    `registry.get("openai").chat(ChatRequest(...))`, returns `""` on any failure.
- **`services/attachment_service.py`** (new):
  - Module-level **guarded** `try: from markitdown import MarkItDown / except: _ENABLED=False`.
    Effective enabled = `settings.attachments_enabled and _ENABLED`.
  - `ingest_upload(upload) -> {id, filename, mime, size, is_image, text}` with size cap
    (`max_attachment_bytes`), store bytes to a temp/attachments dir (or in-memory for the turn).
  - `to_markdown(path/bytes, mime) -> str` via markitdown, truncated to `max_attachment_text_chars`;
    on disabled/failure return a clear "attachments disabled" note (never raise into the turn).
  - `is_image(mime)`; **per-model vision gating**: images sent as vision parts ONLY when
    `model.supports_vision`, else the doc/image→text markitdown path is used (or 400 for a raw image
    on a non-vision model, per router policy).

### Phase 3 — routers + schemas (mount in `main.py`, `prefix="/account"`, + OPENAPI_TAGS)
- `schemas/chat.py`: `ChatTurnRequest{content, model?, attachment_ids?, stream=True}`, `PublicModelOut`,
  `AttachmentOut`, settings + memory in/out schemas. Reuse existing Conversation/Message schemas.
- `api/account/chat.py` (`/chat`): GET `/models` (enabled ∧ public_chat ∧ plan `model_allowed`);
  conversation CRUD (create/list/get-with-messages/rename/delete); POST
  `/conversations/{id}/completions` (streaming SSE turn); optional POST `/completions` (ephemeral);
  POST `/attachments` (multipart).
- `api/account/settings.py` (`/settings`): GET/PATCH `UserSettings`.
- `api/account/memories.py` (`/memories`): GET/POST/PATCH/DELETE, strictly user-scoped.

**Enforcement order in the streaming turn (above `prepare`; `/v1` untouched):**
`get_chat_context` → plan `chat_enabled` (403) → resolve model (enabled/public_chat/plan-allowed →
404/403) → `check_chat_messages` (429) → attachments (docs→text; image only if `supports_vision`
else 400) → persist user `Message` (**commit**) → `memory_service.build_context` →
`chat_service.prepare(payload=packed messages)` → stream → **persist assistant `Message` on a FRESH
`SessionLocal()`** (SQLite single-writer) → auto-title (first turn) → best-effort
summarize/extract/embed (out-of-band).

**SSE:** mirror `api/v1/chat.py` `SSE_HEADERS` + `_sse`/`_envelope` + `event_stream`; `prepare`
commits before streaming; finalize on its own session. Client uses **fetch-stream** (EventSource
can't POST / set auth header).

### Phase 4 — user frontend (`frontend/`)
- `package.json`: add `react-markdown`, `remark-gfm`, `rehype-highlight`, `highlight.js`.
- **Default theme → LIGHT**: `app/layout.tsx` `data-theme="light"` + pre-hydration script default
  `light`; `components/ThemeToggle.tsx` initial `useState<Theme>("light")` + SSR icon default.
- **Public landing** `app/page.tsx`: real marketing page (hero, value props, model/feature showcase,
  footer) + CTA → `/login`; signed-in users get "Go to chat".
- **Chat** route group `app/(chat)/` (auth-gated, full-height): sidebar (list/new/rename/delete/
  search), message list (react-markdown + rehype-highlight, copy-code/message), composer (textarea,
  send, **stop**, model picker, attachment button gated by `model.supports_vision`), regenerate +
  edit-and-resend, token hints. New `components/chat/*`.
- **Settings** page: custom instructions (about/style), toggles (memory/personalization),
  preferred_model. **Memories** page: list/edit/delete + manual add.
- `lib/types.ts` + `lib/api.ts`: chat models/conversations CRUD, `chat.stream` (fetch-stream reader),
  attachments, settings, memories. `Sidebar.tsx`: Chat / Settings / Memories nav.

### Phase 5 — admin frontend (`frontend-admin/`)
- **Default theme → LIGHT** (same 3 edits).
- **Models page**: `public_chat` + `supports_vision` toggles in create/edit (+ types/api).
- **Plans page**: surface `chat_enabled` feature + `monthly_chat_messages` limit in the editor.

### Phase 6 — wiring / hardening / verification
- Mount routers + tags; confirm system key hidden in account + admin key lists.
- Backend: `alembic upgrade head` (fresh+existing) → `pytest`; end-to-end SSE (stream + fresh-session
  assistant persist + auto-title); `/v1` regression-free; tiny-context packing keeps system+turn;
  quota 429; public_chat gate; attachment vision gating (image rejected on non-vision model); recall
  degrades gracefully when embeddings off.
- Frontend: both `npm run build` green.
- Manual: register → chat streams, markdown/code render, memory persists across chats,
  settings/memories editable, landing renders, light default in both apps.

---

## Enhancements to include (the "add what improves it" ask)
Stop-generation (abort stream), regenerate, edit-and-resend, copy message / copy code, conversation
rename/search, auto-title, per-conversation token hints, keyboard shortcuts, graceful "attachments
disabled" / "recall disabled" fallbacks.
