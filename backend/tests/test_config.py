from backend.app.core.config import get_settings


def test_settings_load_database_urls_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("SYNC_DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("EXPORT_STORAGE_DIR", "var/exports")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://u:p@localhost:5432/db"
    assert settings.sync_database_url == "postgresql+psycopg://u:p@localhost:5432/db"
    assert settings.export_storage_dir == "var/exports"

    get_settings.cache_clear()
