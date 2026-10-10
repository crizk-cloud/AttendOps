"""Application settings, read from environment variables (and an optional .env file).

Every variable is documented in /.env.example and the README.
"""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", description="development | production")
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://attendops:attendops@localhost:5432/attendops"

    # Auth
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Fernet key used to encrypt device passwords at rest.
    device_credentials_key: SecretStr

    # Device communication
    device_connect_timeout: float = 3.0
    device_read_timeout: float = 10.0
    device_max_concurrency: int = 4

    # History sync
    sync_initial_days: int = 30      # how far back the first sync of a device goes
    sync_overlap_minutes: int = 60   # re-read this much before the last sync point (late/clock-skewed records)
    sync_chunk_hours: int = 24       # import and commit in chunks of this size

    app_timezone: str = "Asia/Beirut"
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strength(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @field_validator("device_credentials_key")
    @classmethod
    def _valid_fernet_key(cls, v: SecretStr) -> SecretStr:
        try:
            Fernet(v.get_secret_value().encode())
        except Exception as exc:  # noqa: BLE001 - re-raised as a clear config error
            raise ValueError("DEVICE_CREDENTIALS_KEY must be a Fernet key (see README)") from exc
        return v

    @field_validator("app_timezone")
    @classmethod
    def _valid_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {v!r}") from exc
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
