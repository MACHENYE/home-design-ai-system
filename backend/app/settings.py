from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):  # 集中读取后端运行所需的环境变量和默认配置，包括数据库、模型服务、上传和缓存参数
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nanobanana_api_key: str = ""
    nanobanana_base_url: str = "https://api.nanobananaapi.ai/api/v1/nanobanana"

    public_base_url: str = "http://localhost:8000"
    database_url: str = ""
    uploads_dir: str = "./uploads"
    frontend_dir: str = "../frontend"
    max_upload_mb: int = 12

    redis_url: str = ""
    cache_ttl_s: int = 120
    recommendation_cache_ttl_s: int = 600
    generation_queue_enabled: bool = True
    generation_queue_poll_timeout_s: int = 2

    remote_upload_enabled: bool = False
    remote_upload_host: str = ""
    remote_upload_port: int = 22
    remote_upload_user: str = ""
    remote_upload_password: str = ""
    remote_upload_key_path: str = ""
    remote_upload_dir: str = ""
    remote_public_base_url: str = ""
    remote_upload_timeout_s: float = 20.0

    # 可选的阿里云百炼视觉推荐配置
    vision_recommendation_enabled: bool = False
    bailian_api_key: str = ""
    dashscope_api_key: str = ""
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_vision_model: str = "qwen3-vl-plus"
    bailian_text_model: str = "qwen-plus"
    bailian_timeout_s: float = 35.0

    # 保留旧版 OpenAI 配置名，避免历史 .env 文件加载失败
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    vision_recommendation_model: str = "gpt-4.1-mini"
    vision_recommendation_timeout_s: float = 35.0


settings = Settings()
