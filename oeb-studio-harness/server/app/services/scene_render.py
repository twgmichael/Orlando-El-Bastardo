from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.job import Job

SCENE_RENDER_JOB_TYPE = "scene.render"


def slug_scene_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "scene"


def scene_render_review_url(job_id: str) -> str:
    return f"/review/scene-renders/{job_id}"


def scene_render_trace_url(job_id: str) -> str:
    return f"/api/v1/debug/jobs/{job_id}/trace"


def normalize_scene_script_path(script_path: str) -> str:
    raw = script_path.strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=422, detail="script_path is required")
    raw_parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise HTTPException(status_code=422, detail="script_path must not contain path traversal")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise HTTPException(status_code=422, detail="script_path must be repo-relative")
    if path.suffix.lower() != ".py":
        raise HTTPException(status_code=422, detail="script_path must point to a Python scene script")
    return path.as_posix()


async def create_scene_render_job(
    db: AsyncSession,
    *,
    scene_name: str,
    script_path: str,
    quality: str = "preview",
    width: int | None = None,
    height: int | None = None,
    preferred_worker_id: str | None = None,
    priority: int = 10,
    require_gpu_cycles: bool = False,
    mode: str | None = None,
    expected_frames: int | None = None,
    actor_id: str = "admin",
) -> Job:
    normalized_script_path = normalize_scene_script_path(script_path)
    scene_slug = slug_scene_name(scene_name)
    render_mode = mode or "preview"
    required_capabilities = ["blender.final_render" if quality == "final" else "blender.preview_render"]
    if require_gpu_cycles:
        required_capabilities.append("gpu.cycles_render")

    output_path = (
        "{output_root}/oeb-studio-harness/scene-renders/"
        f"{{job_id}}/{scene_slug}_{quality}.mp4"
    )
    frames_dir = (
        "{output_root}/oeb-studio-harness/scene-renders/"
        f"{{job_id}}/{scene_slug}_{quality}_frames"
    )
    script_args = [
        "--mode",
        render_mode,
    ]
    if width is not None:
        script_args.extend(["--width", str(width)])
    if height is not None:
        script_args.extend(["--height", str(height)])
    script_args.extend(["--output", output_path])

    payload = {
        "job_type": SCENE_RENDER_JOB_TYPE,
        "scene_name": scene_name,
        "scene_slug": scene_slug,
        "script_path": normalized_script_path,
        "script_file": f"{{workspace_root}}/{normalized_script_path}",
        "cwd": "{workspace_root}",
        "factory_startup": True,
        "quality": quality,
        "mode": render_mode,
        "output_path": output_path,
        "frames_dir": frames_dir,
        "artifact_paths": [output_path],
        "artifact_type": "scene.final_render" if quality == "final" else "scene.preview_render",
        "script_args": script_args,
        "require_gpu_cycles": require_gpu_cycles,
    }
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    if expected_frames is not None:
        payload["expected_frames"] = expected_frames

    job = Job(
        title=f"Scene render {scene_name}",
        description=f"Render scene {scene_name} from {normalized_script_path}",
        required_capabilities=required_capabilities,
        policy="wait_for_preferred_worker" if preferred_worker_id else "run_anywhere",
        preferred_worker_id=preferred_worker_id,
        priority=priority,
        payload=payload,
        is_idempotent=False,
    )
    db.add(job)
    await db.flush()
    db.add(AuditEvent(
        event_type="job.scene_render.created",
        actor_type="user",
        actor_id=actor_id,
        resource_type="job",
        resource_id=str(job.id),
        details={
            "scene_name": scene_name,
            "script_path": normalized_script_path,
            "quality": quality,
            "require_gpu_cycles": require_gpu_cycles,
        },
    ))
    return job
