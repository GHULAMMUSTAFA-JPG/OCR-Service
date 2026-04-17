import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from db.repository import RequestRepository
from core.config import settings


async def run_fallback_polling(db: AsyncIOMotorDatabase) -> None:
    """
    Runs forever. Every POLL_INTERVAL_SECONDS, scans for jobs stuck in
    'processing' (worker crashed mid-job) and resets them to 'pending'.

    WHY this exists:
    Change Streams are reliable but not perfect — if a worker process crashes
    while processing a job, the job stays locked in 'processing' forever and
    never re-triggers the Change Stream. Polling catches these orphaned jobs
    and re-queues them so they get picked up again.
    """
    repo = RequestRepository(db)
    while True:
        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
        count = await repo.reset_stuck_jobs(settings.MAX_PROCESSING_MINUTES)
        if count > 0:
            print(f"[polling] Reset {count} stuck job(s) back to pending")
