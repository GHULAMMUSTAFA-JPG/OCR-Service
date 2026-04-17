import pytest
from db.client import Database

async def test_connect_and_ping(test_db):
    db = Database()
    await db.connect("mongodb://localhost:27017", "ocr_service_test")
    result = await db.client.admin.command("ping")
    assert result["ok"] == 1.0
    await db.disconnect()

async def test_create_indexes(test_db):
    db = Database()
    await db.connect("mongodb://localhost:27017", "ocr_service_test")
    await db.create_indexes()
    indexes = await db.get_db()["processing_requests"].index_information()
    index_keys = [list(v["key"]) for v in indexes.values()]
    assert any("status" in str(k) for k in index_keys)
    await db.disconnect()
