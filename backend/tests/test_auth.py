"""Authentication & account tests."""
import pytest

from tests.conftest import register_admin

pytestmark = pytest.mark.asyncio


async def test_first_user_becomes_admin(client):
    jwt, user = await register_admin(client)
    assert user["role"] == "admin"
    assert user["plan"] == "enterprise"
    assert jwt


async def test_second_user_is_developer(client):
    await register_admin(client)
    r = await client.post(
        "/admin/auth/register",
        json={"email": "dev@example.com", "password": "anotherpass1", "name": "Dev"},
    )
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "developer"
    assert r.json()["user"]["plan"] == "free"


async def test_login_and_me(client):
    await register_admin(client, email="admin@example.com", password="supersecret1")
    r = await client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "supersecret1"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = await client.get("/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"


async def test_login_wrong_password(client):
    await register_admin(client)
    r = await client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


async def test_duplicate_email_conflict(client):
    await register_admin(client)
    r = await client.post(
        "/admin/auth/register",
        json={"email": "admin@example.com", "password": "supersecret1", "name": "Dup"},
    )
    assert r.status_code == 409


async def test_change_password(client):
    jwt, _ = await register_admin(client, password="supersecret1")
    h = {"Authorization": f"Bearer {jwt}"}
    r = await client.post(
        "/admin/auth/change-password",
        headers=h,
        json={"current_password": "supersecret1", "new_password": "brandnewpass2"},
    )
    assert r.status_code == 200
    # Old password no longer works; new one does.
    assert (await client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "supersecret1"})).status_code == 401
    assert (await client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "brandnewpass2"})).status_code == 200


async def test_unauthenticated_me_rejected(client):
    r = await client.get("/admin/auth/me")
    assert r.status_code == 401
