import pytest
from unittest.mock import AsyncMock
from websockets.manager import ConnectionManager

@pytest.fixture
def manager():
    return ConnectionManager()

async def test_connect_registers_socket(manager):
    ws = AsyncMock()
    await manager.connect("req_123", ws)
    assert "req_123" in manager.active
    ws.accept.assert_called_once()

async def test_disconnect_removes_socket(manager):
    ws = AsyncMock()
    await manager.connect("req_123", ws)
    await manager.disconnect("req_123")
    assert "req_123" not in manager.active

async def test_push_sends_json(manager):
    ws = AsyncMock()
    await manager.connect("req_123", ws)
    await manager.push("req_123", {"status": "completed", "text": "hello"})
    ws.send_json.assert_called_once_with({"status": "completed", "text": "hello"})

async def test_push_skips_if_disconnected(manager):
    await manager.push("req_999", {"status": "completed"})  # no error
