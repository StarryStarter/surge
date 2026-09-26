# app/config.py
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (12-factor).

    Invalid values fail at startup, not on the first request that needs them.
    Secrets have NO default so a missing one crashes the boot instead of
    silently falling back to something unsafe.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "surge"
    app_env: Literal["development", "test", "production"] = "development"

    database_url: SecretStr
    # Upper bound on concurrent DB queries per API process; tuned in Phase 4.
    db_pool_max_size: int = Field(default=10, ge=1)

    # Only the test suite reads this — a separate database so tests never
    # touch dev data. Optional at the type level; tests fail clearly if unset.
    test_database_url: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()