# OCR Service Design Spec
**Date:** 2026-04-17
**Scope:** OCR + FastAPI + MongoDB Watcher (user's portion of AI-Powered PDF Processing Platform)
**Stack:** FastAPI · Motor (async MongoDB) · Tesseract · pdf2image · WebSockets · pydantic-settings

---

## 1. Goals

- Learn MongoDB fundamentals: collections, documents, indexes, Change Streams
- Learn FastAPI patterns: lifespan, dependency injection, WebSockets
- Build a production-grade OCR service: concurrent, horizontally scalable, fault-tolerant
- Implement job queue entirely in MongoDB — no Redis, no Celery

---

## 2. Project Structure

```
ocr-service/
├── main.py                        # FastAPI entry point → uvicorn main:app
├── worker.py                      # Worker entry point → python worker.py
├── .env                           # Environment variables
├── requirements.txt
│
├── api/
│   ├── routes/
│   │   ├── upload.py              # POST /api/upload
│   │   └── requests.py           # POST /api/request, GET /api/request/{id}
│   └── deps.py                   # FastAPI dependencies (db, current_user)
│
├── db/
│   ├── client.py                  # Motor client singleton
│   ├── models.py                  # Pydantic document models
│   └── repository.py              # All MongoDB operations
│
├── watcher/
│   ├── change_stream.py           # Worker: watches pending jobs
│   ├── api_stream.py              # API: watches completed/failed → WebSocket push
│   └── polling.py                 # Fallback: resets stuck processing jobs
│
├── ocr/
│   ├── engine.py                  # Tesseract wrapper (asyncio.to_thread)
│   └── pdf_processor.py           # PDF → images via pdf2image
│
├── core/
│   ├── config.py                  # Settings via pydantic-settings
│   └── security.py                # JWT encode/decode
│
├── storage/
│   └── local.py                   # File save/read (S3-ready interface)
│
└── websockets/
    └── manager.py                 # ConnectionManager: request_id → WebSocket
```

---

## 3. MongoDB Data Model

### Collection: `users`
```json
{
  "_id": "ObjectId",
  "email": "string",
  "hashed_password": "string",
  "created_at": "ISODate"
}
```

### Collection: `processing_requests`
```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "type": "ocr",
  "status": "pending | processing | completed | failed",
  "input": {
    "file_url": "string",
    "file_type": "pdf | image"
  },
  "output": {
    "text": "string"
  },
  "retry_count": 0,
  "max_retries": 3,
  "error": null,
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

### Indexes
```python
# Index 1: Worker query — oldest pending job first
{"status": 1, "created_at": 1}

# Index 2: Analytics — jobs by type and status
{"type": 1, "status": 1}
```

---

## 4. Status Flow

```
pending → processing → completed
                     → failed (retry_count < max_retries → back to pending)
```

- **pending**: job created, waiting for worker
- **processing**: atomically locked by one worker
- **completed**: OCR finished, output.text populated
- **failed**: exhausted retries, error message stored

---

## 5. Concurrency Model

| Layer | Tool | Reason |
|---|---|---|
| MongoDB I/O | Motor (async) | Non-blocking, shares event loop |
| File I/O | asyncio.to_thread() | Offloads blocking calls |
| Tesseract OCR | asyncio.to_thread() | CPU-bound, must leave event loop |
| Concurrent jobs per worker | asyncio.Semaphore(N) | Limits parallel OCR tasks |
| True parallelism | Multiple worker.py processes | Beats GIL for CPU work |

### Atomic Job Locking
```python
job = await collection.find_one_and_update(
    {"status": "pending"},
    {"$set": {"status": "processing", "updated_at": datetime.utcnow()}},
    sort=[("created_at", 1)],   # oldest first
    return_document=True
)
# job is None if no pending work — only ONE worker wins the race
```

---

## 6. WebSocket Architecture

### Connection Flow
```
Frontend opens ws://server/ws/{request_id}
API stores {request_id: websocket} in ConnectionManager

Worker updates MongoDB: status = completed
API-side Change Stream fires
API calls manager.push(request_id, {status, output})
Frontend receives result
```

### ConnectionManager (`websockets/manager.py`)
```python
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, request_id: str, ws: WebSocket): ...
    async def disconnect(self, request_id: str): ...
    async def push(self, request_id: str, data: dict): ...
