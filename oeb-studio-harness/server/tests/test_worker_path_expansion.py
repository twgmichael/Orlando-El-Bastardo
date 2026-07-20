import pytest
import sys
from types import ModuleType
from types import SimpleNamespace

from agent.adapters.blender import BlenderCLIAdapter
from agent.config import BlenderAdapterConfig

client_stub = ModuleType("agent.client")
client_stub.HarnessClient = object
sys.modules.setdefault("agent.client", client_stub)

from agent.job_runner import JobRunner


def test_blender_adapter_expands_output_workspace_and_job_placeholders():
    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender"),
        output_root="/render-output",
        workspace_root="/workspace",
    )

    assert adapter._resolve_path("{output_root}/jobs/{job_id}/preview.png", "job-123") == (
        "/render-output/jobs/job-123/preview.png"
    )
    assert adapter._resolve_path("{workspace_root}/tools/build.py", "job-123") == (
        "/workspace/tools/build.py"
    )


def test_blender_adapter_rejects_path_traversal_after_expansion():
    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender"),
        output_root="/render-output",
        workspace_root="/workspace",
    )

    with pytest.raises(ValueError):
        adapter._resolve_runtime_path("{output_root}/../escape.png", "output_path")


def test_blender_adapter_routes_asset_review_render(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools_dir = workspace / "tools"
    tools_dir.mkdir()
    (tools_dir / "render_asset_review.py").write_text("# test script\n", encoding="utf-8")
    output_root = tmp_path / "output"
    commands = []

    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender"),
        output_root=str(output_root),
        workspace_root=str(workspace),
    )

    def fake_run(cmd, cwd=None, timeout_seconds=None):
        commands.append((cmd, cwd, timeout_seconds))
        out_dir = output_root / "oeb-studio-harness" / "review-renders" / "job-123"
        out_dir.mkdir(parents=True, exist_ok=True)
        for view in ("front", "action"):
            (out_dir / f"ventradi_cruiser_{view}.png").write_bytes(b"png")
        return "ok", 0

    monkeypatch.setattr(adapter, "_run", fake_run)

    result = adapter.execute({
        "id": "job-123",
        "required_capabilities": ["blender.preview_render"],
        "payload": {
            "job_type": "asset.review_render",
            "asset_path": "assets/ships/ventradi_cruiser.glb",
            "asset_id": "ventradi_cruiser",
            "views": ["front", "action"],
            "quality": "preview",
        },
    })

    assert result.success
    assert [path.name for path in result.artifacts] == [
        "ventradi_cruiser_front.png",
        "ventradi_cruiser_action.png",
    ]
    assert "--factory-startup" in commands[0][0]
    assert commands[0][1] == str(workspace)
    assert result.artifact_type == "asset.review_render"
    assert result.output_summary["artifact_views"] == {
        "ventradi_cruiser_front.png": "front",
        "ventradi_cruiser_action.png": "action",
    }


def test_blender_adapter_routes_scene_render(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools_dir = workspace / "tools"
    tools_dir.mkdir()
    (tools_dir / "scene.py").write_text("# test script\n", encoding="utf-8")
    output_root = tmp_path / "output"
    commands = []

    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender"),
        output_root=str(output_root),
        workspace_root=str(workspace),
    )

    def fake_run(cmd, cwd=None, timeout_seconds=None):
        commands.append((cmd, cwd, timeout_seconds))
        out_dir = output_root / "oeb-studio-harness" / "scene-renders" / "job-456"
        frames_dir = out_dir / "jb100-pirate-escape_final_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "jb100-pirate-escape_final.mp4").write_bytes(b"mp4")
        for frame in range(1, 4):
            (frames_dir / f"frame_{frame:04d}.png").write_bytes(b"png")
        return "ok", 0

    monkeypatch.setattr(adapter, "_run", fake_run)

    result = adapter.execute({
        "id": "job-456",
        "required_capabilities": ["blender.final_render"],
        "payload": {
            "job_type": "scene.render",
            "scene_name": "JB100-pirate-escape",
            "script_path": "tools/scene.py",
            "script_file": "{workspace_root}/tools/scene.py",
            "cwd": "{workspace_root}",
            "factory_startup": True,
            "quality": "final",
            "mode": "preview",
            "output_path": "{output_root}/oeb-studio-harness/scene-renders/{job_id}/jb100-pirate-escape_final.mp4",
            "frames_dir": "{output_root}/oeb-studio-harness/scene-renders/{job_id}/jb100-pirate-escape_final_frames",
            "artifact_paths": [
                "{output_root}/oeb-studio-harness/scene-renders/{job_id}/jb100-pirate-escape_final.mp4",
            ],
            "artifact_type": "scene.final_render",
            "expected_frames": 3,
            "blender_timeout_seconds": 172800,
        },
    })

    assert result.success
    assert [path.name for path in result.artifacts] == ["jb100-pirate-escape_final.mp4"]
    assert "--factory-startup" in commands[0][0]
    assert commands[0][1] == str(workspace)
    assert commands[0][2] == 172800
    assert result.artifact_type == "scene.final_render"
    assert result.output_summary["job_type"] == "scene.render"
    assert result.output_summary["scene_name"] == "JB100-pirate-escape"
    assert result.output_summary["frame_count"] == 3
    assert result.output_summary["timing"]["frames"] == 3
    assert result.output_summary["progress"]["phase"] == "complete"
    assert result.output_summary["blender_timeout_seconds"] == 172800
    assert result.output_summary["blender_timeout_source"] == "payload"


