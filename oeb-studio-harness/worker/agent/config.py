from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import yaml


class OllamaAdapterConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    default_model: str = "qwen2.5-coder:14b"
    timeout_seconds: int = 300


class BlenderAdapterConfig(BaseModel):
    executable: str = "blender"
    max_concurrent: int = 1
    timeout_seconds: int = 3600


class AdapterConfigs(BaseModel):
    ollama: OllamaAdapterConfig = OllamaAdapterConfig()
    blender: BlenderAdapterConfig = BlenderAdapterConfig()


class WorkerConfig(BaseModel):
    worker_id: str
    platform: str
    agent_version: str = "0.1.0"
    capabilities: list[str]
    resources: dict = {}
    adapters: AdapterConfigs = AdapterConfigs()

    # Connectivity — can be overridden from env after loading YAML
    harness_url: str = ""
    enrollment_token: str = ""
    token_file: str = "~/.oeb-harness-worker-token"

    # Tuning
    poll_interval_seconds: int = 5
    heartbeat_interval_seconds: int = 20
    artifact_store_root: str = "/srv/oeb-studio-harness/artifacts"
    output_root: str = ""  # base path for render/file output; substituted into {output_root} in job script_args


def load_config(config_path: str) -> WorkerConfig:
    path = Path(config_path)
    with path.open() as f:
        data = yaml.safe_load(f)
    return WorkerConfig(**data)
