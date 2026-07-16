import pytest
from pydantic import ValidationError

from app.config import Settings


def settings_kwargs(**overrides):
    values = {
        "OEB_ENVIRONMENT": "local",
        "DATABASE_URL": "postgresql+asyncpg://harness:pw@postgres:5432/harness",
        "API_ADMIN_TOKEN": "local-admin-token",
        "WORKER_ENROLLMENT_TOKEN": "local-worker-enrollment-token",
        "APP_SIGNING_SECRET": "local-signing-secret-change-me",
        "OEB_STUDIO_CHAT_OLLAMA_URL": "http://host.docker.internal:11434",
    }
    values.update(overrides)
    return values


def test_local_allows_local_docker_ollama_url_and_placeholder_secrets():
    settings = Settings(**settings_kwargs())

    assert settings.environment == "local"
    assert settings.studio_chat_ollama_url == "http://host.docker.internal:11434"


def test_staging_rejects_local_docker_ollama_url():
    with pytest.raises(ValidationError, match="local-only host"):
        Settings(**settings_kwargs(
            OEB_ENVIRONMENT="staging-docker-pi",
            API_ADMIN_TOKEN="staging-admin-token",
            WORKER_ENROLLMENT_TOKEN="staging-worker-token",
            **{"APP_SIGNING_SECRET": "staging-signing-value"},
        ))


def test_staging_accepts_network_reachable_ollama_url():
    settings = Settings(**settings_kwargs(
        OEB_ENVIRONMENT="staging-docker-pi",
        API_ADMIN_TOKEN="staging-admin-token",
        WORKER_ENROLLMENT_TOKEN="staging-worker-token",
        **{"APP_SIGNING_SECRET": "staging-signing-value"},
        OEB_STUDIO_CHAT_OLLAMA_URL="http://llm-host.local:11434",
    ))

    assert settings.environment == "staging-docker-pi"
    assert settings.studio_chat_ollama_url == "http://llm-host.local:11434"


def test_staging_rejects_local_placeholder_secrets():
    with pytest.raises(ValidationError, match="local placeholder"):
        Settings(**settings_kwargs(
            OEB_ENVIRONMENT="staging-docker-pi",
            OEB_STUDIO_CHAT_OLLAMA_URL="http://llm-host.local:11434",
        ))
