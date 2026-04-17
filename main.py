import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from db.client import db
from api.routes import auth
from api.routes import upload, requests as req_routes
from api.deps import get_current_user
from watcher.api_stream import watch_completions
from websockets.manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await db.connect(settings.MONGO_URL, settings.DB_NAME)
    await db.create_indexes()
    database = db.get_db()
    asyncio.create_task(watch_completions(database))
    yield
    # SHUTDOWN
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
app.include_router(req_routes.router)

@app.websocket("/ws/{request_id}")
async def websocket_endpoint(request_id: str, ws: WebSocket):
    await manager.connect(request_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(request_id)
