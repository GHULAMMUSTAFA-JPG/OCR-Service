from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING

class Database:
    def __init__(self):
        self.client: AsyncIOMotorClient | None = None
        self._db_name: str = ""

    async def connect(self, mongo_url: str, db_name: str) -> None:
        self.client = AsyncIOMotorClient(mongo_url)
        self._db_name = db_name

    async def disconnect(self) -> None:
        if self.client:
            self.client.close()

    def get_db(self) -> AsyncIOMotorDatabase:
        if not self.client:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.client[self._db_name]

    async def create_indexes(self) -> None:
        db = self.get_db()
        col = db["processing_requests"]
        # Index 1: worker query — find oldest pending job
        await col.create_index(
            [("status", ASCENDING), ("created_at", ASCENDING)],
            name="status_created_at"
        )
        # Index 2: analytics — jobs by type and status
        await col.create_index(
            [("type", ASCENDING), ("status", ASCENDING)],
            name="type_status"
        )

# Module-level singleton — imported by all other modules
db = Database()
