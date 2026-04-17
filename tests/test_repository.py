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

async def test_mark_failed_retries(repo, test_db):
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

async def test_reset_stuck_jobs(repo, test_db):
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
