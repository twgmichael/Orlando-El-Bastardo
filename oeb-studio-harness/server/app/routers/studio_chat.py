import asyncio
import urllib.error

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.routers.conversations import create_conversation_job
from app.schemas.conversation import ConversationJobRequest, ConversationJobResponse
from app.schemas.studio_chat import (
    StudioChatModelList,
    StudioChatOllamaRequest,
    StudioChatOllamaResponse,
    StudioChatPresetList,
    StudioChatRequest,
    StudioChatResponse,
)
from app.services.studio_chat import (
    StudioChatLLMConfig,
    build_studio_chat_trace,
    chat_with_ollama,
    list_ollama_models,
    post_json,
    studio_chat_presets,
)

router = APIRouter(prefix="/studio-chat", tags=["studio-chat"])


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
