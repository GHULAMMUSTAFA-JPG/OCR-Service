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
