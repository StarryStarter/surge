import pytest
from pydantic import ValidationError

from app.config import Settings


def test_defaults_when_env_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.app_name == "surge"


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    assert Settings(_env_file=None).app_env == "test"


def test_invalid_environment_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging-ish")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)