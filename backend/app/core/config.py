"""Application settings, loaded from environment variables (and an optional backend/.env file).

Secrets are held as ``SecretStr`` so they never appear in reprs, logs, or tracebacks.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class DatabricksSettings(BaseSettings):
    """Databricks SQL Warehouse connection settings. All values come from ``DATABRICKS_*`` env vars."""

    model_config = SettingsConfigDict(
        env_prefix="DATABRICKS_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_hostname: str | None = None
    http_path: str | None = None
    token: SecretStr | None = None
    catalog: str = "workspace"
    schema_name: str = Field(default="smartstock_retail", validation_alias="DATABRICKS_SCHEMA")

    # Bounded network behaviour for an interactive API. The connector's own defaults are a
    # 900 s socket timeout and up to 30 retries over 900 s, which would stall a request for
    # up to 15 minutes. Each value is within the connector's accepted range.
    socket_timeout_seconds: float = Field(default=30, ge=5, le=300)
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_max_duration_seconds: float = Field(default=60, ge=5, le=600)
    statement_timeout_seconds: int = Field(default=60, ge=10, le=3600)
    # CloudFetch downloads large results from cloud-storage links (a second host, with the
    # connector's own 60 s download timeout). Off: results arrive inline over the bounded connection.
    use_cloud_fetch: bool = False

    @property
    def is_configured(self) -> bool:
        return bool(self.server_hostname and self.http_path and self.token and self.token.get_secret_value())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SMARTSTOCK_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SmartStock AI API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"
    # Where the read-only data API reads from. "databricks" is implemented but UNVERIFIED
    # against a real warehouse; "csv" (the generated synthetic files) is the default.
    data_source: Literal["csv", "databricks"] = "csv"
    data_dir: Path = BACKEND_DIR / "data" / "synthetic"
    # Databricks source only: how often the cached snapshot is refreshed, and how long a request
    # may wait for the very first load before getting a 503 (keep below the frontend's 15 s timeout).
    data_refresh_seconds: float = Field(default=300, ge=30, le=86400)
    data_wait_seconds: float = Field(default=10, ge=0, le=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_databricks_settings() -> DatabricksSettings:
    return DatabricksSettings()
