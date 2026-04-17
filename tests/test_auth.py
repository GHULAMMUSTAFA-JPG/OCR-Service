import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

async def test_register(client):
    res = await client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "password123"
    })
    assert res.status_code == 201

async def test_login_success(client):
    await client.post("/auth/register", json={
        "email": "login@example.com",
        "password": "password123"
    })
    res = await client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "password123"
    })
    assert res.status_code == 200
    assert "access_token" in res.json()

async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "email": "wrong@example.com",
        "password": "password123"
    })
    res = await client.post("/auth/login", json={
        "email": "wrong@example.com",
        "password": "wrongpassword"
    })
    assert res.status_code == 401
