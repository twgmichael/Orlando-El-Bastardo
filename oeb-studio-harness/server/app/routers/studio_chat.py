import asyncio
import urllib.error
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.routers.conversations import _build_job_payload, create_conversation_job
from app.schemas.conversation import ConversationJobRequest, ConversationJobResponse
from app.schemas.studio_chat import (
    StudioChatBuildJobRequest,
    StudioChatBuildJobResponse,
    StudioChatBuildJobStatusResponse,
    StudioChatModelList,
    StudioChatOllamaRequest,
    StudioChatOllamaResponse,
    StudioChatPrimitiveResolveRequest,
    StudioChatPrimitiveResolveResponse,
    StudioChatReviewArtifact,
    StudioChatPresetList,
    StudioChatRequest,
    StudioChatResponse,
)
from app.schemas.job import JobSummary
from app.services.asset_review import image_artifacts_by_view, missing_uploaded_views
from app.services.studio_chat import (
    StudioChatLLMConfig,
    build_spec_with_primitive_resolver,
    build_studio_chat_trace,
    chat_with_ollama,
    list_ollama_models,
    post_json,
    primitive_registry,
    resolve_primitive_spec,
    studio_chat_presets,
)

router = APIRouter(prefix="/studio-chat", tags=["studio-chat"])


def _review_render_views(review_views: list[str]) -> list[str]:
    return ["back" if view == "rear" else view for view in review_views]


def _chat_review_views(review_views: list[str]) -> list[str]:
    return ["rear" if view == "back" else view for view in review_views]


def _artifact_url(artifact: Artifact) -> str:
    return artifact.public_url or f"/review/artifacts/{artifact.id}"


def _asset_review_url(asset_id: str) -> str:
    return f"/review/assets/{asset_id}"


def _absolute_url(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return f"{base_url.rstrip('/')}{path_or_url}"


def _conversation_payload(body: StudioChatRequest, trace: dict) -> dict:
    return {
        "creative_request": body.prompt,
        "llm_response": trace["raw_response"],
        "llm_prompt": trace["llm_prompt"],
        "scene_plan_prompt": trace["scene_plan_prompt"],
        "scene_plan_response": trace["scene_plan_response"],
        "repair_prompt": trace["repair_prompt"],
        "repair_response": trace["repair_response"],
        "scene_plan": trace["parsed_scene_plan"].model_dump(),
        "repaired_scene_plan": trace["repaired_scene_plan"].model_dump(),
        "detail_validation_warnings": trace.get("detail_validation_warnings", []),
        "spec": trace["spec"].model_dump(),
        "priority": body.priority,
        "policy": body.policy,
    }


def _studio_response_from_conversation(
    conversation: ConversationJobResponse | dict,
    target_harness_url: str | None,
) -> StudioChatResponse:
    if isinstance(conversation, ConversationJobResponse):
        job = conversation.job
        spec = conversation.spec
        job_id = job.id
        job_status = job.status
        canonical_id = spec.canonical_id
        saved_llm_response = job.llm_response is not None
        review_url = conversation.review_url
    else:
        job = conversation["job"]
        spec = conversation["spec"]
        job_id = job["id"]
        job_status = job["status"]
        canonical_id = spec["canonical_id"]
        saved_llm_response = job.get("llm_response") is not None
        review_url = conversation["review_url"]

    if target_harness_url:
        review_url = _absolute_url(target_harness_url, review_url)
        trace_url = _absolute_url(target_harness_url, f"/api/v1/debug/jobs/{job_id}/trace")
    else:
        trace_url = f"/api/v1/debug/jobs/{job_id}/trace"

    return StudioChatResponse(
        job_id=job_id,
        status=job_status,
        canonical_id=canonical_id,
        review_url=review_url,
        trace_url=trace_url,
        saved_llm_response=saved_llm_response,
        target_harness_url=target_harness_url,
        job=job,
        spec=spec,
    )


async def _submit_remote(body: StudioChatRequest, trace: dict, target_harness_url: str, token: str) -> dict:
    try:
        await asyncio.to_thread(
            post_json,
            f"{target_harness_url.rstrip('/')}/api/v1/conversations/accept",
            {"creative_request": body.prompt},
            token,
            10,
        )
        return await asyncio.to_thread(
            post_json,
            f"{target_harness_url.rstrip('/')}/api/v1/conversations/jobs",
            _conversation_payload(body, trace),
            token,
            60,
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach target harness at {target_harness_url}: {exc}",
        ) from exc


@router.get("/models", response_model=StudioChatModelList)
async def studio_chat_models():
    settings = get_settings()
    try:
        models = await asyncio.to_thread(list_ollama_models, settings.studio_chat_ollama_url)
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Ollama at {settings.studio_chat_ollama_url}: {exc}",
        ) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama did not return a usable model list: {exc}",
        ) from exc
    default_model = settings.studio_chat_model
    if models and default_model not in models:
        default_model = next(
            (model for model in models if model.split(":", 1)[0] == settings.studio_chat_model),
            models[0],
        )
    return StudioChatModelList(
        models=models,
        default_model=default_model,
        ollama_base_url=settings.studio_chat_ollama_url,
    )


