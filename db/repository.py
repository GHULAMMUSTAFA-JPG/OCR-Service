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
