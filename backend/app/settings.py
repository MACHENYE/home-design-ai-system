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

    remote_upload_enabled: bool = False
    remote_upload_host: str = ""
    remote_upload_port: int = 22
    remote_upload_user: str = ""
    remote_upload_password: str = ""
    remote_upload_key_path: str = ""
    remote_upload_dir: str = ""
    remote_public_base_url: str = ""
    remote_upload_timeout_s: float = 20.0


settings = Settings()
