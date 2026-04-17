import pytest
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

TEST_MONGO_URL = "mongodb://localhost:27017"
TEST_DB_NAME = "ocr_service_test"   # separate test database — never touches production data

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_db():
    """Real Motor client pointing at a test database."""
    client = AsyncIOMotorClient(TEST_MONGO_URL)
    db = client[TEST_DB_NAME]
    yield db
    # Clean up entire test database after session
    await client.drop_database(TEST_DB_NAME)
    client.close()
