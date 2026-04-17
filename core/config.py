from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URL: str
    DB_NAME: str = "ocr_service"
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 60
    MAX_RETRIES: int = 3
    WORKER_CONCURRENCY: int = 3
    POLL_INTERVAL_SECONDS: int = 60
    MAX_PROCESSING_MINUTES: int = 10
    MAX_FILE_SIZE_MB: int = 20
    STORAGE_PATH: str = "./storage/uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
