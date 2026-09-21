from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (12-factor).

    Invalid values fail at startup, not on the first request that needs them.
    Secrets added later (DB/Redis URLs, JWT key) must have NO default so a
    missing one crashes the boot instead of silently using an unsafe value.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "surge"
    app_env: Literal["development", "test", "production"] = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
