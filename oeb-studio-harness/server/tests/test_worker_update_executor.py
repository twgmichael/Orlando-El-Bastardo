import sys
from types import ModuleType
from pathlib import Path

import pytest

client_stub = ModuleType("agent.client")
client_stub.HarnessClient = object
sys.modules.setdefault("agent.client", client_stub)

from agent.config import WorkerConfig
from agent.heartbeat import HeartbeatLoop
from agent.updater import WorkerUpdateExecutor


def test_worker_update_executor_runs_configured_commands_and_probes(tmp_path, monkeypatch):
    marker = tmp_path / "updated.txt"
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="test",
        capabilities=["llm.generate"],
        workspace_root=str(tmp_path),
        update_commands=[
            [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ok')"]
        ],
    )
    executor = WorkerUpdateExecutor(cfg)
    monkeypatch.setattr("agent.updater.current_git_sha", lambda _workspace: "abc1234")

    result = executor._apply_sync(target_git_sha=None)

    assert result.success
    assert marker.read_text() == "ok"
    assert result.probes["workspace_root"]["ok"]
    assert result.probes["capabilities"]["ok"]


def test_worker_update_executor_fails_when_target_git_sha_does_not_match(tmp_path, monkeypatch):
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="test",
        capabilities=["llm.generate"],
        workspace_root=str(tmp_path),
    )
    executor = WorkerUpdateExecutor(cfg)
    monkeypatch.setattr("agent.updater.current_git_sha", lambda _workspace: "abc1234")

    result = executor._apply_sync(target_git_sha="def5678")

    assert not result.success
    assert "git_sha" in result.error
    assert not result.probes["git_sha"]["ok"]


def test_worker_update_commands_support_target_sha_placeholder(tmp_path, monkeypatch):
    marker = tmp_path / "target.txt"
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="test",
        capabilities=["llm.generate"],
        workspace_root=str(tmp_path),
        update_commands=[
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    f"from pathlib import Path; Path({str(marker)!r}).write_text(sys.argv[1])"
                ),
                "{target_git_sha}",
            ]
        ],
    )
    executor = WorkerUpdateExecutor(cfg)
    monkeypatch.setattr("agent.updater.current_git_sha", lambda _workspace: "abc1234")

    result = executor._apply_sync(target_git_sha="abc1234")

    assert result.success
    assert marker.read_text() == "abc1234"


def test_worker_update_executor_requires_blender_for_blender_capability(tmp_path):
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="test",
        capabilities=["blender.preview_render"],
        workspace_root=str(tmp_path),
    )
    cfg.adapters.blender.executable = str(tmp_path / "missing-blender")
    executor = WorkerUpdateExecutor(cfg)

    result = executor._apply_sync(target_git_sha=None)

    assert not result.success
    assert "blender" in result.error
    assert not result.probes["blender"]["ok"]


@pytest.mark.anyio
async def test_heartbeat_dispatches_ready_update_instruction_once_per_response():
    calls = []
    heartbeat = HeartbeatLoop(
        client=None,
        worker_id="render-test-01",
        on_update_instruction=lambda instruction: calls.append(instruction),
    )

    await heartbeat._dispatch_update_instruction({
        "update_state": "ready_to_update",
        "update_target_git_sha": "abc1234",
    })
    await heartbeat._dispatch_update_instruction({"update_state": "applying"})

    assert calls == [{
        "update_state": "ready_to_update",
        "update_target_git_sha": "abc1234",
    }]
