import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_and_me(client: AsyncClient):
    payload = {"email": "test@example.com", "password": "StrongPassword123!"}
    register_resp = await client.post("/auth/register", json=payload)
    assert register_resp.status_code == 201
    user_data = register_resp.json()
    assert user_data["email"] == "test@example.com"
    assert "id" in user_data
    assert "password" not in user_data
    assert "hashed_password" not in user_data

    duplicate_resp = await client.post("/auth/register", json=payload)
    assert duplicate_resp.status_code == 409

    login_resp = await client.post(
        "/auth/login",
        data={"username": "test@example.com", "password": "StrongPassword123!"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = await client.get("/users/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_invalid_token_and_unauthorized_protected_routes(client: AsyncClient):
    me_no_token = await client.get("/users/me")
    assert me_no_token.status_code == 401

    me_bad_token = await client.get(
        "/users/me", headers={"Authorization": "Bearer invalid.jwt.token"}
    )
    assert me_bad_token.status_code == 401