import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

class LocalStorage:
    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, max_size_mb: int) -> str:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Extension {ext} not allowed. Use: {ALLOWED_EXTENSIONS}")

        content = await file.read()

        max_bytes = max_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"File size {len(content)} exceeds {max_size_mb}MB limit")

        filename = f"{uuid.uuid4()}{ext}"
        dest = self.upload_dir / filename

        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)

        return str(dest)

    def get_path(self, file_url: str) -> Path:
        return Path(file_url)