def test_blender_adapter_falls_back_to_config_timeout_when_payload_omits_timeout(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools_dir = workspace / "tools"
    tools_dir.mkdir()
    (tools_dir / "scene.py").write_text("# test script\n", encoding="utf-8")
    output_root = tmp_path / "output"
    commands = []

    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender", timeout_seconds=321),
        output_root=str(output_root),
        workspace_root=str(workspace),
    )

    def fake_run(cmd, cwd=None, timeout_seconds=None):
        commands.append((cmd, cwd, timeout_seconds))
        out_dir = output_root / "oeb-studio-harness" / "scene-renders" / "job-457"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "scene_preview.mp4").write_bytes(b"mp4")
        return "ok", 0

    monkeypatch.setattr(adapter, "_run", fake_run)

    result = adapter.execute({
        "id": "job-457",
        "required_capabilities": ["blender.preview_render"],
        "payload": {
            "job_type": "scene.render",
            "scene_name": "No Timeout Payload",
            "script_path": "tools/scene.py",
            "script_file": "{workspace_root}/tools/scene.py",
            "cwd": "{workspace_root}",
            "quality": "preview",
            "output_path": "{output_root}/oeb-studio-harness/scene-renders/{job_id}/scene_preview.mp4",
            "artifact_paths": [
                "{output_root}/oeb-studio-harness/scene-renders/{job_id}/scene_preview.mp4",
            ],
            "artifact_type": "scene.preview_render",
        },
    })

    assert result.success
    assert commands[0][2] == 321
    assert result.output_summary["blender_timeout_seconds"] == 321
    assert result.output_summary["blender_timeout_source"] == "adapter_default"


def test_blender_adapter_reports_scene_render_failure_diagnostics(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools_dir = workspace / "tools"
    tools_dir.mkdir()
    (tools_dir / "scene.py").write_text("# test script\n", encoding="utf-8")
    output_root = tmp_path / "output"

    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender", timeout_seconds=321),
        output_root=str(output_root),
        workspace_root=str(workspace),
    )

    def fake_run(cmd, cwd=None, timeout_seconds=None):
        frames_dir = output_root / "oeb-studio-harness" / "scene-renders" / "job-458" / "scene_preview_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for frame in range(1, 3):
            (frames_dir / f"frame_{frame:04d}.png").write_bytes(b"png")
        return "\n".join(f"log line {idx}" for idx in range(100)), 2

    monkeypatch.setattr(adapter, "_run", fake_run)

    result = adapter.execute({
        "id": "job-458",
        "required_capabilities": ["blender.preview_render"],
        "payload": {
            "job_type": "scene.render",
            "scene_name": "JB100-pirate-escape",
            "script_path": "tools/scene.py",
            "script_file": "{workspace_root}/tools/scene.py",
            "cwd": "{workspace_root}",
            "quality": "preview",
            "output_path": "{output_root}/oeb-studio-harness/scene-renders/{job_id}/scene_preview.mp4",
            "frames_dir": "{output_root}/oeb-studio-harness/scene-renders/{job_id}/scene_preview_frames",
            "artifact_type": "scene.preview_render",
            "expected_frames": 276,
        },
    })

    assert not result.success
    assert result.error == "Blender exited 2"
    assert result.output_summary["job_type"] == "scene.render"
    assert result.output_summary["exit_code"] == 2
    assert result.output_summary["frames_rendered"] == 2
    assert result.output_summary["latest_frame_path"].endswith("frame_0002.png")
    assert result.output_summary["blender_timeout_seconds"] == 321
    assert result.output_summary["blender_timeout_source"] == "adapter_default"
    assert "log line 20" in result.output_summary["log_tail"]
    assert "log line 19" not in result.output_summary["log_tail"]


def test_job_runner_reports_scene_render_progress(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for frame in range(1, 7):
        (frames_dir / f"frame_{frame:04d}.png").write_bytes(b"png")

    runner = JobRunner(
        client=None,
        heartbeat=None,
        registry=None,
        config=SimpleNamespace(
            output_root=str(tmp_path),
            workspace_root=str(tmp_path),
        ),
    )

    progress = runner._scene_render_progress({
        "id": "job-789",
        "created_at": "2026-07-19T20:00:00+00:00",
        "payload": {
            "job_type": "scene.render",
            "quality": "final",
            "frames_dir": str(frames_dir),
            "output_path": str(tmp_path / "out.mp4"),
            "expected_frames": 24,
        },
    })

    assert progress["phase"] == "rendering_frames"
    assert progress["frames_rendered"] == 6
    assert progress["total_frames"] == 24
    assert progress["percent"] == 25
    assert progress["estimate_source"] == "current_render"
    assert progress["latest_frame_path"].endswith("frame_0006.png")


def test_job_runner_reports_final_render_with_no_early_frames(tmp_path):
    runner = JobRunner(
        client=None,
        heartbeat=None,
        registry=None,
        config=SimpleNamespace(
            output_root=str(tmp_path),
            workspace_root=str(tmp_path),
        ),
    )

    progress = runner._scene_render_progress({
        "id": "job-790",
        "created_at": "2020-01-01T00:00:00+00:00",
        "payload": {
            "job_type": "scene.render",
            "quality": "final",
            "frames_dir": str(tmp_path / "missing_frames"),
            "output_path": str(tmp_path / "out.mp4"),
            "initial_progress": {
                "estimate_source": "insufficient_data",
                "message": "No prior preview timing available; ETA will start after final frames land.",
            },
        },
    })

    assert progress["phase"] == "starting"
    assert progress["frames_rendered"] == 0
    assert progress["total_frames"] is None
    assert progress["percent"] is None
    assert progress["eta_seconds"] is None
    assert progress["estimate_source"] == "insufficient_data"
    assert progress["message"].startswith("No prior preview timing")
    assert progress["warning"].startswith("No rendered frames yet")
