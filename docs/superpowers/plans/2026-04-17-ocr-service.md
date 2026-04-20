# OCR Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade OCR service with FastAPI, async MongoDB (Motor), Change Stream worker, and WebSocket real-time updates.

**Architecture:** Two separate processes — `uvicorn main:app` (API + WebSocket notifier) and `python worker.py` (Change Stream job processor). MongoDB is the job queue. Atomic `find_one_and_update` prevents double-processing. WebSocket clients are notified via API-side Change Stream when jobs complete.

**Tech Stack:** FastAPI · Motor · Pydantic v2 · pydantic-settings · python-jose · passlib · pytesseract · pdf2image · pytest-asyncio · httpx

---

## File Map

| File | Responsibility |
|---|---|
| `core/config.py` | All settings from `.env` via pydantic-settings |
| `core/security.py` | JWT encode/decode, password hash/verify |
| `db/client.py` | Motor async client singleton — connect, disconnect, create indexes |
| `db/models.py` | Pydantic document models for MongoDB (User, ProcessingRequest) |
| `db/repository.py` | All MongoDB operations — create, fetch, update status, atomic lock |
| `storage/local.py` | File save/read with size + type validation |
| `websockets/manager.py` | ConnectionManager — maps request_id → WebSocket |
| `api/deps.py` | FastAPI dependencies: get_db, get_current_user |
| `api/routes/auth.py` | POST /auth/register, POST /auth/login |
| `api/routes/upload.py` | POST /api/upload |
| `api/routes/requests.py` | POST /api/request, GET /api/request/{id} |
| `watcher/api_stream.py` | API-side Change Stream → push to WebSocket clients |
| `watcher/change_stream.py` | Worker-side Change Stream → pick up pending jobs |
| `watcher/polling.py` | Fallback: reset stuck processing jobs |
| `ocr/engine.py` | Tesseract wrapper using asyncio.to_thread |
| `ocr/pdf_processor.py` | pdf2image → list of PIL images |
| `main.py` | FastAPI app with lifespan, router registration, WebSocket route |
| `worker.py` | Worker entry point — asyncio.gather(change_stream, polling) |
| `tests/conftest.py` | Shared pytest fixtures: test DB client, test app, async HTTP client |
| `tests/test_models.py` | Pydantic model validation tests |
| `tests/test_repository.py` | Repository operation tests against real test DB |
| `tests/test_ocr.py` | OCR engine tests with fixture images |
| `tests/test_api.py` | API endpoint integration tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `pytest.ini`
- Create: all `__init__.py` files

- [ ] **Step 1: Create project folder structure**

```bash
cd C:/Users/parep/Desktop/ocr-service
mkdir -p api/routes db watcher ocr core storage websockets tests/fixtures
touch api/__init__.py api/routes/__init__.py db/__init__.py watcher/__init__.py
touch ocr/__init__.py core/__init__.py storage/__init__.py websockets/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
motor==3.5.1
pydantic-settings==2.4.0
pydantic[email]==2.8.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
pytesseract==0.3.13
pdf2image==1.17.0
Pillow==10.4.0
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

- [ ] **Step 3: Create pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

> **Why `asyncio_mode = auto`?** This tells pytest-asyncio to treat every `async def test_*` as an async test automatically. Without this, you'd need to decorate every async test with `@pytest.mark.asyncio`.

- [ ] **Step 4: Create .env.example**

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=ocr_service
JWT_SECRET=change-this-to-a-long-random-string
JWT_EXPIRE_MINUTES=60
MAX_RETRIES=3
WORKER_CONCURRENCY=3
POLL_INTERVAL_SECONDS=60
MAX_PROCESSING_MINUTES=10
MAX_FILE_SIZE_MB=20
STORAGE_PATH=./storage/uploads
```

- [ ] **Step 5: Copy to .env and fill in values**

```bash
cp .env.example .env
```

- [ ] **Step 6: Create virtual environment and install dependencies**

```bash
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
```

- [ ] **Step 7: Verify Tesseract is installed**

```bash
tesseract --version
```

Expected output: `tesseract 5.x.x` — if not installed, download from https://github.com/UB-Mannheim/tesseract/wiki (Windows).

- [ ] **Step 8: Commit**

```bash
git init
git add requirements.txt .env.example pytest.ini
git commit -m "chore: project scaffolding"
```

---

## Task 2: Core Config

**Files:**
- Create: `core/config.py`
- Create: `tests/test_config.py`

> **Concept:** `pydantic-settings` reads environment variables and `.env` files and validates them as a Pydantic model. This means if `MONGO_URL` is missing, your app crashes at startup with a clear error — not silently at runtime when the first DB call happens.

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
from core.config import settings

