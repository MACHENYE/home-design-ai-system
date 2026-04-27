from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ai_provider: str = "auto"

    nanobanana_api_key: str = ""
    nanobanana_base_url: str = "https://api.nanobananaapi.ai/api/v1/nanobanana"

    public_base_url: str = "http://localhost:8000"
    tasks_db_path: str = "./tasks.db"
    uploads_dir: str = "./uploads"
    frontend_dir: str = "../frontend"
    max_upload_mb: int = 12


settings = Settings()
