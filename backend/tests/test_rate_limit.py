"""Rate limiting: enforcement, standard headers, and persistence of throttling.

Exercises the full path — an admin sets a low per-caller limit, the caller
exceeds it, and we assert the 429 response, the OpenAI/Anthropic-standard
headers, and that the throttled request is durably recorded (request log +
rate-limit event + analytics), which coding IDE agents rely on for backoff.
"""
import pytest

from tests.conftest import create_api_key, register_admin

pytestmark = pytest.mark.asyncio


def _chat(model="gpt-4o"):
    return {"model": model, "messages": [{"role": "user", "content": "hi"}]}


async def test_rate_limit_exceeded_returns_429_with_headers(client, fake_provider):
    jwt, user = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}

    # Cap this user at 2 requests/minute.
    cfg = await client.put(
        "/admin/rate-limits/configs",
        headers=h,
        json={"scope_type": "user", "scope_id": user["id"], "rpm": 2},
    )
    assert cfg.status_code == 200, cfg.text

    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}

    r1 = await client.post("/v1/chat/completions", headers=kh, json=_chat())
    r2 = await client.post("/v1/chat/completions", headers=kh, json=_chat())
    r3 = await client.post("/v1/chat/completions", headers=kh, json=_chat())

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429, r3.text

    # OpenAI-style error envelope.
    err = r3.json()["error"]
    assert err["code"] == "rate_limit_exceeded"
    assert err["type"] == "rate_limit_error"

    # Standard rate-limit headers must be present so clients can back off.
    assert r3.headers.get("retry-after")
    assert int(r3.headers["retry-after"]) >= 1
    assert r3.headers.get("x-ratelimit-limit") == "2"
    assert r3.headers.get("x-ratelimit-remaining") == "0"
    assert r3.headers.get("x-ratelimit-reset")

    # The upstream was called only for the two allowed requests.
    assert fake_provider.calls == 2


async def test_rate_limited_request_is_persisted(client, fake_provider):
    jwt, user = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    await client.put(
        "/admin/rate-limits/configs",
        headers=h,
        json={"scope_type": "user", "scope_id": user["id"], "rpm": 1},
    )
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}

    await client.post("/v1/chat/completions", headers=kh, json=_chat())          # allowed
    blocked = await client.post("/v1/chat/completions", headers=kh, json=_chat())  # throttled
    assert blocked.status_code == 429

    # 1) The throttled request is recorded in the request log.
    items = (await client.get("/admin/requests", headers=h)).json()["items"]
    statuses = {i["status"] for i in items}
    assert "rate_limited" in statuses
    rl = next(i for i in items if i["status"] == "rate_limited")
    assert rl["status_code"] == 429
    assert rl["error_code"] == "rate_limit_exceeded"

    # 2) A rate-limit event is emitted for the dashboard.
    events = (await client.get("/admin/rate-limits/events", headers=h)).json()
    assert len(events) >= 1
    assert events[0]["limit_type"] == "rpm"
    assert events[0]["limit_value"] == 1

    # 3) Analytics reflects the throttle.
    ov = (await client.get("/admin/analytics/overview", headers=h)).json()
    assert ov["total_requests"] == 2
    assert ov["successful_requests"] == 1
    assert ov["rate_limited_requests"] == 1


async def test_limits_are_per_caller(client, fake_provider):
    """One key hitting its cap must not throttle a different key."""
    jwt, user = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    await client.put(
        "/admin/rate-limits/configs",
        headers=h,
        json={"scope_type": "user", "scope_id": user["id"], "rpm": 1},
    )

    raw_a = await create_api_key(client, jwt)
    raw_b = await create_api_key(client, jwt)

    ka = {"Authorization": f"Bearer {raw_a}"}
    kb = {"Authorization": f"Bearer {raw_b}"}

    assert (await client.post("/v1/chat/completions", headers=ka, json=_chat())).status_code == 200
    assert (await client.post("/v1/chat/completions", headers=ka, json=_chat())).status_code == 429
    # Different key, its own counter — still allowed.
    assert (await client.post("/v1/chat/completions", headers=kb, json=_chat())).status_code == 200
