"""Application settings, read from environment variables prefixed ``KIVI_``."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KIVI_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi"

    secret_key: str = DEV_SECRET
    session_hours: int = Field(8, ge=1, le=72)
    cookie_name: str = "kivi_session"
    cookie_secure: bool = False

    signup_mode: Literal["approval", "open", "closed"] = "approval"
    require_four_eyes: bool = True
    max_failed_logins: int = Field(5, ge=1)
    lockout_minutes: int = Field(15, ge=1)

    # HMAC key for watchlist values; defaults to the secret key. Changing it makes stored lists unmatchable.
    list_key: str | None = None

    # Run the background job worker inside the API process (training, batch scoring, monitor schedules).
    run_worker: bool = True

    # Time zone in which monitor schedules ("daily at 06:00") are read.
    timezone: str = "Asia/Shanghai"

    # Used only by `kivi-ui seed-demo` to create the demonstration accounts.
    demo_password: str | None = None

    @model_validator(mode="after")
    def _known_timezone(self) -> "Settings":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"KIVI_TIMEZONE is not a known time zone: {self.timezone}") from error
        return self

    @model_validator(mode="after")
    def _production_secret(self) -> "Settings":
        if self.env == "production":
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
                raise ValueError("KIVI_SECRET_KEY must be set to at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("KIVI_COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
