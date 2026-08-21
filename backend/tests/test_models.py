"""Model registry: OpenAI-compatible /v1/models + admin CRUD."""
import pytest

from tests.conftest import create_api_key, register_admin

pytestmark = pytest.mark.asyncio


async def _key(client):
    jwt, user = await register_admin(client)
    raw = await create_api_key(client, jwt)
    return jwt, user, raw


# --- OpenAI-compatible consumer endpoint (/v1/models) ------------------------
async def test_v1_models_list(client):
    _, _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.get("/v1/models", headers=kh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "list"
    ids = {m["id"] for m in body["data"]}
    assert "gpt-4o" in ids
    for m in body["data"]:
        assert m["object"] == "model"
        assert m["owned_by"]  # provider surfaced, never the upstream secret


async def test_v1_models_retrieve(client):
    _, _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.get("/v1/models/gpt-4o", headers=kh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "gpt-4o"
    assert body["object"] == "model"


async def test_v1_models_alias_retrieve(client):
    """An alias resolves to its canonical public id (model-agnostic routing)."""
    _, _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.get("/v1/models/default", headers=kh)
    assert r.status_code == 200
    assert r.json()["id"] == "gpt-4o"


async def test_v1_models_unknown_404(client):
    _, _, raw = await _key(client)
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.get("/v1/models/nope-9000", headers=kh)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "model_not_found"


async def test_v1_models_requires_api_key(client):
    r = await client.get("/v1/models")
    assert r.status_code == 401


# --- Admin CRUD --------------------------------------------------------------
async def test_admin_models_list(client):
    jwt, _, _ = await _key(client)
    h = {"Authorization": f"Bearer {jwt}"}
    r = await client.get("/admin/models", headers=h)
    assert r.status_code == 200, r.text
    ids = {m["public_id"] for m in r.json()}
    assert "gpt-4o" in ids


async def test_admin_model_create_update_delete(client):
    jwt, _, _ = await _key(client)
    h = {"Authorization": f"Bearer {jwt}"}

    # Create
    create = await client.post(
        "/admin/models",
        headers=h,
        json={
            "public_id": "my-model",
            "display_name": "My Model",
            "upstream_model": "gpt-4o-mini",
            "supports_streaming": True,
            "context_window": 16384,
            "input_price_per_1m": 0.15,
            "output_price_per_1m": 0.6,
            "aliases": ["mm"],
        },
    )
    assert create.status_code == 201, create.text
    model_id = create.json()["id"]
    assert create.json()["public_id"] == "my-model"

    # Retrieve
    got = await client.get(f"/admin/models/{model_id}", headers=h)
    assert got.status_code == 200
    assert got.json()["upstream_model"] == "gpt-4o-mini"

    # An API key can now route to the new model + its alias (model-agnostic path).
    raw = await create_api_key(client, jwt)
    kh = {"Authorization": f"Bearer {raw}"}
    assert (await client.get("/v1/models/my-model", headers=kh)).status_code == 200
    assert (await client.get("/v1/models/mm", headers=kh)).json()["id"] == "my-model"

    # Update
    patch = await client.patch(
        f"/admin/models/{model_id}", headers=h, json={"display_name": "Renamed", "enabled": False}
    )
    assert patch.status_code == 200
    assert patch.json()["display_name"] == "Renamed"
    assert patch.json()["enabled"] is False

    # Disabled models disappear from the consumer listing.
    listed = (await client.get("/v1/models", headers=kh)).json()["data"]
    assert "my-model" not in {m["id"] for m in listed}

    # Delete
    delete = await client.delete(f"/admin/models/{model_id}", headers=h)
    assert delete.status_code == 200
    assert (await client.get(f"/admin/models/{model_id}", headers=h)).status_code == 404


async def test_admin_models_requires_admin_jwt_not_api_key(client):
    """API keys must never reach admin endpoints (privilege separation)."""
    _, _, raw = await _key(client)
    # Presenting an API key (sk_live_...) as a bearer token to the admin API fails.
    r = await client.get("/admin/models", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code in (401, 403)
