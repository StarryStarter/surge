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
    redis_url: SecretStr
    # Upper bound on concurrent DB queries per API process; tuned in Phase 4.
    db_pool_max_size: int = Field(default=10, ge=1)
    redis_pool_max_size: int = Field(default=50, ge=1)
    outbox_poll_interval_seconds: float = Field(default=0.5, gt=0)
    outbox_batch_size: int = Field(default=50, ge=1)
    outbox_max_attempts: int = Field(default=8, ge=1)
    hold_ttl_seconds: int = Field(default=900, ge=1)
    hold_expiry_interval_seconds: float = Field(default=5.0, gt=0)
    hold_expiry_batch_size: int = Field(default=100, ge=1)
    reconcile_enabled: bool = True
    reconcile_interval_seconds: float = Field(default=30.0, gt=0)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # Only the test suite reads this — a separate database so tests never
    # touch dev data. Optional at the type level; tests fail clearly if unset.
    test_database_url: SecretStr | None = None
    test_redis_url: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()