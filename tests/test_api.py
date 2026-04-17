import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.fixture
async def auth_headers(client):
    await client.post("/auth/register", json={
        "email": "api@example.com", "password": "password123"
    })
    res = await client.post("/auth/login", json={
        "email": "api@example.com", "password": "password123"
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

async def test_create_request(client, auth_headers):
    res = await client.post("/api/request", json={
        "type": "ocr",
        "file_url": "/uploads/test.pdf",
        "file_type": "pdf"
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert "request_id" in data
    assert data["status"] == "pending"

async def test_get_request_status(client, auth_headers):
    create_res = await client.post("/api/request", json={
        "type": "ocr",
        "file_url": "/uploads/test.pdf",
        "file_type": "pdf"
    }, headers=auth_headers)
    request_id = create_res.json()["request_id"]

    res = await client.get(f"/api/request/{request_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "pending"

async def test_unauthenticated_request_rejected(client):
    res = await client.post("/api/request", json={
        "type": "ocr", "file_url": "/test.pdf", "file_type": "pdf"
    })
    assert res.status_code == 401
