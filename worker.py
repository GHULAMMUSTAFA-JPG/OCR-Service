import asyncio
from core.config import settings
from db.client import db
from watcher.change_stream import run_change_stream
from watcher.polling import run_fallback_polling


async def main():
    print("[worker] Connecting to MongoDB...")
    await db.connect(settings.MONGO_URL, settings.DB_NAME)
    database = db.get_db()

    # Semaphore limits how many OCR jobs run at the same time in this process
    # e.g. WORKER_CONCURRENCY=3 means max 3 Tesseract threads running simultaneously
    semaphore = asyncio.Semaphore(settings.WORKER_CONCURRENCY)

    print(f"[worker] Ready. Max concurrent jobs: {settings.WORKER_CONCURRENCY}")

    # Run both the Change Stream listener and fallback polling at the same time
    # asyncio.gather keeps both coroutines alive forever — if one crashes, both stop
    await asyncio.gather(
        run_change_stream(database, semaphore),
        run_fallback_polling(database)
    )


if __name__ == "__main__":
    asyncio.run(main())
