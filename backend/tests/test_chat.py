"""Chat completion tests (OpenAI + Anthropic formats) with a mocked provider."""
import pytest

from tests.conftest import create_api_key, register_admin

pytestmark = pytest.mark.asyncio


async def _key(client):
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    return jwt, raw


async def test_openai_chat_completion(client, fake_provider):
    fake_provider.reply_text = "The answer is 42."
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "What is the answer?"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "The answer is 42."
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["total_tokens"] == 18
    assert fake_provider.calls == 1


async def test_model_alias_resolves(client, fake_provider):
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    # "default" is an alias of gpt-4o in the seeded registry.
    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "default", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    assert r.json()["model"] == "gpt-4o"


async def test_unknown_model_404(client):
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "does-not-exist", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "model_not_found"


async def test_usage_accounting_persisted(client, fake_provider):
    jwt, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    h = {"Authorization": f"Bearer {jwt}"}

    reqs = await client.get("/admin/requests", headers=h)
    assert reqs.status_code == 200
    items = reqs.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["status"] == "success"
    assert row["total_tokens"] == 18
    assert row["token_count_source"] == "provider_reported"

    ov = await client.get("/admin/analytics/overview", headers=h)
    assert ov.json()["total_requests"] == 1
    assert ov.json()["total_tokens"] == 18


async def test_estimated_tokens_when_provider_omits_usage(client, fake_provider):
    fake_provider.report_usage = False  # force tokenizer estimation
    jwt, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {jwt}"}
    row = (await client.get("/admin/requests", headers=h)).json()["items"][0]
    assert row["token_count_source"] == "tokenizer_estimated"
    assert row["total_tokens"] > 0


async def test_anthropic_messages_format(client, fake_provider):
    fake_provider.reply_text = "Bonjour!"
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/messages",
        headers=kh,
        json={
            "model": "gpt-4o",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Say hi in French"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    assert body["content"][0]["text"] == "Bonjour!"
    assert body["stop_reason"] == "end_turn"
