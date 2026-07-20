from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.job import Job, JobAttempt

SCENE_RENDER_JOB_TYPE = "scene.render"
SCENE_RENDER_TIMEOUT_DEFAULTS = {
    "draft": 1800,
    "preview": 7200,
    "final": 86400,
}


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


async def latest_preview_timing(
    db: AsyncSession,
    *,
    scene_name: str,
    script_path: str,
) -> dict | None:
    result = await db.execute(
        select(JobAttempt)
        .join(Job, JobAttempt.job_id == Job.id)
        .where(
            Job.status == "completed",
            Job.payload["job_type"].as_string() == SCENE_RENDER_JOB_TYPE,
            Job.payload["quality"].as_string() == "preview",
            Job.payload["script_path"].as_string() == script_path,
        )
        .order_by(Job.updated_at.desc())
        .limit(10)
    )
    for attempt in result.scalars().all():
        summary = attempt.output_summary if isinstance(attempt.output_summary, dict) else {}
        if summary.get("scene_name") not in {scene_name, None}:
            continue
        timing = summary.get("timing") if isinstance(summary.get("timing"), dict) else {}
        seconds_per_frame = timing.get("seconds_per_frame") or summary.get("seconds_per_frame")
        if seconds_per_frame:
            return {
                "seconds_per_frame": float(seconds_per_frame),
                "source_job_id": str(attempt.job_id),
                "source_attempt_id": str(attempt.id),
            }
    return None


async def initial_scene_progress(
    db: AsyncSession,
    *,
    scene_name: str,
    script_path: str,
    quality: str,
    expected_frames: int | None,
) -> dict:
    progress = {
        "phase": "queued",
        "quality": quality,
        "frames_rendered": 0,
        "total_frames": expected_frames,
        "percent": 0 if expected_frames else None,
        "eta_seconds": None,
        "estimate_source": "not_needed" if quality == "draft" else "insufficient_data",
    }
    if quality != "final":
        return progress

    if not expected_frames:
        progress["message"] = (
            "Final render queued without an expected frame count; progress will report frames, "
            "but percent and ETA will remain unavailable until timing can be inferred."
        )
        return progress

    if not hasattr(db, "execute"):
        progress["message"] = "No prior preview timing available; ETA will start after final frames land."
        return progress

    timing = await latest_preview_timing(db, scene_name=scene_name, script_path=script_path)
    if not timing:
        progress["message"] = "No prior preview timing available; ETA will start after final frames land."
        return progress

    progress.update({
        "eta_seconds": round(expected_frames * timing["seconds_per_frame"]),
        "seconds_per_frame": timing["seconds_per_frame"],
        "estimate_source": "previous_preview",
        "estimate_source_job_id": timing["source_job_id"],
    })
    return progress


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
    blender_timeout_seconds: int | None = None,
    actor_id: str = "admin",
) -> Job:
    normalized_script_path = normalize_scene_script_path(script_path)
    scene_slug = slug_scene_name(scene_name)
    render_mode = mode or ("blocking" if quality == "draft" else "preview")
    effective_timeout_seconds = blender_timeout_seconds or SCENE_RENDER_TIMEOUT_DEFAULTS[quality]
    required_capabilities = ["blender.final_render" if quality == "final" else "blender.preview_render"]
    if require_gpu_cycles:
        required_capabilities.append("gpu.cycles_render")
    initial_progress = await initial_scene_progress(
        db,
        scene_name=scene_name,
        script_path=normalized_script_path,
        quality=quality,
        expected_frames=expected_frames,
    )

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
        "artifact_type": "scene.final_render" if quality == "final" else f"scene.{quality}_render",
        "script_args": script_args,
        "require_gpu_cycles": require_gpu_cycles,
        "initial_progress": initial_progress,
        "progress_frame_interval": 24,
        "blender_timeout_seconds": effective_timeout_seconds,
        "blender_timeout_source": "request" if blender_timeout_seconds else "quality_default",
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
            "blender_timeout_seconds": effective_timeout_seconds,
            "blender_timeout_source": payload["blender_timeout_source"],
        },
    ))
    return job
