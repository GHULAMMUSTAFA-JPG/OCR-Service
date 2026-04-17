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
    file_type: str

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
