from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from bson import ObjectId
from pydantic import BaseModel, Field


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
