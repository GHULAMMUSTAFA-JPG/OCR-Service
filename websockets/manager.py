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
            await self.disconnect(request_id)

# Module-level singleton shared across the app
manager = ConnectionManager()
