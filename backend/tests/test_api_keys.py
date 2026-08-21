"""API key lifecycle & security tests."""
import pytest

from tests.conftest import create_api_key, register_admin

pytestmark = pytest.mark.asyncio


async def test_create_key_returns_secret_once(client):
    jwt, _ = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    r = await client.post("/account/api-keys", headers=h, json={"name": "my key"})
    assert r.status_code == 201
    body = r.json()
    assert body["key"].startswith("sk_live_")
    assert body["key_prefix"].startswith("sk_live_")
    # Listing never returns the raw secret.
    lst = await client.get("/admin/api-keys", headers=h)
    assert lst.status_code == 200
    assert all("key" not in k for k in lst.json())


async def test_revoked_key_is_rejected(client):
    jwt, _ = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    r = await client.post("/account/api-keys", headers=h, json={"name": "k"})
    key_id, raw = r.json()["id"], r.json()["key"]
    kh = {"Authorization": f"Bearer {raw}"}

    # Works before revocation.
    assert (await client.get("/v1/models", headers=kh)).status_code == 200
    # Revoke.
    assert (await client.post(f"/admin/api-keys/{key_id}/revoke", headers=h)).status_code == 200
    # Rejected after revocation.
    rej = await client.get("/v1/models", headers=kh)
    assert rej.status_code == 401
    assert rej.json()["error"]["code"] == "key_revoked"


async def test_rotate_invalidates_old_secret(client):
    jwt, _ = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    r = await client.post("/account/api-keys", headers=h, json={"name": "k"})
    key_id, old = r.json()["id"], r.json()["key"]

    rot = await client.post(f"/account/api-keys/{key_id}/rotate", headers=h)
    assert rot.status_code == 200
    new = rot.json()["key"]
    assert new != old

    assert (await client.get("/v1/models", headers={"Authorization": f"Bearer {old}"})).status_code == 401
    assert (await client.get("/v1/models", headers={"Authorization": f"Bearer {new}"})).status_code == 200


async def test_scope_enforcement(client):
    jwt, _ = await register_admin(client)
    # Key with only models:read cannot perform chat:write.
    raw = await create_api_key(client, jwt, scopes=["models:read"])
    kh = {"Authorization": f"Bearer {raw}"}
    r = await client.post(
        "/v1/chat/completions",
        headers=kh,
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_scope"


async def test_delete_key(client):
    jwt, _ = await register_admin(client)
    h = {"Authorization": f"Bearer {jwt}"}
    r = await client.post("/account/api-keys", headers=h, json={"name": "k"})
    key_id = r.json()["id"]
    assert (await client.delete(f"/admin/api-keys/{key_id}", headers=h)).status_code == 200
    lst = await client.get("/admin/api-keys", headers=h)
    assert all(k["id"] != key_id for k in lst.json())
