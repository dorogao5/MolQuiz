from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MOLQUIZ_",
        extra="ignore",
    )

    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    app_name: str = "MolQuiz"

    telegram_token: SecretStr = Field(
        validation_alias=AliasChoices("MOLQUIZ_TELEGRAM_TOKEN", "TELEGRAM_TOKEN", "token")
    )
    telegram_webhook_secret: str = "molquiz-webhook-secret"
    telegram_webhook_base_url: str | None = None
    telegram_parse_mode: str = "HTML"
    telegram_reuse_file_ids: bool = True

    database_url: str = "postgresql+asyncpg://molquiz:molquiz@localhost:15432/molquiz"
    redis_url: str = "redis://localhost:16379/0"
    session_ttl_seconds: int = 60 * 60 * 12

    opsin_base_url: str = "http://localhost:18080"
    pubchem_base_url: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    pubchem_batch_size: int = 100

    storage_dir: Path = Path("storage")
    qwen_command: str | None = None

    auto_create_schema: bool = False
    metrics_enabled: bool = True
    request_timeout_seconds: float = 20.0
    review_export_dir: Path = Path("data/review_exports")

    @property
    def webhook_path(self) -> str:
        return f"/telegram/webhook/{self.telegram_webhook_secret}"

    @property
    def webhook_url(self) -> str | None:
        if not self.telegram_webhook_base_url:
            return None
        return f"{self.telegram_webhook_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.review_export_dir.mkdir(parents=True, exist_ok=True)
    return settings
