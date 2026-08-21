"""Provider adapter behavior: upstream errors are translated + masked, never leaked.

The provider adapter is the only layer that talks to the upstream. When the
upstream fails, consumers must get a clean, non-leaky API error (no stack traces,
no upstream credentials, no hint that it was *our* key that failed) and the
failure must be recorded for observability.
"""
import pytest

from app.providers.errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from tests.conftest import create_api_key, register_admin

pytestmark = pytest.mark.asyncio


async def _key(client):
    jwt, _ = await register_admin(client)
    raw = await create_api_key(client, jwt)
    return jwt, raw


def _chat():
    return {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}


async def test_upstream_auth_failure_is_masked_as_502(client, fake_provider):
    """A 401 from the upstream must NEVER surface as a client auth error, and
    must not reveal that our own credential failed."""
    fake_provider.raise_exc = UpstreamError(
        "Incorrect API key provided: sk-secret-upstream-xyz", status_code=401
    )
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}

    r = await client.post("/v1/chat/completions", headers=kh, json=_chat())
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["message"] == "Upstream authorization failed."
    assert err["code"] == "upstream_auth_error"
    # The raw upstream secret / message must not leak to the consumer.
    assert "sk-secret-upstream-xyz" not in r.text
    assert "Incorrect API key" not in r.text


async def test_upstream_timeout_maps_to_504(client, fake_provider):
    fake_provider.raise_exc = UpstreamTimeout()
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}

    r = await client.post("/v1/chat/completions", headers=kh, json=_chat())
    assert r.status_code == 504, r.text
    assert r.json()["error"]["code"] == "upstream_timeout"


async def test_upstream_unavailable_maps_to_503(client, fake_provider):
    fake_provider.raise_exc = UpstreamUnavailable()
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}

    r = await client.post("/v1/chat/completions", headers=kh, json=_chat())
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "upstream_unavailable"


async def test_upstream_500_maps_to_502(client, fake_provider):
    fake_provider.raise_exc = UpstreamError("kaboom", status_code=500)
    _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}

    r = await client.post("/v1/chat/completions", headers=kh, json=_chat())
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["type"] == "provider_error"
    assert err["code"] == "upstream_error"


async def test_failed_request_is_persisted(client, fake_provider):
    """Errors must be logged (fresh session) so the dashboard/analytics see them."""
    fake_provider.raise_exc = UpstreamError("boom", status_code=401)
    jwt, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}

    assert (await client.post("/v1/chat/completions", headers=kh, json=_chat())).status_code == 502

    h = {"Authorization": f"Bearer {jwt}"}
    items = (await client.get("/admin/requests", headers=h)).json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["status"] == "error"
    assert row["status_code"] == 502
    assert row["error_code"] == "upstream_auth_error"
    # The stored error message is the masked one, never the raw upstream text.
    assert row["error_message"] == "Upstream authorization failed."

    ov = (await client.get("/admin/analytics/overview", headers=h)).json()
    assert ov["failed_requests"] == 1
    assert ov["provider_errors"] == 1


async def test_timeout_persisted_with_timeout_status(client, fake_provider):
    fake_provider.raise_exc = UpstreamTimeout()
    jwt, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    await client.post("/v1/chat/completions", headers=kh, json=_chat())

    h = {"Authorization": f"Bearer {jwt}"}
    row = (await client.get("/admin/requests", headers=h)).json()["items"][0]
    assert row["status"] == "timeout"
    assert row["status_code"] == 504


async def test_provider_credential_is_masked_in_admin_view(client):
    """The admin provider view exposes only a masked credential, never the secret."""
    jwt, _ = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    providers = (await client.get("/admin/provider", headers=h)).json()
    assert len(providers) >= 1
    openai_cfg = next(p for p in providers if p["name"] == "openai")
    masked = openai_cfg["key_masked"]
    # Configured in conftest as UPSTREAM_API_KEY="test-upstream-key".
    assert "test-upstream-key" not in masked  # full secret never present
    assert "..." in masked  # visibly masked (first4...last4)
