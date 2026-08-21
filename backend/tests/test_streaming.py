"""Streaming (SSE) tests."""
import json

import pytest

from tests.conftest import create_api_key, register_admin

pytestmark = pytest.mark.asyncio


def _parse_openai_sse(text: str):
    """Return (assembled_text, finish_reasons, saw_done)."""
    assembled, finishes, saw_done = [], [], False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            saw_done = True
            continue
        data = json.loads(payload)
        for ch in data.get("choices", []):
            delta = ch.get("delta", {})
            if delta.get("content"):
                assembled.append(delta["content"])
            if ch.get("finish_reason"):
                finishes.append(ch["finish_reason"])
    return "".join(assembled), finishes, saw_done


async def test_openai_streaming(client, fake_provider):
    fake_provider.chunk_words = ["Hello", ", ", "world", "!"]
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}

    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    assembled, finishes, saw_done = _parse_openai_sse(r.text)
    assert assembled == "Hello, world!"
    assert "stop" in finishes
    assert saw_done


async def test_stream_is_logged(client, fake_provider):
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}
    await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    h = {"Authorization": f"Bearer {jwt}"}
    items = (await client.get("/admin/requests", headers=h)).json()["items"]
    assert len(items) == 1
    assert items[0]["stream"] is True
    assert items[0]["status"] == "success"
    assert items[0]["total_tokens"] == 18


async def test_anthropic_streaming(client, fake_provider):
    fake_provider.chunk_words = ["Bon", "jour"]
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/messages",
        headers=kh,
        json={
            "model": "gpt-4o",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    # Anthropic emits named events; the text deltas ride in content_block_delta.
    assert "content_block_delta" in r.text
    assert "message_stop" in r.text
    assert "Bon" in r.text and "jour" in r.text


async def test_openai_streaming_tool_calls_pass_through(client, fake_provider):
    """Tool-call deltas must survive the gateway verbatim — coding IDEs depend on it.

    This is model-agnostic: the API layer forwards whatever ``choices`` the upstream
    streams, so it works identically for the current model and any future model.
    """
    fake_provider.stream_choices = [
        [{"index": 0, "finish_reason": None, "delta": {
            "role": "assistant", "content": None,
            "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                            "function": {"name": "get_weather", "arguments": ""}}],
        }}],
        [{"index": 0, "finish_reason": None, "delta": {
            "tool_calls": [{"index": 0, "function": {"arguments": '{"city":"Paris"}'}}],
        }}],
        [{"index": 0, "finish_reason": "tool_calls", "delta": {}}],
    ]
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "weather in Paris?"}],
            "tools": [{"type": "function", "function": {"name": "get_weather"}}],
            "stream": True,
        },
    )
    assert r.status_code == 200

    names, args, finishes = [], [], []
    for line in r.text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            continue
        data = json.loads(payload)
        assert data["object"] == "chat.completion.chunk"
        assert data["model"] == "gpt-4o"  # public id, not upstream id
        for ch in data.get("choices", []):
            for tc in ch.get("delta", {}).get("tool_calls") or []:
                fn = tc.get("function", {})
                if fn.get("name"):
                    names.append(fn["name"])
                if fn.get("arguments"):
                    args.append(fn["arguments"])
            if ch.get("finish_reason"):
                finishes.append(ch["finish_reason"])

    assert "get_weather" in names
    assert "".join(args) == '{"city":"Paris"}'
    assert "tool_calls" in finishes


async def test_streaming_usage_only_when_requested(client, fake_provider):
    """A usage chunk is emitted only when the client opts in via stream_options."""
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}

    def _has_usage(text: str) -> bool:
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                continue
            if json.loads(payload).get("usage"):
                return True
        return False

    # Default: no usage chunk on the wire.
    r1 = await client.post(
        "/v1/chat/completions", headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    assert not _has_usage(r1.text)

    # Opt-in: usage chunk present.
    r2 = await client.post(
        "/v1/chat/completions", headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}],
              "stream": True, "stream_options": {"include_usage": True}},
    )
    assert _has_usage(r2.text)