def test_settings_loads():
    assert settings.DB_NAME == "ocr_service"
    assert settings.MAX_RETRIES == 3
    assert settings.WORKER_CONCURRENCY == 3

def test_settings_has_mongo_url():
    assert settings.MONGO_URL.startswith("mongodb://")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.config'`

- [ ] **Step 3: Implement core/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGO_URL: str
    DB_NAME: str = "ocr_service"
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 60
    MAX_RETRIES: int = 3
    WORKER_CONCURRENCY: int = 3
    POLL_INTERVAL_SECONDS: int = 60
    MAX_PROCESSING_MINUTES: int = 10
    MAX_FILE_SIZE_MB: int = 20
    STORAGE_PATH: str = "./storage/uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
```

> **Why a module-level `settings = Settings()` singleton?** Creating `Settings()` reads the `.env` file. You want this once at import time, not every time a route runs. All modules import this one instance.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config.py pytest.ini
git commit -m "feat: core settings via pydantic-settings"
```

---

## Task 3: Pydantic Document Models

**Files:**
- Create: `db/models.py`
- Create: `tests/test_models.py`

> **Concept:** MongoDB documents don't have a fixed schema enforced by the DB. We enforce it in Python with Pydantic. The key challenge: MongoDB uses `_id` (underscore prefix, BSON ObjectId type) but Python prefers `id` (no underscore, string type). The `PyObjectId` class bridges this.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models.py
from datetime import datetime
from db.models import ProcessingRequest, User, RequestStatus, RequestType