```

### WebSocket Route
```
GET /ws/{request_id}   → upgrades to WebSocket, registers in manager
```

---

## 7. API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /api/upload | JWT | Upload PDF or image, returns file_url |
| POST | /api/request | JWT | Create OCR job, returns request_id |
| GET | /api/request/{id} | JWT | Poll status + result |
| GET | /ws/{request_id} | JWT | WebSocket — realtime status push |
| POST | /auth/register | None | Create user |
| POST | /auth/login | None | Returns JWT token |

---

## 8. FastAPI Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await db.connect()
    await db.create_indexes()
    asyncio.create_task(watch_completions())  # API-side Change Stream
    yield
    # SHUTDOWN
    await db.disconnect()

app = FastAPI(lifespan=lifespan)
```

---

## 9. Worker Entry Point

```python
# worker.py — run as: python worker.py
async def main():
    await db.connect()
    semaphore = asyncio.Semaphore(settings.WORKER_CONCURRENCY)
    await asyncio.gather(
        run_change_stream(semaphore),   # primary: Change Stream
        run_fallback_polling(semaphore) # secondary: catch stuck jobs
    )

asyncio.run(main())
```

---

## 10. Fallback Polling

Runs every `POLL_INTERVAL_SECONDS`. Finds jobs stuck in `processing` for longer than `MAX_PROCESSING_MINUTES` (crashed worker didn't update status) and resets them to `pending`.

```python
stuck_threshold = datetime.utcnow() - timedelta(minutes=settings.MAX_PROCESSING_MINUTES)
await collection.update_many(
    {"status": "processing", "updated_at": {"$lt": stuck_threshold}},
    {"$set": {"status": "pending", "updated_at": datetime.utcnow()}}
)
```

---

## 11. Retry Logic

On OCR failure:
- `retry_count < max_retries` → set `status = pending`, increment `retry_count` → re-queues automatically via Change Stream
- `retry_count >= max_retries` → set `status = failed`, store `error` message

---

## 12. OCR Pipeline

```
Input: file_url, file_type

if file_type == "image":
    image = PIL.Image.open(file_path)
    text = await asyncio.to_thread(pytesseract.image_to_string, image)

if file_type == "pdf":
    images = await asyncio.to_thread(pdf2image.convert_from_path, file_path)
    # asyncio.gather runs all page OCR concurrently, not sequentially
    pages = await asyncio.gather(*[
        asyncio.to_thread(pytesseract.image_to_string, img) for img in images
    ])
    text = "\n\n".join(pages)

Output: {"text": text}
```

---

## 13. Environment Variables

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=ocr_service
JWT_SECRET=your-secret-key
JWT_EXPIRE_MINUTES=60
MAX_RETRIES=3
WORKER_CONCURRENCY=3
POLL_INTERVAL_SECONDS=60
MAX_PROCESSING_MINUTES=10
MAX_FILE_SIZE_MB=20
STORAGE_PATH=./storage/uploads
```

---

## 14. Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# Terminal 1 — API
uvicorn main:app --reload --port 8000

# Terminal 2 — Worker (scale by opening more terminals)
python worker.py

# Terminal 3 — Second worker (competes atomically for same jobs)
python worker.py
```

---

## 15. Requirements

```
fastapi
uvicorn[standard]
motor
pydantic-settings
pydantic[email]
python-jose[cryptography]
passlib[bcrypt]
python-multipart
pytesseract
pdf2image
Pillow
python-dotenv
```
