from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    admin_token: str = Field(alias="API_ADMIN_TOKEN")
    worker_enrollment_token: str = Field(alias="WORKER_ENROLLMENT_TOKEN")
    signing_secret: str = Field(alias="APP_SIGNING_SECRET")

    worker_heartbeat_seconds: int = Field(default=20, alias="WORKER_HEARTBEAT_SECONDS")
    worker_timeout_seconds: int = Field(default=75, alias="WORKER_TIMEOUT_SECONDS")
    job_lease_seconds: int = Field(default=120, alias="JOB_LEASE_SECONDS")

    artifacts_root: str = Field(default="/srv/oeb-studio-harness/artifacts", alias="ARTIFACTS_ROOT")
    asset_root: str = Field(default="assets", alias="OEB_ASSET_ROOT")
    oeb_config_path: str = Field(default="../../oeb.config.json", alias="OEB_CONFIG_PATH")
    timezone: str = "America/New_York"

    # Derived at validation time; not set from env
    database_url_sync: str = ""

    @model_validator(mode="after")
    def derive_sync_url(self) -> "Settings":
        if not self.database_url_sync:
            self.database_url_sync = self.database_url.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