@router.get("/presets", response_model=StudioChatPresetList)
async def studio_chat_role_presets():
    return StudioChatPresetList(presets=studio_chat_presets())


@router.post("/chat", response_model=StudioChatOllamaResponse)
async def studio_chat_ollama(body: StudioChatOllamaRequest):
    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Streaming is not implemented in the first lightweight slice; send stream=false.",
        )
    settings = get_settings()
    try:
        return await asyncio.to_thread(chat_with_ollama, settings.studio_chat_ollama_url, body)
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Ollama at {settings.studio_chat_ollama_url}: {exc}",
        ) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama did not return a usable chat response: {exc}",
        ) from exc


@router.post("/primitive-resolver", response_model=StudioChatPrimitiveResolveResponse)
async def studio_chat_primitive_resolver(body: StudioChatPrimitiveResolveRequest):
    settings = get_settings()
    try:
        resolved = await asyncio.to_thread(
            resolve_primitive_spec,
            settings.studio_chat_ollama_url,
            body.model or settings.studio_chat_model,
            body.creative_request,
            body.assistant_response,
            body.max_retries,
        )
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Ollama at {settings.studio_chat_ollama_url}: {exc}",
        ) from exc
    return StudioChatPrimitiveResolveResponse(
        resolved=resolved,
        registry=primitive_registry(),
    )


