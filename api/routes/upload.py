from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from core.config import settings
from storage.local import LocalStorage
from api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["upload"])
storage = LocalStorage(settings.STORAGE_PATH)

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    try:
        file_url = await storage.save(file, max_size_mb=settings.MAX_FILE_SIZE_MB)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    suffix = file.filename.rsplit(".", 1)[-1].lower()
    file_type = "pdf" if suffix == "pdf" else "image"

    return {"file_url": file_url, "file_type": file_type}
