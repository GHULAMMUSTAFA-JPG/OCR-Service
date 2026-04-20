# OCR Service

Async OCR pipeline built with FastAPI and MongoDB. Upload an image or PDF, get extracted text back via WebSocket when processing completes.

## Architecture

Two processes run independently:

```
FastAPI (main.py)          Worker (worker.py)
──────────────────         ──────────────────
POST /upload               Change Stream listener
POST /auth/register        Runs Tesseract / pdf2image
POST /auth/login           Retries on failure
GET  /requests/{id}        Fallback polling
WS   /ws/{id}  ←──── MongoDB Change Stream ────→ marks completed
```

The API never runs OCR. The worker never serves HTTP. MongoDB Change Streams connect them.

## Requirements

- Python 3.11+
- MongoDB 6+ (replica set required for Change Streams)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and on PATH
- Poppler (for PDF support) — `apt install poppler-utils` / `brew install poppler`

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=ocr_service
JWT_SECRET=change-this-secret
JWT_EXPIRE_MINUTES=60
WORKER_CONCURRENCY=3
MAX_FILE_SIZE_MB=20
STORAGE_PATH=./storage/uploads
POLL_INTERVAL_SECONDS=60
MAX_PROCESSING_MINUTES=10
```

## Running

Start both processes (each in its own terminal):

```bash
# Terminal 1 — API
uvicorn main:app --reload

# Terminal 2 — Worker
python worker.py
```

## API

### Auth

```
POST /auth/register    { "email": "...", "password": "..." }
POST /auth/login       { "email": "...", "password": "..." }  → { "access_token": "..." }
```

### Upload & track

```
POST /upload                          multipart file, Bearer token required
                                      → { "request_id": "..." }

GET  /requests/{request_id}           → { "status": "pending|processing|completed|failed", ... }

WS   /ws/{request_id}                 connect to receive push notification when done
                                      ← { "status": "completed", "output": { "text": "..." } }
```

Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png` — max 20 MB by default.

## Tests

```bash
pytest
```
