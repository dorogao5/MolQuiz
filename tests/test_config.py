from molquiz.config import Settings


def test_settings_default_to_localhost_service_urls(monkeypatch) -> None:
    monkeypatch.setenv("MOLQUIZ_TELEGRAM_TOKEN", "test-token")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://molquiz:molquiz@localhost:15432/molquiz"
    assert settings.redis_url == "redis://localhost:16379/0"
    assert settings.opsin_base_url == "http://localhost:18080"
