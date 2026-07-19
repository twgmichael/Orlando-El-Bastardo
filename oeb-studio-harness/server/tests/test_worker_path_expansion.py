import pytest

from agent.adapters.blender import BlenderCLIAdapter
from agent.config import BlenderAdapterConfig


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

    def fake_run(cmd, cwd=None):
        commands.append((cmd, cwd))
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

    def fake_run(cmd, cwd=None):
        commands.append((cmd, cwd))
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
        },
    })

    assert result.success
    assert [path.name for path in result.artifacts] == ["jb100-pirate-escape_final.mp4"]
    assert "--factory-startup" in commands[0][0]
    assert commands[0][1] == str(workspace)
    assert result.artifact_type == "scene.final_render"
    assert result.output_summary["job_type"] == "scene.render"
    assert result.output_summary["scene_name"] == "JB100-pirate-escape"
    assert result.output_summary["frame_count"] == 3
