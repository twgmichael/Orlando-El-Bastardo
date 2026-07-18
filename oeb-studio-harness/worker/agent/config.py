from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
import re
import shlex
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
    artifact_public_base_url: str = ""  # public harness base URL for review links; defaults to harness_url
    output_root: str = ""  # base path for render/file output; substituted into {output_root} in job script_args
    workspace_root: str = "."  # base path for repo-relative job scripts; substituted into {workspace_root}


_ENV_DEFAULT_PATTERN = re.compile(r"\$\{([A-Z0-9_]+):-([^}]+)\}")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def normalize_harness_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    return url


def _parse_env_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    match = _ENV_ASSIGNMENT_PATTERN.match(stripped)
    if not match:
        return None
    key, raw_value = match.groups()
    try:
        parts = shlex.split(raw_value, comments=True, posix=True)
    except ValueError:
        return key, raw_value.strip().strip("'\"")
    return key, parts[0] if parts else ""


def load_local_env(config_path: str) -> None:
    path = Path(config_path)
    candidates = [
        Path.cwd() / ".env.local",
        path.parent / ".env.local",
        Path(__file__).resolve().parents[1] / ".env.local",
    ]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            assignment = _parse_env_assignment(line)
            if not assignment:
                continue
            key, value = assignment
            os.environ.setdefault(key, value)
        return


def _expand_env_defaults(value):
    if isinstance(value, str):
        def repl(match):
            return os.environ.get(match.group(1), match.group(2))
        return os.path.expandvars(_ENV_DEFAULT_PATTERN.sub(repl, value))
    if isinstance(value, dict):
        return {k: _expand_env_defaults(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_defaults(v) for v in value]
    return value


def load_config(config_path: str) -> WorkerConfig:
    load_local_env(config_path)
    path = Path(config_path)
    with path.open() as f:
        data = yaml.safe_load(f)
    data = _expand_env_defaults(data)
    if data.get("harness_url"):
        data["harness_url"] = normalize_harness_url(data["harness_url"])
    workspace_root = data.get("workspace_root")
    if workspace_root:
        workspace_path = Path(workspace_root)
        if not workspace_path.is_absolute():
            data["workspace_root"] = str((path.parent / workspace_path).resolve())
    return WorkerConfig(**data)
