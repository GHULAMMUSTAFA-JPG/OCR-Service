import pytest
import io
from fastapi import UploadFile
from storage.local import LocalStorage

@pytest.fixture
def storage(tmp_path):
    return LocalStorage(upload_dir=str(tmp_path))

async def test_save_image(storage):
    content = b"fake image content"
    file = UploadFile(filename="test.jpg", file=io.BytesIO(content))
    file_url = await storage.save(file, max_size_mb=20)
    assert "test" in file_url or file_url.endswith(".jpg")
    assert file_url.endswith(".jpg")

async def test_rejects_oversized_file(storage):
    content = b"0" * (21 * 1024 * 1024)
    file = UploadFile(filename="big.pdf", file=io.BytesIO(content))
    with pytest.raises(ValueError, match="exceeds"):
        await storage.save(file, max_size_mb=20)

async def test_rejects_invalid_extension(storage):
    content = b"malicious"
    file = UploadFile(filename="script.exe", file=io.BytesIO(content))
    with pytest.raises(ValueError, match="not allowed"):
        await storage.save(file, max_size_mb=20)