def test_processing_request_defaults():
    req = ProcessingRequest(
        user_id="user123",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    assert req.status == RequestStatus.PENDING
    assert req.retry_count == 0
    assert req.max_retries == 3
    assert req.output is None
    assert req.error is None
    assert isinstance(req.created_at, datetime)

def test_processing_request_status_enum():
    assert RequestStatus.PENDING == "pending"
    assert RequestStatus.PROCESSING == "processing"
    assert RequestStatus.COMPLETED == "completed"
    assert RequestStatus.FAILED == "failed"

def test_user_model():
    user = User(email="test@example.com", hashed_password="hashed")
    assert user.email == "test@example.com"
    assert isinstance(user.created_at, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'db.models'`

- [ ] **Step 3: Implement db/models.py**

```python
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from bson import ObjectId
from pydantic import BaseModel, Field, field_validator

class PyObjectId(str):
    """
    Bridge between MongoDB's ObjectId and Pydantic's str type.
    MongoDB stores _id as ObjectId (12-byte BSON type).
    We convert it to str so Pydantic and JSON can handle it.
    """
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> str:
        if isinstance(v, ObjectId):
            return str(v)
        if ObjectId.is_valid(v):
            return str(v)
        raise ValueError(f"Invalid ObjectId: {v}")

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        from pydantic_core import core_schema
        return core_schema.no_info_plain_validator_function(cls.validate)


class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RequestType(str, Enum):
    OCR = "ocr"


class User(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    email: str
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ProcessingRequest(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: str
    type: RequestType
    status: RequestStatus = RequestStatus.PENDING
    input: dict
    output: Optional[dict] = None
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add db/models.py tests/test_models.py
git commit -m "feat: pydantic document models for MongoDB"
```

---

## Task 4: Motor Client

**Files:**
- Create: `db/client.py`
- Modify: `tests/conftest.py`

> **Concept:** Motor is the async MongoDB driver. One `AsyncIOMotorClient` manages a connection pool internally — you never create one per request. The pattern is a module-level class with `connect()` / `disconnect()` methods called in FastAPI's lifespan. Indexes are created at startup so the app doesn't start without them.

- [ ] **Step 1: Create tests/conftest.py with shared DB fixture**

```python
# tests/conftest.py
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
```

> **Why a real test database instead of mocks?** Mocking Motor hides real query bugs — a wrong `$set` key silently passes a mock but fails against real MongoDB. A test database on your local machine costs nothing and catches real bugs.

- [ ] **Step 2: Write failing test**

```python
# tests/test_client.py
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
    assert ["status", "created_at"] in index_keys or \
           any("status" in str(k) for k in index_keys)
    await db.disconnect()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'db.client'`

- [ ] **Step 4: Implement db/client.py**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_client.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add db/client.py tests/conftest.py tests/test_client.py
git commit -m "feat: Motor async MongoDB client with indexes"
```

---

## Task 5: Repository Layer

**Files:**
- Create: `db/repository.py`
- Create: `tests/test_repository.py`

> **Concept:** The repository is the only place in the codebase that speaks MongoDB query language. Every other module calls repository methods with Python objects — they never write raw `{"$set": ...}` queries themselves. This makes the DB layer swappable and keeps business logic clean.

> **The most important method here is `lock_next_pending_job`.** This is the atomic operation that makes concurrent workers safe. Read it carefully.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_repository.py
import pytest
from datetime import datetime, timedelta
from bson import ObjectId
from db.repository import RequestRepository
from db.models import ProcessingRequest, RequestStatus, RequestType

@pytest.fixture
async def repo(test_db):
    r = RequestRepository(test_db)
    yield r
    # clean up after each test
    await test_db["processing_requests"].delete_many({})

async def test_create_request(repo):
    req = ProcessingRequest(
        user_id="user1",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    created = await repo.create(req)
    assert created.id is not None
    assert created.status == RequestStatus.PENDING

async def test_get_by_id(repo):
    req = ProcessingRequest(
        user_id="user1",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    created = await repo.create(req)
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.user_id == "user1"

async def test_lock_next_pending_job(repo):
    """Only one caller should win the lock even if called concurrently."""
    req = ProcessingRequest(
        user_id="user1",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    await repo.create(req)

    job1 = await repo.lock_next_pending_job()
    job2 = await repo.lock_next_pending_job()  # nothing left to lock

    assert job1 is not None
    assert job1.status == RequestStatus.PROCESSING
    assert job2 is None  # second caller gets nothing

async def test_mark_completed(repo):
    req = ProcessingRequest(
        user_id="user1",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    created = await repo.create(req)
    await repo.mark_completed(created.id, output={"text": "hello world"})
    fetched = await repo.get_by_id(created.id)
    assert fetched.status == RequestStatus.COMPLETED
    assert fetched.output == {"text": "hello world"}

async def test_mark_failed_retries(repo):
    req = ProcessingRequest(
        user_id="user1",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    created = await repo.create(req)
    # retry_count=0, max_retries=3 → should re-queue to pending
    await repo.mark_failed(created.id, error="tesseract crashed", retry_count=0, max_retries=3)
    fetched = await repo.get_by_id(created.id)
    assert fetched.status == RequestStatus.PENDING
    assert fetched.retry_count == 1

async def test_mark_failed_exhausted(repo):
    req = ProcessingRequest(
        user_id="user1",
        type=RequestType.OCR,
        input={"file_url": "/uploads/test.pdf", "file_type": "pdf"}
    )
    created = await repo.create(req)
    # retry_count=3, max_retries=3 → should set failed
    await repo.mark_failed(created.id, error="tesseract crashed", retry_count=3, max_retries=3)
    fetched = await repo.get_by_id(created.id)
    assert fetched.status == RequestStatus.FAILED
    assert fetched.error == "tesseract crashed"

async def test_reset_stuck_jobs(repo):
    # Insert a job that appears to be stuck in processing for too long
    old_time = datetime.utcnow() - timedelta(minutes=15)
    await test_db["processing_requests"].insert_one({
        "user_id": "user1",
        "type": "ocr",
        "status": "processing",
        "input": {},
        "retry_count": 0,
        "max_retries": 3,
        "updated_at": old_time,
        "created_at": old_time
    })
    count = await repo.reset_stuck_jobs(stuck_after_minutes=10)
    assert count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_repository.py -v
```

Expected: `ModuleNotFoundError: No module named 'db.repository'`

- [ ] **Step 3: Implement db/repository.py**

```python
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from db.models import ProcessingRequest, RequestStatus

class RequestRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["processing_requests"]

    async def create(self, req: ProcessingRequest) -> ProcessingRequest:
        doc = req.model_dump(exclude={"id"}, by_alias=False)
        result = await self.col.insert_one(doc)
        req.id = str(result.inserted_id)
        return req

    async def get_by_id(self, request_id: str) -> Optional[ProcessingRequest]:
        doc = await self.col.find_one({"_id": ObjectId(request_id)})
        if doc is None:
            return None
        return ProcessingRequest(**{**doc, "_id": doc["_id"]})

    async def lock_next_pending_job(self) -> Optional[ProcessingRequest]:
        """
        Atomically find the oldest pending job and mark it as processing.
        Only ONE worker wins this race — the others get None.

        find_one_and_update is a SINGLE MongoDB operation (atomic).
        Even with 10 workers calling this simultaneously, MongoDB
        guarantees only one of them gets the document updated.
        """
        doc = await self.col.find_one_and_update(
            {"status": RequestStatus.PENDING},
            {"$set": {
                "status": RequestStatus.PROCESSING,
                "updated_at": datetime.utcnow()
            }},
            sort=[("created_at", 1)],          # oldest first
            return_document=ReturnDocument.AFTER
        )
        if doc is None:
            return None
        return ProcessingRequest(**{**doc, "_id": doc["_id"]})

    async def mark_completed(self, request_id: str, output: dict) -> None:
        await self.col.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {
                "status": RequestStatus.COMPLETED,
                "output": output,
                "updated_at": datetime.utcnow()
            }}
        )

    async def mark_failed(
        self,
        request_id: str,
        error: str,
        retry_count: int,
        max_retries: int
    ) -> None:
        if retry_count < max_retries:
            # Re-queue: set back to pending, increment retry_count
            # This automatically re-triggers the Change Stream on the worker
            await self.col.update_one(
                {"_id": ObjectId(request_id)},
                {"$set": {
                    "status": RequestStatus.PENDING,
                    "error": error,
                    "updated_at": datetime.utcnow()
                },
                "$inc": {"retry_count": 1}}
            )
        else:
            # Exhausted retries — mark as permanently failed
            await self.col.update_one(
                {"_id": ObjectId(request_id)},
                {"$set": {
                    "status": RequestStatus.FAILED,
                    "error": error,
                    "updated_at": datetime.utcnow()
                }}
            )

    async def reset_stuck_jobs(self, stuck_after_minutes: int) -> int:
        """
        Fallback: find jobs stuck in 'processing' (worker crashed mid-job)
        and reset them to 'pending' so they get picked up again.
        """
        threshold = datetime.utcnow() - timedelta(minutes=stuck_after_minutes)
        result = await self.col.update_many(
            {"status": RequestStatus.PROCESSING, "updated_at": {"$lt": threshold}},
            {"$set": {"status": RequestStatus.PENDING, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_repository.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add db/repository.py tests/test_repository.py tests/conftest.py
git commit -m "feat: repository layer with atomic job locking"
```

---

## Task 6: Security (JWT + Passwords)

**Files:**
- Create: `core/security.py`
- Create: `tests/test_security.py`

> **Concept:** We never store plain-text passwords. `passlib` hashes them with bcrypt (a slow, salted hash designed to be expensive to brute-force). JWTs are signed tokens — the server signs them with `JWT_SECRET`, the client sends them back in the `Authorization` header, and we verify the signature without hitting the DB on every request.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_security.py
from core.security import hash_password, verify_password, create_token, decode_token

def test_hash_and_verify():
    hashed = hash_password("mysecretpassword")
    assert hashed != "mysecretpassword"           # never stored plain
    assert verify_password("mysecretpassword", hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_create_and_decode_token():
    token = create_token({"sub": "user123"})
    payload = decode_token(token)
    assert payload["sub"] == "user123"

def test_expired_token_raises():
    import pytest
    from jose import JWTError
    # Create a token that expired 1 second ago
    token = create_token({"sub": "user123"}, expires_minutes=-1)
    with pytest.raises(JWTError):
        decode_token(token)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.security'`

- [ ] **Step 3: Implement core/security.py**

```python
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(data: dict, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.JWT_EXPIRE_MINUTES
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=minutes)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def decode_token(token: str) -> dict:
    # Raises jose.JWTError if invalid or expired
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_security.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add core/security.py tests/test_security.py
git commit -m "feat: JWT and bcrypt password security"
```

---

## Task 7: Storage Layer

**Files:**
- Create: `storage/local.py`
- Create: `tests/test_storage.py`

> **Concept:** The storage module validates files (size, MIME type) and saves them to disk. The interface is designed to be S3-swappable — if you later want cloud storage, you only change this file.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_storage.py
import pytest
import io
from fastapi import UploadFile
from storage.local import LocalStorage

@pytest.fixture
def storage(tmp_path):
    return LocalStorage(upload_dir=str(tmp_path))

async def test_save_image(storage):
    content = b"fake image content"
    file = UploadFile(filename="test.jpg", file=io.BytesIO(content))
    file_url = await storage.save(file, max_size_mb=20)
    assert "test" in file_url
    assert file_url.endswith(".jpg")

async def test_rejects_oversized_file(storage):
    # 21 MB of zeros
    content = b"0" * (21 * 1024 * 1024)
    file = UploadFile(filename="big.pdf", file=io.BytesIO(content))
    with pytest.raises(ValueError, match="exceeds"):
        await storage.save(file, max_size_mb=20)

async def test_rejects_invalid_extension(storage):
    content = b"malicious"
    file = UploadFile(filename="script.exe", file=io.BytesIO(content))
    with pytest.raises(ValueError, match="not allowed"):
        await storage.save(file, max_size_mb=20)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_storage.py -v
```

Expected: `ModuleNotFoundError: No module named 'storage.local'`

- [ ] **Step 3: Implement storage/local.py**

```python
import uuid
import os
import aiofiles
from pathlib import Path
from fastapi import UploadFile

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

class LocalStorage:
    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, max_size_mb: int) -> str:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Extension {ext} not allowed. Use: {ALLOWED_EXTENSIONS}")

        content = await file.read()

        max_bytes = max_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"File size {len(content)} exceeds {max_size_mb}MB limit")

        filename = f"{uuid.uuid4()}{ext}"
        dest = self.upload_dir / filename

        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)

        return str(dest)

    def get_path(self, file_url: str) -> Path:
        return Path(file_url)
```

- [ ] **Step 4: Add aiofiles to requirements.txt**

```
aiofiles==24.1.0
```

```bash
pip install aiofiles
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_storage.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add storage/local.py tests/test_storage.py requirements.txt
git commit -m "feat: local file storage with validation"
```

---

## Task 8: OCR Engine

**Files:**
- Create: `ocr/engine.py`
- Create: `ocr/pdf_processor.py`
- Create: `tests/test_ocr.py`
- Create: `tests/fixtures/sample.png` (you provide a test image)

> **YOUR TURN — this is the core of your service.**
> After creating the fixture and reading the concept below, implement `engine.py` and `pdf_processor.py` yourself.

> **Concept:** Tesseract is a C program — calling it from Python (`pytesseract.image_to_string`) blocks the current thread. In an async program, blocking the thread freezes the entire event loop — no other coroutines can run while Tesseract works. `asyncio.to_thread()` moves the blocking call into a thread pool worker, freeing the event loop. `asyncio.gather()` runs all page extractions concurrently in the thread pool.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ocr.py
import pytest
from pathlib import Path
from ocr.engine import extract_text_from_image
from ocr.pdf_processor import extract_text_from_pdf

FIXTURES = Path("tests/fixtures")

async def test_extract_from_image():
    # Use any real image with text — place it at tests/fixtures/sample.png
    text = await extract_text_from_image(str(FIXTURES / "sample.png"))
    assert isinstance(text, str)
    assert len(text) > 0

async def test_extract_from_pdf():
    # Use any real PDF — place it at tests/fixtures/sample.pdf
    text = await extract_text_from_pdf(str(FIXTURES / "sample.pdf"))
    assert isinstance(text, str)
    assert len(text) > 0
```

- [ ] **Step 2: Add test fixtures**

Place a real image with visible text at `tests/fixtures/sample.png` and a real PDF at `tests/fixtures/sample.pdf`. These can be any document — a screenshot, a scan, anything with readable text.

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_ocr.py -v
```

Expected: `ModuleNotFoundError: No module named 'ocr.engine'`

- [ ] **Step 4: YOUR TURN — implement ocr/engine.py**

In `ocr/engine.py`, implement `extract_text_from_image(file_path: str) -> str`.

**Constraints:**
- Must be an `async def` function
- Must use `asyncio.to_thread()` to call `pytesseract.image_to_string`
- Open the image with `PIL.Image.open(file_path)` before passing to Tesseract

```python
# ocr/engine.py
import asyncio
import pytesseract
from PIL import Image

async def extract_text_from_image(file_path: str) -> str:
    # YOUR TURN: implement this
    # Hint: image = Image.open(file_path)
    # Hint: await asyncio.to_thread(pytesseract.image_to_string, image)
    ...
```

- [ ] **Step 5: YOUR TURN — implement ocr/pdf_processor.py**

In `ocr/pdf_processor.py`, implement `extract_text_from_pdf(file_path: str) -> str`.

**Constraints:**
- Must convert PDF pages to images with `pdf2image.convert_from_path`
- That call is blocking — wrap it in `asyncio.to_thread()`
- Must run OCR on ALL pages concurrently using `asyncio.gather()`
- Join pages with `"\n\n"` separator

```python
# ocr/pdf_processor.py
import asyncio
from pdf2image import convert_from_path
from ocr.engine import extract_text_from_image
import tempfile
from pathlib import Path

async def extract_text_from_pdf(file_path: str) -> str:
    # YOUR TURN: implement this
    # Step 1: await asyncio.to_thread(convert_from_path, file_path) → list of PIL images
    # Step 2: save each image to a temp file (Tesseract needs a file path)
    # Step 3: asyncio.gather all extract_text_from_image calls
    # Step 4: join results with "\n\n"
    ...
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/test_ocr.py -v
```

Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add ocr/engine.py ocr/pdf_processor.py tests/test_ocr.py
git commit -m "feat: async Tesseract OCR engine and PDF processor"
```

---

## Task 9: WebSocket Manager

**Files:**
- Create: `websockets/manager.py`
- Create: `tests/test_ws_manager.py`

> **Concept:** The `ConnectionManager` is an in-memory dictionary mapping `request_id → WebSocket`. It lives for the lifetime of the FastAPI process. When the API-side Change Stream sees a job complete, it looks up the WebSocket for that job's ID and pushes the result. If the client disconnected, the push is silently skipped.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ws_manager.py
import pytest
from unittest.mock import AsyncMock, MagicMock
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
    # Push to non-existent connection should not raise
    await manager.push("req_999", {"status": "completed"})  # no error
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ws_manager.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement websockets/manager.py**

```python
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, request_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.active[request_id] = ws

    async def disconnect(self, request_id: str) -> None:
        self.active.pop(request_id, None)

    async def push(self, request_id: str, data: dict) -> None:
        ws = self.active.get(request_id)
        if ws is None:
            return
        try:
            await ws.send_json(data)
        except Exception:
            # Client disconnected mid-stream — clean up silently
            await self.disconnect(request_id)

# Module-level singleton shared across the app
manager = ConnectionManager()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_ws_manager.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add websockets/manager.py tests/test_ws_manager.py
git commit -m "feat: WebSocket connection manager"
```

---

## Task 10: API Dependencies + Auth Routes

**Files:**
- Create: `api/deps.py`
- Create: `api/routes/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Implement api/deps.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from jose import JWTError
from core.security import decode_token
from db.client import db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_db() -> AsyncIOMotorDatabase:
    return db.get_db()

async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """
    Validates the JWT and returns {"user_id": "..."}.
    No DB lookup needed — the user_id is embedded in the signed token.
    If the token is forged or expired, jose raises JWTError → 401.
    """
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return {"user_id": user_id}
```

- [ ] **Step 2: Implement api/routes/auth.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr
from core.security import hash_password, verify_password, create_token
from api.deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterBody(BaseModel):
    email: EmailStr
    password: str

class LoginBody(BaseModel):
    email: EmailStr
    password: str

@router.post("/register", status_code=201)
async def register(body: RegisterBody, db: AsyncIOMotorDatabase = Depends(get_db)):
    existing = await db["users"].find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    await db["users"].insert_one({
        "email": body.email,
        "hashed_password": hash_password(body.password)
    })
    return {"message": "registered"}

@router.post("/login")
async def login(body: LoginBody, db: AsyncIOMotorDatabase = Depends(get_db)):
    user = await db["users"].find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": str(user["_id"])})
    return {"access_token": token, "token_type": "bearer"}
```

- [ ] **Step 3: Write failing API tests**

```python
# tests/test_auth.py
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
```

- [ ] **Step 4: Run test to verify it fails**

```bash
pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'` — we need main.py next.

---

## Task 11: FastAPI App Entry Point

**Files:**
- Create: `main.py`
- Create: `watcher/api_stream.py`

- [ ] **Step 1: Implement watcher/api_stream.py**

> **Concept:** This Change Stream runs inside the FastAPI process. It watches for documents where status flips to `completed` or `failed`. When it sees one, it pushes the result to the waiting WebSocket client. The `$match` pipeline filter means MongoDB only sends the event to Python if the status is one we care about — reducing unnecessary network traffic.

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from websockets.manager import manager

async def watch_completions(db: AsyncIOMotorDatabase) -> None:
    """
    API-side Change Stream: watches processing_requests for completed/failed status.
    Pushes results to the connected WebSocket client for that request_id.
    Runs forever as a background asyncio task inside the FastAPI process.
    """
    pipeline = [
        {"$match": {
            "operationType": "update",
            "updateDescription.updatedFields.status": {
                "$in": ["completed", "failed"]
            }
        }}
    ]
    col = db["processing_requests"]
    async with col.watch(pipeline, full_document="updateLookup") as stream:
        async for event in stream:
            doc = event.get("fullDocument")
            if not doc:
                continue
            request_id = str(doc["_id"])
            status = doc.get("status")
            payload = {"status": status}
            if status == "completed":
                payload["output"] = doc.get("output")
            else:
                payload["error"] = doc.get("error")
            await manager.push(request_id, payload)
```

- [ ] **Step 2: Implement main.py**

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from db.client import db
from api.routes import auth, upload, requests
from api.deps import get_current_user
from watcher.api_stream import watch_completions
from websockets.manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────
    await db.connect(settings.MONGO_URL, settings.DB_NAME)
    await db.create_indexes()
    database = db.get_db()
    asyncio.create_task(watch_completions(database))
    yield
    # ── SHUTDOWN ─────────────────────────────────────────────
    await db.disconnect()

app = FastAPI(title="OCR Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(requests.router)

@app.websocket("/ws/{request_id}")
async def websocket_endpoint(request_id: str, ws: WebSocket):
    await manager.connect(request_id, ws)
    try:
        while True:
            # Keep connection alive — client sends pings
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(request_id)
```

- [ ] **Step 3: Run auth tests (should now pass)**

```bash
pytest tests/test_auth.py -v
```

Expected: `3 passed`

- [ ] **Step 4: Commit**

```bash
git add main.py watcher/api_stream.py api/routes/auth.py api/deps.py tests/test_auth.py
git commit -m "feat: FastAPI app with lifespan, auth routes, WebSocket endpoint"
```

---

## Task 12: Upload + Request Routes

**Files:**
- Create: `api/routes/upload.py`
- Create: `api/routes/requests.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Implement api/routes/upload.py**

```python
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from core.config import settings
from storage.local import LocalStorage
from api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["upload"])
storage = LocalStorage(settings.STORAGE_PATH)

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    try:
        file_url = await storage.save(file, max_size_mb=settings.MAX_FILE_SIZE_MB)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    suffix = file.filename.rsplit(".", 1)[-1].lower()
    file_type = "pdf" if suffix == "pdf" else "image"

    return {"file_url": file_url, "file_type": file_type}
```

- [ ] **Step 2: Implement api/routes/requests.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from db.repository import RequestRepository
from db.models import ProcessingRequest, RequestType
from api.deps import get_db, get_current_user

router = APIRouter(prefix="/api", tags=["requests"])

class CreateRequestBody(BaseModel):
    type: RequestType
    file_url: str
    file_type: str  # "pdf" or "image"

@router.post("/request", status_code=201)
async def create_request(
    body: CreateRequestBody,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user)
):
    repo = RequestRepository(db)
    req = ProcessingRequest(
        user_id=user["user_id"],
        type=body.type,
        input={"file_url": body.file_url, "file_type": body.file_type},
        max_retries=3
    )
    created = await repo.create(req)
    return {"request_id": created.id, "status": created.status}

@router.get("/request/{request_id}")
async def get_request(
    request_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user)
):
    repo = RequestRepository(db)
    req = await repo.get_by_id(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return {
        "request_id": req.id,
        "status": req.status,
        "output": req.output,
        "error": req.error,
        "retry_count": req.retry_count
    }
```

- [ ] **Step 3: Write API integration tests**

```python
# tests/test_api.py
import pytest
import io
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
```

- [ ] **Step 4: Run API tests**

```bash
pytest tests/test_api.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add api/routes/upload.py api/routes/requests.py tests/test_api.py
git commit -m "feat: upload and request routes"
```

---

## Task 13: Worker — Change Stream + Polling

**Files:**
- Create: `watcher/change_stream.py`
- Create: `watcher/polling.py`
- Create: `worker.py`

> **YOUR TURN — the worker is the heart of the system.**
> The scaffolding is provided. You implement the job processing loop.

- [ ] **Step 1: Implement watcher/polling.py**

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from db.repository import RequestRepository
from core.config import settings

async def run_fallback_polling(db: AsyncIOMotorDatabase) -> None:
    """
    Runs forever. Every POLL_INTERVAL_SECONDS, scans for jobs stuck in
    'processing' (worker crashed mid-job) and resets them to 'pending'.
    """
    repo = RequestRepository(db)
    while True:
        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
        count = await repo.reset_stuck_jobs(settings.MAX_PROCESSING_MINUTES)
        if count > 0:
            print(f"[polling] Reset {count} stuck job(s) back to pending")
```

- [ ] **Step 2: Scaffold watcher/change_stream.py — YOUR TURN**

The structure is given. Implement `_process_job`:

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from db.repository import RequestRepository
from db.models import RequestStatus
from core.config import settings

async def _process_job(job, repo: RequestRepository) -> None:
    """
    YOUR TURN: implement job processing.

    You have:
    - job.id            → string request ID
    - job.input         → {"file_url": "...", "file_type": "pdf" or "image"}
    - job.retry_count   → how many times this job has been retried
    - job.max_retries   → max allowed retries

    Steps:
    1. Extract file_url and file_type from job.input
    2. Call the right OCR function based on file_type:
       - "pdf"   → from ocr.pdf_processor import extract_text_from_pdf
       - "image" → from ocr.engine import extract_text_from_image
    3. On success: call repo.mark_completed(job.id, output={"text": text})
    4. On exception: call repo.mark_failed(job.id, error=str(e),
                       retry_count=job.retry_count, max_retries=job.max_retries)
    """
    ...


async def run_change_stream(db: AsyncIOMotorDatabase, semaphore: asyncio.Semaphore) -> None:
    """
    Watches MongoDB for new 'pending' jobs. Uses a semaphore to limit
    how many OCR jobs run concurrently per worker process.
    """
    repo = RequestRepository(db)
    col = db["processing_requests"]

    pipeline = [{"$match": {
        "operationType": "insert",
    }}]

    print("[worker] Change Stream started — waiting for pending jobs...")

    async with col.watch(pipeline) as stream:
        async for _ in stream:
            # A new document was inserted — try to lock it atomically
            # (the Change Stream just signals "something new appeared",
            #  find_one_and_update is what actually picks it up safely)
            job = await repo.lock_next_pending_job()
            if job is None:
                continue  # another worker got it first

            print(f"[worker] Processing job {job.id} (attempt {job.retry_count + 1})")
            async with semaphore:
                asyncio.create_task(_process_job(job, repo))
```

- [ ] **Step 3: Implement worker.py**

```python
import asyncio
from core.config import settings
from db.client import db
from watcher.change_stream import run_change_stream
from watcher.polling import run_fallback_polling

async def main():
    print("[worker] Connecting to MongoDB...")
    await db.connect(settings.MONGO_URL, settings.DB_NAME)
    database = db.get_db()
    semaphore = asyncio.Semaphore(settings.WORKER_CONCURRENCY)
    print(f"[worker] Ready. Concurrency: {settings.WORKER_CONCURRENCY}")
    await asyncio.gather(
        run_change_stream(database, semaphore),
        run_fallback_polling(database)
    )

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Implement _process_job (your implementation from Step 2)**

Run the tests after implementing:

```bash
pytest tests/ -v
```

Expected: all previous tests still pass.

- [ ] **Step 5: Commit**

```bash
git add watcher/change_stream.py watcher/polling.py worker.py
git commit -m "feat: worker change stream listener and fallback polling"
```

---

## Task 14: End-to-End Smoke Test

**Goal:** Verify the full system works — API creates a job, worker picks it up, WebSocket client gets notified.

- [ ] **Step 1: Start MongoDB**

```bash
# Verify MongoDB is running
mongosh --eval "db.runCommand({ping: 1})"
```

Expected: `{ ok: 1 }`

- [ ] **Step 2: Start the API server**

```bash
uvicorn main:app --reload --port 8000
```

Expected log: `Application startup complete.`

- [ ] **Step 3: Start a worker (new terminal)**

```bash
python worker.py
```

Expected log: `[worker] Change Stream started — waiting for pending jobs...`

- [ ] **Step 4: Register and get a token**

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke@test.com","password":"password123"}'

curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke@test.com","password":"password123"}'
```

Copy the `access_token` from the login response.

- [ ] **Step 5: Create an OCR request**

```bash
curl -X POST http://localhost:8000/api/request \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"type":"ocr","file_url":"tests/fixtures/sample.png","file_type":"image"}'
```

Copy the `request_id`.

- [ ] **Step 6: Poll for result**

```bash
curl http://localhost:8000/api/request/<request_id> \
  -H "Authorization: Bearer <your_token>"
```

Expected: `"status": "completed"` with `"output": {"text": "..."}` within a few seconds.

- [ ] **Step 7: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Final commit**

```bash
git add .
git commit -m "feat: complete OCR service with FastAPI, Motor, Change Streams, WebSockets"
```

---

## Spec Coverage Checklist

| Requirement | Task |
|---|---|
| POST /api/upload | Task 12 |
| POST /api/request | Task 12 |
| GET /api/request/{id} | Task 12 |
| JWT authentication | Task 6, 10 |
| status: pending→processing→completed/failed | Task 5 |
| Atomic job locking | Task 5 |
| Change Stream worker | Task 13 |
| Fallback polling | Task 13 |
| Retry mechanism | Task 5 |
| asyncio.to_thread for OCR | Task 8 |
| asyncio.gather for PDF pages | Task 8 |
| WebSocket real-time push | Task 9, 11 |
| MongoDB indexes | Task 4 |
| pydantic-settings config | Task 2 |
| File validation (size, type) | Task 7 |
| FastAPI lifespan | Task 11 |
| Dependency injection | Task 10 |
| Horizontal scaling (multiple workers) | Task 13, 14 |
