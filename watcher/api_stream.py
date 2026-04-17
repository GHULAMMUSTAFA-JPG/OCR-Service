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
