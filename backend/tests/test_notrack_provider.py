"""Notrack adapter: dispatch body construction and SSE translation.

The adapter is unit-tested against a captured wire transcript (the HAR shows
``POST /api/dispatch`` returning ``text/event-stream``). No real network calls.
"""
import json

import httpx
import pytest

from app.providers.base import ChatRequest
from app.providers.errors import UpstreamError
from app.providers.notrack_provider import NotrackProvider

pytestmark = pytest.mark.asyncio

SSE_BODY = (
    'data: {"type":"chat_meta","chat_id":"4f72c010-c6bc-44bb-9fac-56aa2da2d771","mode":"usual"}\n\n'
    'data: {"type":"user","turn":0,"content":"hello notrack","message_id":"151ac329-9fa3-4858-b6a3-b3bbf88bbbeb"}\n\n'
    'data: {"type":"thinking","speaker":"C","turn":1}\n\n'
    'data: {"type":"delta","speaker":"C","turn":1,"chunk":"Hello"}\n\n'
    'data: {"type":"delta","speaker":"C","turn":1,"chunk":" world"}\n\n'
    'data: {"type":"message","speaker":"C","turn":1,"content":"Hello world"}\n\n'
    'data: {"type":"done"}\n\n'
)


def _request(**overrides) -> ChatRequest:
    payload = {
        "model": "notrack-c",
        "messages": [{"role": "user", "content": "hello notrack"}],
    }
    payload.update(overrides)
    return ChatRequest(
        model_public="notrack-c",
        model_upstream="C",
        payload=payload,
        stream=False,
    )


async def test_chat_builds_dispatch_body_and_parses_sse():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, text=SSE_BODY, headers={"content-type": "text/event-stream"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        result = await provider.chat(_request())

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/dispatch")
    body = captured["body"]
    assert body["user_input"] == "hello notrack"
    assert body["model"] == "C"
    assert body["mode"] == "usual"
    assert body["persona"] == "normal"
    assert body["max_turns"] == 6
    assert body["chat_id"] is None
    assert body["attachments"] == []
    assert body["regenerate"] is False
    assert body["edit"] is False
    assert body["edit_mid"] is None

    assert result.text == "Hello world"
    assert result.choices[0]["message"]["content"] == "Hello world"
    assert result.provider_request_id == "4f72c010-c6bc-44bb-9fac-56aa2da2d771"
    assert result.usage is None


async def test_chat_payload_overrides_debate_knobs():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SSE_BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        request = _request(mode="draft", max_turns=3, persona="skeptic", chat_id="abc")
        # The provider writes the payload override onto its body copy.
        body = provider._build_body(request)

    assert body["mode"] == "draft"
    assert body["max_turns"] == 3
    assert body["persona"] == "skeptic"
    assert body["chat_id"] == "abc"


async def test_chat_multimodal_content_uses_text_parts():
    request = _request()
    request.payload["messages"] = [
        {"role": "user", "content": [
            {"type": "text", "text": "describe "},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]}
    ]
    captured = {}

    async def handler(r: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(r.content)
        return httpx.Response(200, text=SSE_BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        await provider.chat(request)

    assert captured["body"]["user_input"] == "describe "


async def test_stream_chat_yields_deltas_then_stop():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=SSE_BODY, headers={"content-type": "text/event-stream"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        chunks = [c async for c in provider.stream_chat(_request())]

    assert [c.delta for c in chunks if c.delta] == ["Hello", " world"]
    assert chunks[-1].finish_reason == "stop"


async def test_stream_chat_message_only_fallback():
    body = SSE_BODY.replace(
        'data: {"type":"delta","speaker":"C","turn":1,"chunk":"Hello"}\n\n'
        'data: {"type":"delta","speaker":"C","turn":1,"chunk":" world"}\n\n',
        "",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        chunks = [c async for c in provider.stream_chat(_request())]

    # The full message event becomes a single content chunk when no deltas arrive.
    assert [c.delta for c in chunks if c.delta] == ["Hello world"]
    assert chunks[-1].finish_reason == "stop"


async def test_http_error_maps_to_upstream_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text='{"error":{"message":"blocked"}}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        with pytest.raises(UpstreamError) as exc_info:
            await provider.chat(_request())

    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "blocked"


async def test_stream_error_maps_to_upstream_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        with pytest.raises(UpstreamError) as exc_info:
            async for _ in provider.stream_chat(_request()):
                pass

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True


async def test_health_check_uses_chats_endpoint():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text="{}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NotrackProvider(client)
        ok, latency = await provider.health_check()

    assert captured["url"].endswith("/api/chats")
    assert ok is True
    assert latency is not None