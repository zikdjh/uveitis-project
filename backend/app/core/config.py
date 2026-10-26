from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    app_name: str = "Uveitis Auxiliary Diagnosis Backend"
    app_version: str = "0.1.0"
    environment: str = "development"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    data_dir: Path = Path("data")
    database_url: str = ""
    redis_url: str = "redis://127.0.0.1:6380/0"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60
    refresh_rotation_grace_seconds: int = 30
    login_max_attempts: int = 5
    login_window_seconds: int = 15 * 60
    trust_proxy_headers: bool = False
    cookie_secure: bool = False
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_doctor_username: str = ""
    bootstrap_doctor_password: str = ""
    max_upload_bytes: int = 25 * 1024 * 1024
    model_mode: Literal["mock", "remote"] = "mock"
    perception_model: str = "Qwen3.5-4B"
    retrieval_model: str = "BAAI/bge-m3"
    decision_model: str = "Intern-Decision-4B"
    fallback_model: str = "Kev-4B"
    decision_enabled: bool = False
    perception_service_url: str = ""
    retrieval_service_url: str = ""
    decision_service_url: str = ""
    vector_collection_name: str = "uveitis_knowledge"
    vector_dimension: int = 1024
    vector_provider: Literal["memory", "local", "remote"] = "local"
    bge_m3_model_path: Path = Path("models/bge-m3")
    bge_m3_batch_size: int = 8
    bge_m3_max_length: int = 1024
    vector_top_k: int = 5

    @property
    def database_path(self) -> Path:
        return self.data_dir / "uveitis.db"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "zvec"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