@router.post(
    "/build-jobs",
    response_model=StudioChatBuildJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_build_job(
    body: StudioChatBuildJobRequest,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    try:
        spec, parsed_response, resolver_output = build_spec_with_primitive_resolver(
            body.creative_request,
            body.assistant_response,
            body.messages,
            settings.studio_chat_ollama_url,
            body.model or settings.studio_chat_model,
            resolver_retries=1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    payload = _build_job_payload(body.creative_request, spec)
    review_url = ""
    asset_review_url = f"/review/assets/{spec.canonical_id}"
    asset_path_template = payload["payload"]["artifact_paths"][0]
    payload["payload"] = {
        **payload["payload"],
        "post_build_review": {
            "enabled": True,
            "asset_id": spec.canonical_id,
            "asset_name": spec.name,
            "asset_kind": spec.kind,
            "asset_path": asset_path_template,
            "views": _review_render_views(body.review_views),
            "quality": "preview",
            "priority": body.priority + 10,
            "gallery_url": asset_review_url,
        },
        "studio_chat": {
            "source": "oeb-studio-chat",
            "assistant_response": parsed_response,
            "primitive_resolver": resolver_output,
            "review_views": body.review_views,
        },
    }
    job = Job(
        title=payload["title"],
        description=payload["description"],
        llm_response=body.assistant_response,
        required_capabilities=payload["required_capabilities"],
        policy=body.policy,
        priority=body.priority,
        payload=payload["payload"],
        is_idempotent=True,
    )
    db.add(job)
    await db.flush()
    review_url = f"/review/jobs/{job.id}"
    job.payload = {
        **job.payload,
        "review_url": review_url,
    }
    db.add(AuditEvent(
        event_type="studio_chat.build_job_created",
        actor_type="user",
        actor_id="studio-chat",
        resource_type="job",
        resource_id=str(job.id),
        details={
            "canonical_id": spec.canonical_id,
            "review_url": review_url,
            "asset_review_url": asset_review_url,
            "review_views": body.review_views,
        },
    ))
    await db.commit()
    await db.refresh(job)
    return StudioChatBuildJobResponse(
        job=job,
        review_url=review_url,
        asset_review_url=asset_review_url,
        spec=spec,
        review_views=body.review_views,
        resolver=resolver_output,
    )


@router.get("/build-jobs/{job_id}/status", response_model=StudioChatBuildJobStatusResponse)
async def studio_chat_build_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    build_result = await db.execute(select(Job).where(Job.id == job_id))
    build_job = build_result.scalar_one_or_none()
    if not build_job:
        raise HTTPException(status_code=404, detail="Build job not found")

    payload = build_job.payload or {}
    review_config = payload.get("post_build_review") if isinstance(payload.get("post_build_review"), dict) else {}
    if not review_config:
        raise HTTPException(status_code=404, detail="Job is not a studio-chat build job")

    asset_id = str(review_config.get("asset_id") or "")
    review_result = await db.execute(
        select(Job)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Job.payload["parent_build_job_id"].as_string() == str(build_job.id),
        )
        .order_by(Job.created_at.desc())
    )
    review_job = review_result.scalars().first()
    artifacts: list[StudioChatReviewArtifact] = []
    missing_views = _chat_review_views(review_config.get("views") or [])
    gallery_ready = False
    phase = build_job.status

    if review_job:
        phase = f"review_{review_job.status}"
        artifact_result = await db.execute(
            select(Artifact).where(Artifact.job_id == review_job.id).order_by(Artifact.created_at)
        )
        review_artifacts = artifact_result.scalars().all()
        by_view = image_artifacts_by_view(asset_id, review_artifacts)
        missing_views = _chat_review_views(missing_uploaded_views(review_job, review_artifacts))
        gallery_ready = review_job.status == "completed" and not missing_views
        artifacts = [
            StudioChatReviewArtifact(
                view=_chat_review_views([view])[0],
                filename=artifact.filename,
                url=_artifact_url(artifact),
            )
            for view, artifact in by_view.items()
        ]
        artifacts.sort(key=lambda artifact: artifact.view)
    elif build_job.status == "completed":
        phase = "review_pending"

    return StudioChatBuildJobStatusResponse(
        build_job=JobSummary.model_validate(build_job),
        build_review_url=str(payload.get("review_url") or f"/review/jobs/{build_job.id}"),
        asset_review_url=_asset_review_url(asset_id),
        review_job=JobSummary.model_validate(review_job) if review_job else None,
        gallery_ready=gallery_ready,
        missing_views=missing_views,
        artifacts=artifacts,
        phase=phase,
    )


@router.post("", response_model=StudioChatResponse, dependencies=[Depends(require_admin)])
async def studio_chat(body: StudioChatRequest, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    llm_config = StudioChatLLMConfig(
        ollama_url=settings.studio_chat_ollama_url,
        model=settings.studio_chat_model,
    )

    try:
        trace = await asyncio.to_thread(build_studio_chat_trace, body.prompt, llm_config)
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach studio chat LLM at {settings.studio_chat_ollama_url}: {exc}",
        ) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Studio chat LLM did not return usable JSON: {exc}",
        ) from exc

    target_harness_url = (body.target_harness_url or settings.studio_chat_harness_url).strip()
    if target_harness_url:
        token = settings.studio_chat_admin_token or settings.admin_token
        remote_response = await _submit_remote(body, trace, target_harness_url, token)
        return _studio_response_from_conversation(remote_response, target_harness_url)

    conversation_body = ConversationJobRequest.model_validate(_conversation_payload(body, trace))
    local_response = await create_conversation_job(conversation_body, db)
    return _studio_response_from_conversation(local_response, None)
