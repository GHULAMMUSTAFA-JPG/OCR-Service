import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from db.repository import RequestRepository
from db.models import RequestStatus
from core.config import settings


async def _process_job(job, repo: RequestRepository) -> None:
    """
    Process a single OCR job:
    - read file_url and file_type from job.input
    - call the right OCR function
    - mark completed on success, failed on exception (with retry logic)
    """
    file_url = job.input["file_url"]
    file_type = job.input["file_type"]

    try:
        if file_type == "pdf":
            from ocr.pdf_processor import extract_text_from_pdf
            text = await extract_text_from_pdf(file_url)
        else:
            from ocr.engine import extract_text_from_image
            text = await extract_text_from_image(file_url)

        await repo.mark_completed(job.id, output={"text": text})
        print(f"[worker] Job {job.id} completed — {len(text)} chars extracted")

    except Exception as e:
        print(f"[worker] Job {job.id} failed (attempt {job.retry_count + 1}): {e}")
        await repo.mark_failed(
            job.id,
            error=str(e),
            retry_count=job.retry_count,
            max_retries=job.max_retries
        )


async def run_change_stream(db: AsyncIOMotorDatabase, semaphore: asyncio.Semaphore) -> None:
    """
    Watches MongoDB for new 'pending' jobs via Change Stream.
    Uses find_one_and_update to atomically claim one job at a time.
    Semaphore limits how many OCR jobs run concurrently per worker process.
    """
    repo = RequestRepository(db)
    col = db["processing_requests"]

    # Only fire when a new document is inserted (a new job created)
    pipeline = [{"$match": {"operationType": "insert"}}]

    print("[worker] Change Stream started — waiting for pending jobs...")

    async with col.watch(pipeline) as stream:
        async for _ in stream:
            # The Change Stream signals "something was inserted"
            # find_one_and_update does the actual atomic claim
            job = await repo.lock_next_pending_job()
            if job is None:
                continue  # another worker got it first

            print(f"[worker] Picked up job {job.id} (attempt {job.retry_count + 1})")
            async with semaphore:
                asyncio.create_task(_process_job(job, repo))
