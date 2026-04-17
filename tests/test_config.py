from core.config import settings


def test_settings_loads():
    assert settings.DB_NAME == "ocr_service"
    assert settings.MAX_RETRIES == 3
    assert settings.WORKER_CONCURRENCY == 3


def test_settings_has_mongo_url():
    assert settings.MONGO_URL.startswith("mongodb://")
