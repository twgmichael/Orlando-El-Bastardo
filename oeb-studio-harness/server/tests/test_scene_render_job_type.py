from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import scene_render


def test_scene_render_script_path_must_be_repo_relative():
    assert scene_render.normalize_scene_script_path("tools/JB100-pirate-escape.py") == (
        "tools/JB100-pirate-escape.py"
    )

    for bad_path in (
        "/tmp/scene.py",
        "tools/../secrets.py",
        "./tools/scene.py",
        "tools/scene.blend",
    ):
        with pytest.raises(HTTPException):
            scene_render.normalize_scene_script_path(bad_path)


@pytest.mark.anyio
async def test_scene_render_final_job_prefers_requested_worker_and_gpu():
    added = []

    async def flush():
        return None

    db = SimpleNamespace(
        add=lambda value: added.append(value),
        flush=flush,
    )

    job = await scene_render.create_scene_render_job(
        db,
        scene_name="JB100-pirate-escape",
        script_path="tools/JB100-pirate-escape.py",
        quality="final",
        width=1920,
        height=1080,
        preferred_worker_id="render-pc-01",
        require_gpu_cycles=True,
        expected_frames=360,
    )

    assert job.title == "Scene render JB100-pirate-escape"
    assert job.required_capabilities == ["blender.final_render", "gpu.cycles_render"]
    assert job.policy == "wait_for_preferred_worker"
    assert job.preferred_worker_id == "render-pc-01"
    assert job.payload["job_type"] == "scene.render"
    assert job.payload["script_file"] == "{workspace_root}/tools/JB100-pirate-escape.py"
    assert job.payload["output_path"] == (
        "{output_root}/oeb-studio-harness/scene-renders/{job_id}/jb100-pirate-escape_final.mp4"
    )
    assert job.payload["artifact_paths"] == [job.payload["output_path"]]
    assert job.payload["artifact_type"] == "scene.final_render"
    assert job.payload["script_args"] == [
        "--mode",
        "preview",
        "--width",
        "1920",
        "--height",
        "1080",
        "--output",
        job.payload["output_path"],
    ]
    assert job.payload["expected_frames"] == 360
    assert job.payload["initial_progress"]["estimate_source"] == "insufficient_data"
    assert job.payload["initial_progress"]["message"].startswith("No prior preview timing")
    assert not job.is_idempotent


@pytest.mark.anyio
async def test_scene_render_preview_runs_anywhere():
    async def flush():
        return None

    db = SimpleNamespace(
        add=lambda value: None,
        flush=flush,
    )

    job = await scene_render.create_scene_render_job(
        db,
        scene_name="Blocking Pass",
        script_path="tools/blocking_pass.py",
        quality="preview",
        mode="blocking",
    )

    assert job.required_capabilities == ["blender.preview_render"]
    assert job.policy == "run_anywhere"
    assert job.preferred_worker_id is None
    assert job.payload["artifact_type"] == "scene.preview_render"
    assert job.payload["mode"] == "blocking"


@pytest.mark.anyio
async def test_scene_render_draft_uses_preview_worker_and_blocking_mode():
    async def flush():
        return None

    db = SimpleNamespace(
        add=lambda value: None,
        flush=flush,
    )

    job = await scene_render.create_scene_render_job(
        db,
        scene_name="Fast Blocking Pass",
        script_path="tools/blocking_pass.py",
        quality="draft",
        expected_frames=120,
    )

    assert job.required_capabilities == ["blender.preview_render"]
    assert job.payload["mode"] == "blocking"
    assert job.payload["artifact_type"] == "scene.draft_render"
    assert job.payload["initial_progress"] == {
        "phase": "queued",
        "quality": "draft",
        "frames_rendered": 0,
        "total_frames": 120,
        "percent": 0,
        "eta_seconds": None,
        "estimate_source": "not_needed",
    }
