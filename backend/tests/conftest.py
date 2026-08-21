"""Shared test fixtures.

The upstream provider is replaced with an in-process fake, so the entire request
pipeline (auth → rate limit → provider → token accounting → logging) is exercised
without any network calls or a real OpenAI key. Each test gets a pristine SQLite
database and a reset in-memory rate limiter.
"""
from __future__ import annotations

import os

# Configure the environment BEFORE importing the app (settings is a cached
# singleton built at import time).
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite+aiosqlite:///./test_gateway.db",
        "AUTO_CREATE_TABLES": "true",
        "REDIS_URL": "",
        "JWT_SECRET": "test-jwt-secret",
        "API_KEY_PEPPER": "test-pepper",
        "IP_HASH_SALT": "test-salt",
        "UPSTREAM_API_KEY": "test-upstream-key",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "LOG_REQUEST_CONTENT": "false",
        # No bootstrap admin — tests register their own accounts.
        "ADMIN_EMAIL": "",
        "ADMIN_PASSWORD": "",
    }
)

import pytest_asyncio  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.providers import registry  # noqa: E402
from app.providers.base import ChatRequest, ChatResult, StreamChunk, Usage  # noqa: E402
from app.providers.registry import CircuitBreaker  # noqa: E402
import app.models  # noqa: E402,F401  (register all mappers)


class FakeProvider:
    """A configurable stand-in for the OpenAI adapter."""

    name = "openai"

    def __init__(self) -> None:
        self.reply_text = "Hello from the fake provider!"
        self.report_usage = True
        self.raise_exc: Exception | None = None
        self.chunk_words = ["Hello", " from", " the", " fake", " provider!"]
        # When set, stream_chat replays these raw upstream choice arrays verbatim
        # (used to exercise tool_calls / n>1 pass-through).
        self.stream_choices: list[list[dict]] | None = None
        self.calls = 0

    def _usage(self) -> Usage | None:
        if not self.report_usage:
            return None
        return Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18)

    async def chat(self, request: ChatRequest) -> ChatResult:
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return ChatResult(
            id="chatcmpl-fake",
            model=request.model_public,
            created=1700000000,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": self.reply_text},
                    "finish_reason": "stop",
                }
            ],
            usage=self._usage(),
            provider_request_id="fake-req-id",
            raw={},
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.stream_choices is not None:
            # Replay raw upstream choice arrays verbatim (tool_calls / n>1 / etc.).
            for choices in self.stream_choices:
                d = choices[0].get("delta", {}) if choices else {}
                yield StreamChunk(
                    delta=d.get("content") or "",
                    role=d.get("role"),
                    finish_reason=choices[0].get("finish_reason") if choices else None,
                    choices=choices,
                    raw={"choices": choices},
                )
            if self.report_usage:
                yield StreamChunk(usage=self._usage())
            return
        first = True
        for word in self.chunk_words:
            yield StreamChunk(delta=word, role="assistant" if first else None)
            first = False
        yield StreamChunk(finish_reason="stop")
        if self.report_usage:
            yield StreamChunk(usage=self._usage())

    async def health_check(self) -> tuple[bool, float | None]:
        return True, 1.0


@pytest_asyncio.fixture(autouse=True)
async def _reset_state():
    """Fresh DB + rate limiter + circuit breaker + fake provider per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Reset the in-memory rate-limit backend counters.
    from app.rate_limit import backend as rl_backend
    for attr in ("_counters", "_concurrency", "_strings"):
        d = getattr(rl_backend, attr, None)
        if isinstance(d, dict):
            d.clear()

    # Seed the default models + provider config (bootstrap doesn't run under
    # the in-process ASGI transport). The admin user is seeded per-test via the API.
    from app.bootstrap import seed_models, seed_plans, seed_provider
    from app.database import SessionLocal
    async with SessionLocal() as session:
        await seed_models(session)
        await seed_provider(session)
        await seed_plans(session)
        await session.commit()

    # Inject the fake provider and a fresh breaker.
    provider = FakeProvider()
    registry._providers["openai"] = provider
    registry._breakers["openai"] = CircuitBreaker()

    yield provider

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def fake_provider(_reset_state) -> FakeProvider:
    return _reset_state


async def register_admin(client: httpx.AsyncClient, email="admin@example.com", password="supersecret1"):
    """Register the first user (becomes admin) and return (jwt, user).

    Registration mints a user-scoped session; admin surfaces require an admin
    console session (scope=admin), so we log in through /admin/auth/admin-login.
    """
    r = await client.post("/admin/auth/register", json={"email": email, "password": password, "name": "Admin"})
    assert r.status_code == 201, r.text
    al = await client.post("/admin/auth/admin-login", json={"email": email, "password": password})
    assert al.status_code == 200, al.text
    body = al.json()
    assert body["scope"] == "admin"
    return body["access_token"], body["user"]


async def create_api_key(client: httpx.AsyncClient, jwt: str, **kwargs) -> str:
    headers = {"Authorization": f"Bearer {jwt}"}
    r = await client.post("/account/api-keys", headers=headers, json={"name": "test-key", **kwargs})
    assert r.status_code == 201, r.text
    return r.json()["key"]
