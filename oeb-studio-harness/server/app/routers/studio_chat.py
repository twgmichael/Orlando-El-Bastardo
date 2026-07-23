import asyncio
import urllib.error
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.studio_chat import (
    StudioChatBuildEvent,
    StudioChatMessageRecord,
    StudioChatThread,
    StudioChatTraceEvent,
)
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
    StudioChatThreadCreateRequest,
    StudioChatThreadDetail,
    StudioChatThreadEventCreateRequest,
    StudioChatThreadEventResponse,
    StudioChatThreadListResponse,
    StudioChatThreadMessageCreateRequest,
    StudioChatThreadMessageResponse,
    StudioChatThreadSummary,
    StudioChatThreadUpdateRequest,
    StudioChatTraceEventListResponse,
    StudioChatTraceEventResponse,
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _thread_title_from_prompt(prompt: str) -> str:
    words = [word for word in prompt.strip().split() if word]
    title = " ".join(words[:8]).strip(" .")
    return title[:80] or "Studio Chat Thread"


async def _get_thread_or_404(db: AsyncSession, thread_id: uuid.UUID) -> StudioChatThread:
    result = await db.execute(select(StudioChatThread).where(StudioChatThread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Studio chat thread not found")
    return thread


async def _record_thread_event(
    db: AsyncSession,
    thread_id: uuid.UUID | None,
    event_type: str,
    payload: dict,
    message_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    asset_id: str | None = None,
    dedupe: bool = False,
) -> StudioChatBuildEvent | None:
    if not thread_id:
        return None
    if dedupe and job_id:
        existing = await db.execute(
            select(StudioChatBuildEvent).where(
                StudioChatBuildEvent.thread_id == thread_id,
                StudioChatBuildEvent.job_id == job_id,
                StudioChatBuildEvent.event_type == event_type,
            )
        )
        if existing.scalar_one_or_none():
            return None
    event = StudioChatBuildEvent(
        thread_id=thread_id,
        message_id=message_id,
        job_id=job_id,
        asset_id=asset_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    return event


async def record_studio_chat_trace(
    db: AsyncSession,
    thread_id: uuid.UUID | None,
    event_type: str,
    source: str,
    label: str,
    payload: dict,
    message_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    text_snapshot: str | None = None,
) -> StudioChatTraceEvent | None:
    if not thread_id:
        return None
    event = StudioChatTraceEvent(
        thread_id=thread_id,
        message_id=message_id,
        job_id=job_id,
        event_type=event_type,
        source=source,
        label=label,
        payload=payload,
        text_snapshot=text_snapshot,
    )
    db.add(event)
    return event


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


@router.get("/threads", response_model=StudioChatThreadListResponse)
async def list_studio_chat_threads(
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    query = select(StudioChatThread)
    if not include_archived:
        query = query.where(StudioChatThread.archived_at.is_(None))
    result = await db.execute(query.order_by(StudioChatThread.updated_at.desc()).limit(50))
    return StudioChatThreadListResponse(
        threads=[
            StudioChatThreadSummary.model_validate(thread)
            for thread in result.scalars().all()
        ]
    )


@router.post(
    "/threads",
    response_model=StudioChatThreadSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_thread(
    body: StudioChatThreadCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    now = _now()
    thread = StudioChatThread(
        title=body.title.strip() if body.title and body.title.strip() else "Studio Chat Thread",
        environment=body.environment,
        default_model=body.default_model,
        default_preset_id=body.default_preset_id,
        system_prompt=body.system_prompt,
        review_views=body.review_views,
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    await db.flush()
    await record_studio_chat_trace(
        db,
        thread.id,
        "chat.thread.created",
        "backend",
        "Thread created",
        {
            "thread": StudioChatThreadSummary.model_validate(thread).model_dump(mode="json"),
            "request": body.model_dump(mode="json"),
        },
    )
    await db.commit()
    await db.refresh(thread)
    return StudioChatThreadSummary.model_validate(thread)


@router.get("/threads/{thread_id}", response_model=StudioChatThreadDetail)
async def get_studio_chat_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    thread = await _get_thread_or_404(db, thread_id)
    message_result = await db.execute(
        select(StudioChatMessageRecord)
        .where(StudioChatMessageRecord.thread_id == thread_id)
        .order_by(StudioChatMessageRecord.created_at)
    )
    event_result = await db.execute(
        select(StudioChatBuildEvent)
        .where(StudioChatBuildEvent.thread_id == thread_id)
        .order_by(StudioChatBuildEvent.created_at)
    )
    return StudioChatThreadDetail(
        thread=StudioChatThreadSummary.model_validate(thread),
        messages=[
            StudioChatThreadMessageResponse.model_validate(message)
            for message in message_result.scalars().all()
        ],
        events=[
            StudioChatThreadEventResponse.model_validate(event)
            for event in event_result.scalars().all()
        ],
    )


@router.patch("/threads/{thread_id}", response_model=StudioChatThreadSummary)
async def update_studio_chat_thread(
    thread_id: uuid.UUID,
    body: StudioChatThreadUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    thread = await _get_thread_or_404(db, thread_id)
    if body.title is not None and body.title.strip():
        thread.title = body.title.strip()
    if body.default_model is not None:
        thread.default_model = body.default_model
    if body.default_preset_id is not None:
        thread.default_preset_id = body.default_preset_id
    if body.system_prompt is not None:
        thread.system_prompt = body.system_prompt
    if body.review_views is not None:
        thread.review_views = body.review_views
    if body.archived is True and thread.archived_at is None:
        thread.archived_at = _now()
    if body.archived is False:
        thread.archived_at = None
    thread.updated_at = _now()
    await db.commit()
    await db.refresh(thread)
    return StudioChatThreadSummary.model_validate(thread)


@router.post(
    "/threads/{thread_id}/messages",
    response_model=StudioChatThreadMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_thread_message(
    thread_id: uuid.UUID,
    body: StudioChatThreadMessageCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    thread = await _get_thread_or_404(db, thread_id)
    now = _now()
    message = StudioChatMessageRecord(
        thread_id=thread_id,
        role=body.role,
        content=body.content,
        raw=body.raw,
        created_at=now,
    )
    db.add(message)
    if body.role == "user" and thread.title == "Studio Chat Thread":
        thread.title = _thread_title_from_prompt(body.content)
    thread.updated_at = now
    await db.flush()
    await record_studio_chat_trace(
        db,
        thread_id,
        f"chat.{body.role}_message.saved",
        "backend",
        f"{body.role.title()} message saved",
        {
            "message": StudioChatThreadMessageResponse.model_validate(message).model_dump(mode="json"),
            "raw": body.raw,
        },
        message_id=message.id,
        text_snapshot=body.content,
    )
    await db.commit()
    await db.refresh(message)
    return StudioChatThreadMessageResponse.model_validate(message)


@router.post(
    "/threads/{thread_id}/events",
    response_model=StudioChatThreadEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_thread_event(
    thread_id: uuid.UUID,
    body: StudioChatThreadEventCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    thread = await _get_thread_or_404(db, thread_id)
    event = StudioChatBuildEvent(
        thread_id=thread_id,
        message_id=body.message_id,
        job_id=body.job_id,
        asset_id=body.asset_id,
        event_type=body.event_type,
        payload=body.payload,
    )
    db.add(event)
    thread.updated_at = _now()
    await db.flush()
    await record_studio_chat_trace(
        db,
        thread_id,
        f"thread_event.{body.event_type}",
        "backend",
        f"Thread event: {body.event_type}",
        {
            "event": StudioChatThreadEventResponse.model_validate(event).model_dump(mode="json"),
        },
        message_id=body.message_id,
        job_id=body.job_id,
    )
    await db.commit()
    await db.refresh(event)
    return StudioChatThreadEventResponse.model_validate(event)


@router.get("/threads/{thread_id}/events", response_model=list[StudioChatThreadEventResponse])
async def list_studio_chat_thread_events(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_thread_or_404(db, thread_id)
    result = await db.execute(
        select(StudioChatBuildEvent)
        .where(StudioChatBuildEvent.thread_id == thread_id)
        .order_by(StudioChatBuildEvent.created_at)
    )
    return [
        StudioChatThreadEventResponse.model_validate(event)
        for event in result.scalars().all()
    ]


@router.get("/threads/{thread_id}/trace", response_model=StudioChatTraceEventListResponse)
async def list_studio_chat_thread_trace(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_thread_or_404(db, thread_id)
    result = await db.execute(
        select(StudioChatTraceEvent)
        .where(StudioChatTraceEvent.thread_id == thread_id)
        .order_by(StudioChatTraceEvent.created_at)
    )
    return StudioChatTraceEventListResponse(
        trace=[
            StudioChatTraceEventResponse.model_validate(event)
            for event in result.scalars().all()
        ]
    )


@router.get("/messages/{message_id}/trace", response_model=StudioChatTraceEventListResponse)
async def list_studio_chat_message_trace(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudioChatTraceEvent)
        .where(StudioChatTraceEvent.message_id == message_id)
        .order_by(StudioChatTraceEvent.created_at)
    )
    return StudioChatTraceEventListResponse(
        trace=[
            StudioChatTraceEventResponse.model_validate(event)
            for event in result.scalars().all()
        ]
    )


@router.get("/jobs/{job_id}/trace", response_model=StudioChatTraceEventListResponse)
async def list_studio_chat_job_trace(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudioChatTraceEvent)
        .where(StudioChatTraceEvent.job_id == job_id)
        .order_by(StudioChatTraceEvent.created_at)
    )
    return StudioChatTraceEventListResponse(
        trace=[
            StudioChatTraceEventResponse.model_validate(event)
            for event in result.scalars().all()
        ]
    )


@router.post("/chat", response_model=StudioChatOllamaResponse)
async def studio_chat_ollama(
    body: StudioChatOllamaRequest,
    db: AsyncSession = Depends(get_db),
):
    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Streaming is not implemented in the first lightweight slice; send stream=false.",
        )
    settings = get_settings()
    if body.thread_id:
        await _get_thread_or_404(db, body.thread_id)
        from app.services.studio_chat import ollama_chat_payload

        await record_studio_chat_trace(
            db,
            body.thread_id,
            "ollama.request.sent",
            "backend",
            "Ollama chat request sent",
            {
                "ollama_url": settings.studio_chat_ollama_url,
                "request": ollama_chat_payload(body),
            },
            message_id=body.message_id,
        )
        await db.commit()
    try:
        response = await asyncio.to_thread(chat_with_ollama, settings.studio_chat_ollama_url, body)
        if body.thread_id:
            await record_studio_chat_trace(
                db,
                body.thread_id,
                "ollama.response.received",
                "ollama",
                "Ollama chat response received",
                response.raw,
                message_id=body.message_id,
                text_snapshot=response.message.content,
            )
            await db.commit()
        return response
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
    "/threads/{thread_id}/build-jobs",
    response_model=StudioChatBuildJobResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/build-jobs",
    response_model=StudioChatBuildJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_build_job(
    body: StudioChatBuildJobRequest,
    thread_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    effective_thread_id = thread_id or body.thread_id
    if effective_thread_id:
        await _get_thread_or_404(db, effective_thread_id)
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
        await record_studio_chat_trace(
            db,
            effective_thread_id,
            "assistant.json.parse_failed",
            "backend",
            "Assistant JSON parse/build failed",
            {
                "creative_request": body.creative_request,
                "assistant_response": body.assistant_response,
                "messages": [message.model_dump(mode="json") for message in body.messages],
                "error": str(exc),
            },
            message_id=body.message_id,
            text_snapshot=body.assistant_response,
        )
        if effective_thread_id:
            await db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await record_studio_chat_trace(
        db,
        effective_thread_id,
        "assistant.json.parsed",
        "backend",
        "Assistant JSON parsed or recovered",
        {
            "creative_request": body.creative_request,
            "assistant_response": body.assistant_response,
            "parsed_response": parsed_response,
        },
        message_id=body.message_id,
        text_snapshot=body.assistant_response,
    )
    if resolver_output:
        for attempt in resolver_output.get("attempts", []):
            await record_studio_chat_trace(
                db,
                effective_thread_id,
                "resolver.attempt.recorded",
                "resolver",
                f"Resolver attempt {attempt.get('attempt')}",
                attempt,
                message_id=body.message_id,
                text_snapshot=attempt.get("content") if isinstance(attempt.get("content"), str) else None,
            )
        await record_studio_chat_trace(
            db,
            effective_thread_id,
            "resolver.output.accepted" if resolver_output.get("ok") else "resolver.output.rejected",
            "resolver",
            "Primitive resolver output",
            resolver_output,
            message_id=body.message_id,
        )
    await record_studio_chat_trace(
        db,
        effective_thread_id,
        "spec.normalized",
        "backend",
        "Primitive spec normalized",
        spec.model_dump(mode="json"),
        message_id=body.message_id,
    )

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
            "thread_id": str(effective_thread_id) if effective_thread_id else None,
            "message_id": str(body.message_id) if body.message_id else None,
            "assistant_response": parsed_response,
            "primitive_resolver": resolver_output,
            "review_views": body.review_views,
        },
    }
    await record_studio_chat_trace(
        db,
        effective_thread_id,
        "build.job_payload.created",
        "harness",
        "Harness build job payload created",
        {
            "title": payload["title"],
            "description": payload["description"],
            "required_capabilities": payload["required_capabilities"],
            "payload": payload["payload"],
        },
        message_id=body.message_id,
    )
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
    response_payload = StudioChatBuildJobResponse(
        job=job,
        review_url=review_url,
        asset_review_url=asset_review_url,
        spec=spec,
        review_views=body.review_views,
        resolver=resolver_output,
    ).model_dump(mode="json")
    if effective_thread_id:
        await record_studio_chat_trace(
            db,
            effective_thread_id,
            "build.job_created",
            "harness",
            "Harness build job created",
            response_payload,
            message_id=body.message_id,
            job_id=job.id,
        )
        if resolver_output:
            await _record_thread_event(
                db,
                effective_thread_id,
                "resolver",
                {
                    "assistant_json": parsed_response,
                    "resolver_output": resolver_output,
                    "primitive_spec": spec.model_dump(mode="json"),
                },
                message_id=body.message_id,
                job_id=job.id,
                asset_id=spec.canonical_id,
            )
        await _record_thread_event(
            db,
            effective_thread_id,
            "build_created",
            {
                "assistant_json": parsed_response,
                "resolver_output": resolver_output,
                "primitive_spec": spec.model_dump(mode="json"),
                "job_payload": payload["payload"],
                "build_result": response_payload,
            },
            message_id=body.message_id,
            job_id=job.id,
            asset_id=spec.canonical_id,
        )
        thread = await _get_thread_or_404(db, effective_thread_id)
        thread.updated_at = _now()
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

    response = StudioChatBuildJobStatusResponse(
        build_job=JobSummary.model_validate(build_job),
        build_review_url=str(payload.get("review_url") or f"/review/jobs/{build_job.id}"),
        asset_review_url=_asset_review_url(asset_id),
        review_job=JobSummary.model_validate(review_job) if review_job else None,
        gallery_ready=gallery_ready,
        missing_views=missing_views,
        artifacts=artifacts,
        phase=phase,
    )
    studio_chat_meta = payload.get("studio_chat") if isinstance(payload.get("studio_chat"), dict) else {}
    thread_id_value = studio_chat_meta.get("thread_id")
    message_id_value = studio_chat_meta.get("message_id")
    effective_thread_id = None
    effective_message_id = None
    if thread_id_value:
        try:
            effective_thread_id = uuid.UUID(str(thread_id_value))
            effective_message_id = uuid.UUID(str(message_id_value)) if message_id_value else None
        except ValueError:
            effective_thread_id = None
            effective_message_id = None
    if effective_thread_id:
        await record_studio_chat_trace(
            db,
            effective_thread_id,
            "build.status_polled",
            "harness",
            "Build/review status polled",
            response.model_dump(mode="json"),
            message_id=effective_message_id,
            job_id=build_job.id,
        )
        await db.commit()
    event_type = None
    if gallery_ready:
        event_type = "review_ready"
    elif build_job.status == "failed" or (review_job and review_job.status == "failed"):
        event_type = "failure"
    if event_type and effective_thread_id:
            await _record_thread_event(
                db,
                effective_thread_id,
                event_type,
                {
                    "build_status": response.model_dump(mode="json"),
                    "review_artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
                },
                message_id=effective_message_id,
                job_id=build_job.id,
                asset_id=asset_id,
                dedupe=True,
            )
            await record_studio_chat_trace(
                db,
                effective_thread_id,
                "review.ready" if event_type == "review_ready" else "review.failed",
                "harness",
                "Review renders ready" if event_type == "review_ready" else "Review render failed",
                {
                    "build_status": response.model_dump(mode="json"),
                    "review_artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
                },
                message_id=effective_message_id,
                job_id=build_job.id,
            )
            await record_studio_chat_trace(
                db,
                effective_thread_id,
                "ui.card_snapshot",
                "backend",
                "Inline build card snapshot",
                {
                    "title": build_job.title,
                    "status_text": f"Build {build_job.status}; phase {phase}",
                    "build_review_url": response.build_review_url,
                    "asset_review_url": response.asset_review_url,
                    "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
                    "missing_views": missing_views,
                },
                message_id=effective_message_id,
                job_id=build_job.id,
            )
            thread_result = await db.execute(
                select(StudioChatThread).where(StudioChatThread.id == effective_thread_id)
            )
            thread = thread_result.scalar_one_or_none()
            if thread:
                thread.updated_at = _now()
            await db.commit()
    return response


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
