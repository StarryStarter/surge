import pytest
from pydantic import ValidationError

from app.config import Settings


# _env_file=None keeps a developer's local .env from leaking into the test.
def test_defaults_when_env_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.app_name == "surge"


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")

    assert Settings(_env_file=None).app_env == "test"


def test_invalid_environment_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging-ish")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
