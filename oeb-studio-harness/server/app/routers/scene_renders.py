import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.schemas.scene_render import SceneRenderRequest, SceneRenderResponse
from app.services.scene_render import (
    create_scene_render_job,
    scene_render_review_url,
    scene_render_trace_url,
)

router = APIRouter(prefix="/scene-renders", tags=["scene-renders"])


@router.post("", response_model=SceneRenderResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_scene_render(
    body: SceneRenderRequest,
    db: AsyncSession = Depends(get_db),
):
    job = await create_scene_render_job(
        db,
        scene_name=body.scene_name,
        script_path=body.script_path,
        quality=body.quality,
        width=body.width,
        height=body.height,
        preferred_worker_id=body.preferred_worker_id,
        priority=body.priority,
        require_gpu_cycles=body.require_gpu_cycles,
        mode=body.mode,
        expected_frames=body.expected_frames,
        blender_timeout_seconds=body.blender_timeout_seconds,
        actor_id="admin",
    )
    await db.commit()
    await db.refresh(job)
    job_id = uuid.UUID(str(job.id))
    return SceneRenderResponse(
        job_id=job_id,
        status=job.status,
        review_url=scene_render_review_url(str(job.id)),
        trace_url=scene_render_trace_url(str(job.id)),
        scene_name=body.scene_name,
        script_path=job.payload["script_path"],
        quality=body.quality,
        created_at=job.created_at,
    )
