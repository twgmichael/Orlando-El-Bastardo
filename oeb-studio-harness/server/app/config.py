from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_ONLY_HOSTS = ("host.docker.internal", "127.0.0.1", "localhost")
VALID_ENVIRONMENTS = {"local", "staging-docker-pi", "production"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="local", alias="OEB_ENVIRONMENT")

    database_url: str = Field(alias="DATABASE_URL")
    admin_token: str = Field(alias="API_ADMIN_TOKEN")
    worker_enrollment_token: str = Field(alias="WORKER_ENROLLMENT_TOKEN")
    signing_secret: str = Field(alias="APP_SIGNING_SECRET")

    worker_heartbeat_seconds: int = Field(default=20, alias="WORKER_HEARTBEAT_SECONDS")
    worker_timeout_seconds: int = Field(default=75, alias="WORKER_TIMEOUT_SECONDS")
    job_lease_seconds: int = Field(default=120, alias="JOB_LEASE_SECONDS")

    artifacts_root: str = Field(default="/srv/oeb-studio-harness/artifacts", alias="ARTIFACTS_ROOT")
    artifact_public_base_url: str = Field(default="", alias="ARTIFACT_PUBLIC_BASE_URL")
    artifact_worker_path_prefix: str = Field(default="", alias="ARTIFACT_WORKER_PATH_PREFIX")
    artifact_server_path_prefix: str = Field(default="", alias="ARTIFACT_SERVER_PATH_PREFIX")
    asset_root: str = Field(default="assets", alias="OEB_ASSET_ROOT")
    oeb_config_path: str = Field(default="../../oeb.config.json", alias="OEB_CONFIG_PATH")
    studio_chat_harness_url: str = Field(default="", alias="OEB_STUDIO_CHAT_HARNESS_URL")
    studio_chat_admin_token: str = Field(default="", alias="OEB_STUDIO_CHAT_ADMIN_TOKEN")
    studio_chat_ollama_url: str = Field(default="", alias="OEB_STUDIO_CHAT_OLLAMA_URL")
    studio_chat_model: str = Field(default="oeb-qwen2.5-3b", alias="OEB_STUDIO_CHAT_MODEL")
    timezone: str = "America/New_York"

    # Derived at validation time; not set from env
    database_url_sync: str = ""

    @model_validator(mode="after")
    def validate_and_derive(self) -> "Settings":
        if self.environment not in VALID_ENVIRONMENTS:
            allowed = ", ".join(sorted(VALID_ENVIRONMENTS))
            raise ValueError(f"OEB_ENVIRONMENT must be one of: {allowed}")
        if not self.studio_chat_ollama_url:
            raise ValueError("OEB_STUDIO_CHAT_OLLAMA_URL is required")
        if self.environment != "local":
            lowered = self.studio_chat_ollama_url.lower()
            if any(host in lowered for host in LOCAL_ONLY_HOSTS):
                raise ValueError(
                    "OEB_STUDIO_CHAT_OLLAMA_URL uses a local-only host outside "
                    "the local environment"
                )
            forbidden_secret_values = {
                self.admin_token: "API_ADMIN_TOKEN",
                self.worker_enrollment_token: "WORKER_ENROLLMENT_TOKEN",
                self.signing_secret: "APP_SIGNING_SECRET",
            }
            for value, label in forbidden_secret_values.items():
                if value.startswith("local-") or value.endswith("change-me"):
                    raise ValueError(f"{label} contains a local placeholder outside local")
        if not self.database_url_sync:
            self.database_url_sync = self.database_url.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
