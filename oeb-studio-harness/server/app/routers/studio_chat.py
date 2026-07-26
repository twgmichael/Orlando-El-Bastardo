import asyncio
import json
import math
import re
import shutil
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job
from app.models.studio_chat import (
    StudioChatAsset,
    StudioChatAssetRevision,
    StudioChatBuildEvent,
    StudioChatMilestone,
    StudioChatMessageRecord,
    StudioChatThread,
    StudioChatTraceEvent,
)
from app.routers.review import _artifact_file_path
from app.routers.conversations import _build_job_payload, create_conversation_job
from app.schemas.conversation import ConversationJobRequest, ConversationJobResponse
from app.schemas.conversation import PrimitiveBuildSpec
from app.schemas.studio_chat import (
    STANDARD_REVIEW_VIEWS,
    StudioChatBuildJobRequest,
    StudioChatBuildJobResponse,
    StudioChatBuildJobStatusResponse,
    StudioChatAssetCreateRequest,
    StudioChatAssetEditRequest,
    StudioChatAssetEditResponse,
    StudioChatAssetListResponse,
    StudioChatAssetRevertRequest,
    StudioChatAssetRevertResponse,
    StudioChatAssetResponse,
    StudioChatAssetRevisionListResponse,
    StudioChatAssetRevisionResponse,
    StudioChatModelList,
    StudioChatMilestoneCreateRequest,
    StudioChatMilestoneFile,
    StudioChatMilestoneListResponse,
    StudioChatMilestoneRender,
    StudioChatMilestoneResponse,
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
from app.services.asset_review import (
    display_review_view,
    image_artifacts_by_view,
    normalize_review_views,
    review_artifact_readiness,
)
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
    return normalize_review_views(review_views)


def _chat_review_views(review_views: list[str]) -> list[str]:
    return [display_review_view(view) or view for view in review_views]


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


def _safe_slug(value: str, fallback: str = "milestone") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip().lower()).strip("_")
    return slug[:80] or fallback


def _milestone_file_url(milestone_id: uuid.UUID, relative_path: str) -> str:
    return f"/api/v1/studio-chat/milestones/{milestone_id}/files/{relative_path}"


def _copy_file_if_available(source: Path, dest: Path) -> int | None:
    if not source.exists() or not source.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest.stat().st_size


def _copy_tree_if_available(source: Path, dest: Path) -> int | None:
    if not source.exists() or not source.is_dir():
        return None
    shutil.copytree(source, dest)
    return sum(path.stat().st_size for path in dest.rglob("*") if path.is_file())


def _job_output_candidates(job_id: uuid.UUID) -> list[Path]:
    module_path = Path(__file__).resolve()
    candidates = []
    for parent in module_path.parents:
        candidates.append(parent / "oeb-worker-output" / "jobs" / str(job_id))
        candidates.append(parent.parent / "oeb-worker-output" / "jobs" / str(job_id))
    unique: list[Path] = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _find_job_output_dir(job_id: uuid.UUID) -> Path | None:
    for candidate in _job_output_candidates(job_id):
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _review_render_candidates(job_id: uuid.UUID) -> list[Path]:
    module_path = Path(__file__).resolve()
    candidates = []
    for parent in module_path.parents:
        candidates.append(parent / "oeb-worker-output" / "oeb-studio-harness" / "review-renders" / str(job_id))
        candidates.append(parent.parent / "oeb-worker-output" / "oeb-studio-harness" / "review-renders" / str(job_id))
    unique: list[Path] = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _find_review_render_dir(job_id: uuid.UUID) -> Path | None:
    for candidate in _review_render_candidates(job_id):
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _view_from_render_filename(asset_id: str | None, filename: str) -> str | None:
    stem = Path(filename).stem
    view = None
    if asset_id and stem.startswith(f"{asset_id}_"):
        view = stem[len(asset_id) + 1:]
    else:
        view = stem.rsplit("_", 1)[-1]
    view = "rear" if view == "back" else view
    return view if view in {"top", "bottom", "left", "right", "front", "rear", "action"} else None


def _write_json(path: Path, payload: dict | list) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path.stat().st_size


def _write_text(path: Path, text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def _manifest_response(milestone: StudioChatMilestone) -> StudioChatMilestoneResponse:
    manifest = milestone.manifest_json or {}
    return StudioChatMilestoneResponse(
        id=milestone.id,
        thread_id=milestone.thread_id,
        message_id=milestone.message_id,
        asset_id=milestone.asset_id,
        revision=milestone.revision,
        label=milestone.label,
        bundle_path=milestone.bundle_path,
        manifest=manifest,
        files=[
            StudioChatMilestoneFile.model_validate(file_info)
            for file_info in manifest.get("files", [])
        ],
        renders=[
            StudioChatMilestoneRender.model_validate(render_info)
            for render_info in manifest.get("renders", [])
        ],
        missing_views=manifest.get("missing_views", []),
        created_at=milestone.created_at,
    )


def _asset_response(asset: StudioChatAsset) -> StudioChatAssetResponse:
    return StudioChatAssetResponse.model_validate(asset)


def _revision_response(revision: StudioChatAssetRevision) -> StudioChatAssetRevisionResponse:
    return StudioChatAssetRevisionResponse.model_validate(revision)


async def _get_thread_or_404(db: AsyncSession, thread_id: uuid.UUID) -> StudioChatThread:
    result = await db.execute(select(StudioChatThread).where(StudioChatThread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Studio chat thread not found")
    return thread


async def _get_chat_asset_or_404(
    db: AsyncSession,
    asset_id: str,
    thread_id: uuid.UUID | None = None,
) -> StudioChatAsset:
    query = select(StudioChatAsset).where(StudioChatAsset.asset_id == asset_id)
    if thread_id:
        query = query.where(StudioChatAsset.thread_id == thread_id)
    result = await db.execute(query.order_by(StudioChatAsset.updated_at.desc()))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Studio chat asset not found")
    return asset


def _state_paths_from_payload(payload: dict) -> tuple[str | None, str | None]:
    artifact_paths = payload.get("artifact_paths") if isinstance(payload.get("artifact_paths"), list) else []
    source_blend_path = str(payload.get("source_blend_path") or "") or None
    if not source_blend_path:
        source_blend_path = next(
            (str(path) for path in artifact_paths if str(path).lower().endswith(".blend")),
            None,
        )
    glb_path = next((str(path) for path in artifact_paths if str(path).lower().endswith(".glb")), None)
    return source_blend_path, glb_path


def _as_number_list(value: object, *, length: int = 3) -> list[float] | None:
    if not isinstance(value, list) or len(value) != length:
        return None
    numbers = []
    for item in value:
        if not isinstance(item, int | float):
            return None
        numbers.append(float(item))
    return numbers


def _primitive_matches_target(primitive: dict, target: str | None) -> bool:
    if not target or target in {"whole_asset", "asset", "*"}:
        return True
    lowered = target.lower()
    for key in ("id", "label", "name", "role"):
        value = primitive.get(key)
        if isinstance(value, str) and value.lower() == lowered:
            return True
    return False


def _construction_graph_elements(state: dict) -> list[dict]:
    graphs = []
    root_graph = state.get("construction_graph")
    if isinstance(root_graph, dict):
        graphs.append(root_graph)
    asset_intent = state.get("asset_intent")
    if isinstance(asset_intent, dict) and isinstance(asset_intent.get("construction_graph"), dict):
        graphs.append(asset_intent["construction_graph"])
    elements = []
    for graph in graphs:
        graph_elements = graph.get("elements")
        if isinstance(graph_elements, list):
            elements.extend(element for element in graph_elements if isinstance(element, dict))
    return elements


def _element_matches_target(element: dict, target: str | None) -> bool:
    if not target or target in {"whole_asset", "asset", "*"}:
        return True
    lowered = target.lower()
    for key in ("id", "label", "name", "role"):
        value = element.get(key)
        if isinstance(value, str) and value.lower() == lowered:
            return True
    return False


def _numeric_factor(edit_delta: dict, default: float | None = None) -> float | None:
    value = edit_delta.get("factor")
    if value is None:
        value = edit_delta.get("scale_factor")
    if value is None:
        value = edit_delta.get("amount")
    if value is None:
        return default
    if not isinstance(value, int | float):
        return None
    factor = float(value)
    return factor if 0.01 <= factor <= 20.0 else None


def _compile_asset_edit_state(state_before: dict, edit_delta: dict) -> tuple[dict, list[dict], bool]:
    diagnostics: list[dict] = []
    state_after = json.loads(json.dumps(state_before or {}))
    primitives = state_after.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        return state_after, [
            {
                "type": "compile_blocked",
                "message": "Asset state has no compiled primitives to edit deterministically.",
            }
        ], False

    operation = str(edit_delta.get("operation") or "").strip().lower()
    target = edit_delta.get("target")
    matched = [
        primitive
        for primitive in primitives
        if isinstance(primitive, dict) and _primitive_matches_target(primitive, target)
    ]
    if not matched:
        return state_after, [
            {
                "type": "compile_blocked",
                "message": f"Edit target does not match a known primitive or part: {target}",
            }
        ], False

    material = edit_delta.get("material") or edit_delta.get("color")
    location = _as_number_list(edit_delta.get("location") or edit_delta.get("position"))
    location_delta = _as_number_list(edit_delta.get("location_delta") or edit_delta.get("delta_location"))
    rotation = _as_number_list(edit_delta.get("rotation"))
    scale = _as_number_list(edit_delta.get("scale"))
    amount = edit_delta.get("amount")
    semantic_direction = str(edit_delta.get("semantic_direction") or "").strip().lower()
    axis = str(edit_delta.get("axis") or "").strip().lower()
    geometry_modifiers = edit_delta.get("shape_modifiers")
    if not isinstance(geometry_modifiers, list):
        geometry_modifiers = edit_delta.get("modifiers")
    if not isinstance(geometry_modifiers, list):
        geometry_modifiers = []
    hemisphere_direction = str(
        edit_delta.get("hemisphere_direction")
        or edit_delta.get("direction")
        or semantic_direction
    ).strip().lower()
    graph_elements = [
        element
        for element in _construction_graph_elements(state_after)
        if _element_matches_target(element, target)
    ]

    changed = False
    if operation in {"align_centers", "align_objects", "center_objects_on_axis"}:
        locations = [
            _as_number_list(primitive.setdefault("transform", {}).get("location"))
            or [0.0, 0.0, 0.0]
            for primitive in matched
        ]
        horizontal_center = [
            sum(location[index] for location in locations) / len(locations)
            for index in (0, 1)
        ]
        for primitive in matched:
            transform = primitive.setdefault("transform", {})
            location_value = _as_number_list(transform.get("location")) or [0.0, 0.0, 0.0]
            transform["location"] = [horizontal_center[0], horizontal_center[1], location_value[2]]
        diagnostics.append({
            "type": "aligned_centers",
            "message": f"Aligned {len(matched)} object center(s) while preserving vertical heights.",
            "horizontal_center": horizontal_center,
            "target": target or "whole_asset",
        })
        changed = True

    if operation in {"center_group", "center_objects", "center", "align_center"}:
        locations = [
            _as_number_list(primitive.setdefault("transform", {}).get("location"))
            or [0.0, 0.0, 0.0]
            for primitive in matched
        ]
        centroid = [
            sum(location[index] for location in locations) / len(locations)
            for index in range(3)
        ]
        for primitive in matched:
            transform = primitive.setdefault("transform", {})
            location_value = _as_number_list(transform.get("location")) or [0.0, 0.0, 0.0]
            transform["location"] = [
                location_value[index] - centroid[index]
                for index in range(3)
            ]
        diagnostics.append({
            "type": "centered_group",
            "message": f"Centered {len(matched)} object(s) on the asset origin while preserving relative offsets.",
            "previous_centroid": centroid,
            "target": target or "whole_asset",
        })
        changed = True

    for primitive in matched:
        transform = primitive.setdefault("transform", {})
        current_scale = _as_number_list(transform.get("scale")) or [1.0, 1.0, 1.0]
        if operation in {"align_centers", "align_objects", "center_objects_on_axis", "center_group", "center_objects", "center", "align_center"}:
            continue
        if operation in {"set_geometry_modifier", "geometry_modifier", "set_shape_modifier", "shape_modifier", "cut", "hemisphere", "half"}:
            primitive_type = str(primitive.get("type") or "").lower()
            if primitive_type not in {"sphere", "uv_sphere"}:
                diagnostics.append({
                    "type": "compile_blocked",
                    "message": f"Geometry modifier edit requires a sphere target, got {primitive_type or '<missing>'}.",
                })
                continue
            params = primitive.setdefault("params", {})
            existing = params.get("shape_modifiers")
            modifiers = [str(item).strip().lower() for item in existing] if isinstance(existing, list) else []
            requested = [str(item).strip().lower() for item in geometry_modifiers]
            if operation in {"cut", "hemisphere", "half"} and "half" not in requested:
                requested.append("half")
            if "half" in requested and "flat" not in requested:
                requested.append("flat")
            params["shape_modifiers"] = list(dict.fromkeys(modifiers + [item for item in requested if item]))
            if "half" in params["shape_modifiers"] or "hemisphere" in params["shape_modifiers"]:
                if hemisphere_direction in {"down", "-z", "bottom", "flat_up", "flat-top"}:
                    transform["rotation"] = [math.pi, 0.0, 0.0]
                elif hemisphere_direction in {"up", "+z", "top", "flat_down", "flat-bottom", ""}:
                    transform["rotation"] = [0.0, 0.0, 0.0]
                else:
                    diagnostics.append({
                        "type": "compile_blocked",
                        "message": "Hemisphere direction must be up or down.",
                    })
                    continue
            changed = True
        elif material and operation in {"set_material", "material", "recolor", "change_color", "color"}:
            primitive["material"] = str(material)
            changed = True
        elif location and operation in {"set_location", "position", "move_to"}:
            transform["location"] = location
            changed = True
        elif location_delta or operation in {"translate", "move", "adjust_position"}:
            current = _as_number_list(transform.get("location")) or [0.0, 0.0, 0.0]
            delta = location_delta
            if not delta and isinstance(amount, int | float) and semantic_direction:
                direction_vectors = {
                    "front": [float(amount), 0.0, 0.0],
                    "forward": [float(amount), 0.0, 0.0],
                    "rear": [-float(amount), 0.0, 0.0],
                    "back": [-float(amount), 0.0, 0.0],
                    "left": [0.0, -float(amount), 0.0],
                    "right": [0.0, float(amount), 0.0],
                    "up": [0.0, 0.0, float(amount)],
                    "down": [0.0, 0.0, -float(amount)],
                }
                delta = direction_vectors.get(semantic_direction)
            if not delta:
                diagnostics.append({
                    "type": "compile_blocked",
                    "message": "Move edit requires location_delta or semantic_direction plus amount.",
                })
                continue
            transform["location"] = [current[idx] + delta[idx] for idx in range(3)]
            changed = True
        elif rotation and operation in {"set_rotation", "rotate"}:
            transform["rotation"] = rotation
            changed = True
        elif scale and operation in {"set_scale", "scale", "resize"}:
            transform["scale"] = scale
            changed = True
        elif operation in {"proportional_scale", "scale_relative", "scale_uniform"}:
            factor = _numeric_factor(edit_delta)
            if factor is None:
                diagnostics.append({
                    "type": "compile_blocked",
                    "message": "Proportional scale edit requires numeric factor between 0.01 and 20.0.",
                })
                continue
            transform["scale"] = [component * factor for component in current_scale]
            if not target or target in {"whole_asset", "asset", "*"}:
                current_location = _as_number_list(transform.get("location")) or [0.0, 0.0, 0.0]
                transform["location"] = [component * factor for component in current_location]
            changed = True
        elif operation in {"scale_axis", "resize_axis"}:
            factor = _numeric_factor(edit_delta)
            axis_map = {"x": 0, "+x": 0, "-x": 0, "y": 1, "+y": 1, "-y": 1, "z": 2, "+z": 2, "-z": 2}
            axis_index = axis_map.get(axis)
            if factor is None or axis_index is None:
                diagnostics.append({
                    "type": "compile_blocked",
                    "message": "Axis scale edit requires axis x/y/z and numeric factor between 0.01 and 20.0.",
                })
                continue
            next_scale = current_scale.copy()
            next_scale[axis_index] *= factor
            transform["scale"] = next_scale
            changed = True
        elif operation in {"set_thickness", "adjust_thickness"}:
            current_thickness = float(current_scale[0])
            if operation == "adjust_thickness" and isinstance(amount, int | float):
                thickness = current_thickness + float(amount)
            else:
                thickness = float(amount) if isinstance(amount, int | float) else None
            if thickness is None or not 0.01 <= thickness <= 20.0:
                diagnostics.append({
                    "type": "compile_blocked",
                    "message": "Thickness edit requires numeric amount that resolves between 0.01 and 20.0.",
                })
                continue
            next_scale = current_scale.copy()
            next_scale[0] = thickness
            next_scale[1] = thickness
            transform["scale"] = next_scale
            construction_element = primitive.get("construction_element")
            if isinstance(construction_element, dict):
                construction_element["thickness"] = thickness
            changed = True
        else:
            diagnostics.append({
                "type": "compile_blocked",
                "message": f"Unsupported deterministic edit operation: {operation}",
            })

    if changed and operation in {"proportional_scale", "scale_relative", "scale_uniform"}:
        factor = _numeric_factor(edit_delta)
        if factor is not None:
            for element in graph_elements:
                for key in ("from", "to"):
                    vector = _as_number_list(element.get(key))
                    if vector:
                        element[key] = [component * factor for component in vector]
                if isinstance(element.get("thickness"), int | float):
                    element["thickness"] = float(element["thickness"]) * factor
    if changed and operation in {"set_thickness", "adjust_thickness"}:
        for element in graph_elements:
            if isinstance(amount, int | float):
                element["thickness"] = float(amount) if operation == "set_thickness" else float(element.get("thickness") or 0) + float(amount)

    if not changed:
        return state_after, diagnostics, False
    state_after["last_edit_delta"] = edit_delta
    state_after["pending_edit"] = False
    state_after["source"] = "studio_chat_asset_edit"
    diagnostics.append({
        "type": "compiled",
        "message": f"Compiled {operation} edit for {len(matched)} target primitive(s).",
    })
    return state_after, diagnostics, True


async def _record_asset_revision(
    db: AsyncSession,
    *,
    asset: StudioChatAsset,
    revision_number: int,
    parent_revision: int | None,
    message_id: uuid.UUID | None,
    job_id: uuid.UUID | None,
    state_before: dict,
    edit_delta: dict,
    state_after: dict,
    source_blend_path: str | None,
    glb_path: str | None,
    review_artifacts: list | None = None,
    status_value: str = "created",
) -> StudioChatAssetRevision:
    revision = StudioChatAssetRevision(
        chat_asset_id=asset.id,
        revision=revision_number,
        parent_revision=parent_revision,
        message_id=message_id,
        job_id=job_id,
        state_before=state_before,
        edit_delta=edit_delta,
        state_after=state_after,
        source_blend_path=source_blend_path,
        glb_path=glb_path,
        review_artifacts=review_artifacts or [],
        status=status_value,
    )
    db.add(revision)
    # Revision responses and trace events need database-generated fields now,
    # before this request serializes the revision into its build response.
    await db.flush()
    return revision


async def _upsert_asset_state_from_build(
    db: AsyncSession,
    *,
    thread_id: uuid.UUID,
    message_id: uuid.UUID | None,
    job: Job,
    spec: dict,
    build_payload: dict,
) -> tuple[StudioChatAsset, StudioChatAssetRevision]:
    asset_id = str(spec.get("canonical_id") or "")
    if not asset_id:
        raise ValueError("spec canonical_id is required for asset state")
    result = await db.execute(
        select(StudioChatAsset).where(
            StudioChatAsset.thread_id == thread_id,
            StudioChatAsset.asset_id == asset_id,
        )
    )
    asset = result.scalar_one_or_none()
    now = _now()
    state_before = dict(asset.state_json) if asset and isinstance(asset.state_json, dict) else {}
    source_blend_path, glb_path = _state_paths_from_payload(build_payload)
    state_after = {
        **spec,
        "asset_id": asset_id,
        "source_job_id": str(job.id),
        "source": "studio_chat_build",
    }
    if asset:
        parent_revision = asset.current_revision
        revision_number = asset.current_revision + 1
        asset.current_revision = revision_number
        asset.state_json = state_after
        asset.source_blend_path = source_blend_path or asset.source_blend_path
        asset.glb_path = glb_path or asset.glb_path
        asset.updated_at = now
    else:
        parent_revision = None
        revision_number = 1
        asset = StudioChatAsset(
            thread_id=thread_id,
            asset_id=asset_id,
            base_builder=str(build_payload.get("tool") or "primitive_asset_builder"),
            current_revision=revision_number,
            state_json=state_after,
            source_blend_path=source_blend_path,
            glb_path=glb_path,
            created_at=now,
            updated_at=now,
        )
        db.add(asset)
        await db.flush()
    revision = await _record_asset_revision(
        db,
        asset=asset,
        revision_number=revision_number,
        parent_revision=parent_revision,
        message_id=message_id,
        job_id=job.id,
        state_before=state_before,
        edit_delta={"operation": "initial_build"},
        state_after=state_after,
        source_blend_path=source_blend_path,
        glb_path=glb_path,
        status_value="build_created",
    )
    return asset, revision


def _edit_build_job_from_state(
    *,
    asset: StudioChatAsset,
    revision_number: int,
    state_after: dict,
    edit_delta: dict,
    priority: int = 0,
) -> tuple[Job, str, str]:
    spec = PrimitiveBuildSpec.model_validate(state_after)
    creative_request = str(
        edit_delta.get("creative_request")
        or edit_delta.get("description")
        or state_after.get("creative_request")
        or f"Edit {asset.asset_id} revision {revision_number}"
    )
    payload = _build_job_payload(creative_request, spec)
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
            "views": _review_render_views(STANDARD_REVIEW_VIEWS),
            "quality": "preview",
            "priority": priority + 10,
            "gallery_url": asset_review_url,
        },
        "studio_chat": {
            "source": "oeb-studio-chat",
            "thread_id": str(asset.thread_id),
            "asset_id": asset.asset_id,
            "base_revision": asset.current_revision,
            "target_revision": revision_number,
            "edit_delta": edit_delta,
            "review_views": STANDARD_REVIEW_VIEWS,
        },
    }
    job = Job(
        title=f"Edit {asset.asset_id} revision {revision_number}",
        description=creative_request,
        llm_response=json.dumps(edit_delta, indent=2, sort_keys=True),
        required_capabilities=payload["required_capabilities"],
        policy=payload["policy"],
        priority=priority,
        payload=payload["payload"],
        is_idempotent=True,
    )
    review_url = f"/review/jobs/{{job_id}}"
    return job, review_url, asset_review_url


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


async def _latest_thread_build_job(db: AsyncSession, thread_id: uuid.UUID) -> Job | None:
    event_result = await db.execute(
        select(StudioChatBuildEvent)
        .where(
            StudioChatBuildEvent.thread_id == thread_id,
            StudioChatBuildEvent.event_type.in_(["review_ready", "build_created", "failure"]),
            StudioChatBuildEvent.job_id.is_not(None),
        )
        .order_by(StudioChatBuildEvent.created_at.desc())
    )
    for event in event_result.scalars().all():
        job_result = await db.execute(select(Job).where(Job.id == event.job_id))
        job = job_result.scalar_one_or_none()
        if job:
            return job
    return None


async def _build_job_for_milestone(
    db: AsyncSession,
    thread_id: uuid.UUID,
    build_job_id: uuid.UUID | None,
) -> Job | None:
    if build_job_id:
        result = await db.execute(select(Job).where(Job.id == build_job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Build job not found")
        return job
    return await _latest_thread_build_job(db, thread_id)


async def _review_job_for_build(db: AsyncSession, build_job: Job | None) -> Job | None:
    if not build_job:
        return None
    result = await db.execute(
        select(Job)
        .where(
            Job.payload["job_type"].as_string() == "asset.review_render",
            Job.payload["parent_build_job_id"].as_string() == str(build_job.id),
        )
        .order_by(Job.created_at.desc())
    )
    return result.scalars().first()


async def _job_artifacts(db: AsyncSession, job: Job | None) -> list[Artifact]:
    if not job:
        return []
    result = await db.execute(
        select(Artifact).where(Artifact.job_id == job.id).order_by(Artifact.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/threads/{thread_id}/milestones",
    response_model=StudioChatMilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_thread_milestone(
    thread_id: uuid.UUID,
    body: StudioChatMilestoneCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    thread = await _get_thread_or_404(db, thread_id)
    build_job = await _build_job_for_milestone(db, thread_id, body.build_job_id)
    review_job = await _review_job_for_build(db, build_job)
    build_payload = build_job.payload if build_job and isinstance(build_job.payload, dict) else {}
    review_config = (
        build_payload.get("post_build_review")
        if isinstance(build_payload.get("post_build_review"), dict)
        else {}
    )
    asset_id = str(review_config.get("asset_id") or "") or None
    review_views = _chat_review_views(review_config.get("views") or [])
    label = body.label.strip() if body.label and body.label.strip() else None
    now = _now()
    milestone_id = uuid.uuid4()
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    asset_slug = _safe_slug(asset_id or thread.title or "thread")
    label_slug = f"_{_safe_slug(label, 'milestone')}" if label else ""
    bundle_name = f"{timestamp}_{asset_slug}{label_slug}_{milestone_id.hex[:8]}"
    bundle_root = Path(get_settings().studio_chat_milestones_root) / bundle_name
    bundle_root.mkdir(parents=True, exist_ok=False)

    await record_studio_chat_trace(
        db,
        thread_id,
        "milestone.requested",
        "backend",
        "Milestone requested",
        {
            "milestone_id": str(milestone_id),
            "label": label,
            "build_job_id": str(build_job.id) if build_job else None,
            "review_job_id": str(review_job.id) if review_job else None,
        },
        message_id=body.message_id,
        job_id=build_job.id if build_job else None,
    )

    files: list[dict] = []
    renders: list[dict] = []

    def add_json_file(source: str, relative_path: str, payload: dict | list) -> None:
        size = _write_json(bundle_root / relative_path, payload)
        files.append({
            "source": source,
            "path": relative_path,
            "filename": Path(relative_path).name,
            "url": _milestone_file_url(milestone_id, relative_path),
            "size_bytes": size,
        })

    def add_text_file(source: str, relative_path: str, text: str) -> None:
        size = _write_text(bundle_root / relative_path, text)
        files.append({
            "source": source,
            "path": relative_path,
            "filename": Path(relative_path).name,
            "url": _milestone_file_url(milestone_id, relative_path),
            "size_bytes": size,
        })

    if build_job:
        add_json_file("build_job", "artifacts/build_job.json", JobSummary.model_validate(build_job).model_dump(mode="json"))
        add_json_file("build_payload", "artifacts/build_payload.json", build_payload)
        spec_json = (
            build_payload.get("conversation", {}).get("spec")
            if isinstance(build_payload.get("conversation"), dict)
            else None
        )
        if isinstance(spec_json, dict):
            add_json_file("asset_state", "state/asset_state.json", spec_json)
    if review_job:
        add_json_file("review_job", "artifacts/review_job.json", JobSummary.model_validate(review_job).model_dump(mode="json"))
        add_json_file("review_payload", "artifacts/review_payload.json", review_job.payload or {})

    trace_result = await db.execute(
        select(StudioChatTraceEvent)
        .where(StudioChatTraceEvent.thread_id == thread_id)
        .order_by(StudioChatTraceEvent.created_at)
    )
    trace_payload = [
        StudioChatTraceEventResponse.model_validate(event).model_dump(mode="json")
        for event in trace_result.scalars().all()
    ]
    add_json_file("studio_chat_trace", "traces/studio_chat_trace.json", trace_payload)

    message_result = await db.execute(
        select(StudioChatMessageRecord)
        .where(StudioChatMessageRecord.thread_id == thread_id)
        .order_by(StudioChatMessageRecord.created_at)
    )
    messages_payload = [
        StudioChatThreadMessageResponse.model_validate(message).model_dump(mode="json")
        for message in message_result.scalars().all()
    ]
    add_json_file("studio_chat_messages", "state/thread_messages.json", messages_payload)

    build_artifacts = await _job_artifacts(db, build_job)
    review_artifacts = await _job_artifacts(db, review_job)
    render_by_view = image_artifacts_by_view(asset_id or "", review_artifacts) if asset_id else {}
    expected_views = review_views or sorted(render_by_view)

    for artifact in build_artifacts:
        source = _artifact_file_path(artifact)
        relative_path = f"artifacts/build/{Path(artifact.filename).name}"
        size = _copy_file_if_available(source, bundle_root / relative_path)
        if size is not None:
            files.append({
                "source": f"artifact:{artifact.id}",
                "path": relative_path,
                "filename": Path(relative_path).name,
                "url": _milestone_file_url(milestone_id, relative_path),
                "size_bytes": size,
            })

    if build_job:
        job_output_dir = _find_job_output_dir(build_job.id)
        if job_output_dir:
            relative_path = f"working/jobs/{build_job.id}"
            size = _copy_tree_if_available(job_output_dir, bundle_root / relative_path)
            if size is not None:
                files.append({
                    "source": "job_output_directory",
                    "path": relative_path,
                    "filename": str(build_job.id),
                    "url": None,
                    "size_bytes": size,
            })

    copied_render_views = set()
    for view, artifact in render_by_view.items():
        display_view = _chat_review_views([view])[0]
        suffix = Path(artifact.filename).suffix or ".png"
        relative_path = f"renders/{display_view}{suffix}"
        size = _copy_file_if_available(_artifact_file_path(artifact), bundle_root / relative_path)
        if size is not None:
            copied_render_views.add(display_view)
            renders.append({
                "view": display_view,
                "path": relative_path,
                "filename": Path(relative_path).name,
                "url": _milestone_file_url(milestone_id, relative_path),
                "source_artifact_id": str(artifact.id),
                "size_bytes": size,
            })

    if review_job:
        review_render_dir = _find_review_render_dir(review_job.id)
        if review_render_dir:
            for render_path in sorted(review_render_dir.iterdir()):
                if render_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                display_view = _view_from_render_filename(asset_id, render_path.name)
                if not display_view or display_view in copied_render_views:
                    continue
                relative_path = f"renders/{display_view}{render_path.suffix.lower()}"
                size = _copy_file_if_available(render_path, bundle_root / relative_path)
                if size is not None:
                    copied_render_views.add(display_view)
                    renders.append({
                        "view": display_view,
                        "path": relative_path,
                        "filename": Path(relative_path).name,
                        "url": _milestone_file_url(milestone_id, relative_path),
                        "source_artifact_id": None,
                        "size_bytes": size,
                    })

    renders.sort(key=lambda render: render["view"])
    missing_views = [view for view in expected_views if view not in copied_render_views]

    readme_lines = [
        "# Studio Chat Milestone",
        "",
        f"Created: {now.isoformat()}",
        f"Thread: {thread_id}",
        f"Label: {label or ''}",
        f"Asset: {asset_id or ''}",
        f"Build job: {build_job.id if build_job else ''}",
        f"Review job: {review_job.id if review_job else ''}",
        "",
        "Saved renders:",
        *[f"- {render['view']}: {render['path']}" for render in renders],
        "",
        "Missing views:",
        *[f"- {view}" for view in missing_views],
    ]
    add_text_file("summary", "README.md", "\n".join(readme_lines).rstrip() + "\n")

    manifest = {
        "milestone_id": str(milestone_id),
        "label": label,
        "created_at": now.isoformat(),
        "thread_id": str(thread_id),
        "message_id": str(body.message_id) if body.message_id else None,
        "asset_id": asset_id,
        "revision": None,
        "build_job_id": str(build_job.id) if build_job else None,
        "review_job_id": str(review_job.id) if review_job else None,
        "bundle_path": str(bundle_root),
        "files": files,
        "renders": renders,
        "missing_views": missing_views,
    }
    _write_json(bundle_root / "milestone.json", manifest)
    files.insert(0, {
        "source": "milestone_manifest",
        "path": "milestone.json",
        "filename": "milestone.json",
        "url": _milestone_file_url(milestone_id, "milestone.json"),
        "size_bytes": (bundle_root / "milestone.json").stat().st_size,
    })
    manifest["files"] = files
    _write_json(bundle_root / "milestone.json", manifest)

    milestone = StudioChatMilestone(
        id=milestone_id,
        thread_id=thread_id,
        message_id=body.message_id,
        asset_id=asset_id,
        revision=None,
        label=label,
        bundle_path=str(bundle_root),
        manifest_json=manifest,
        created_at=now,
    )
    db.add(milestone)
    await _record_thread_event(
        db,
        thread_id,
        "milestone_created",
        {"milestone": manifest},
        message_id=body.message_id,
        job_id=build_job.id if build_job else None,
        asset_id=asset_id,
    )
    await record_studio_chat_trace(
        db,
        thread_id,
        "milestone.created",
        "backend",
        "Milestone created",
        manifest,
        message_id=body.message_id,
        job_id=build_job.id if build_job else None,
    )
    thread.updated_at = now
    await db.commit()
    await db.refresh(milestone)
    return _manifest_response(milestone)


@router.get("/threads/{thread_id}/milestones", response_model=StudioChatMilestoneListResponse)
async def list_studio_chat_thread_milestones(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_thread_or_404(db, thread_id)
    result = await db.execute(
        select(StudioChatMilestone)
        .where(StudioChatMilestone.thread_id == thread_id)
        .order_by(StudioChatMilestone.created_at.desc())
    )
    return StudioChatMilestoneListResponse(
        milestones=[_manifest_response(milestone) for milestone in result.scalars().all()]
    )


@router.get("/threads/{thread_id}/assets", response_model=StudioChatAssetListResponse)
async def list_studio_chat_thread_assets(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_thread_or_404(db, thread_id)
    result = await db.execute(
        select(StudioChatAsset)
        .where(StudioChatAsset.thread_id == thread_id)
        .order_by(StudioChatAsset.updated_at.desc())
    )
    return StudioChatAssetListResponse(assets=[_asset_response(asset) for asset in result.scalars().all()])


@router.post(
    "/assets/{asset_id}/milestones",
    response_model=StudioChatMilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_asset_milestone(
    asset_id: str,
    body: StudioChatMilestoneCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.thread_id:
        raise HTTPException(status_code=422, detail="thread_id is required to save an asset milestone")
    await _get_thread_or_404(db, body.thread_id)
    build_job = await _build_job_for_milestone(db, body.thread_id, body.build_job_id)
    build_payload = build_job.payload if build_job and isinstance(build_job.payload, dict) else {}
    review_config = (
        build_payload.get("post_build_review")
        if isinstance(build_payload.get("post_build_review"), dict)
        else {}
    )
    effective_asset_id = str(review_config.get("asset_id") or "")
    if effective_asset_id and effective_asset_id != asset_id:
        raise HTTPException(status_code=422, detail="Build job asset does not match requested asset")
    return await create_studio_chat_thread_milestone(body.thread_id, body, db)


@router.get("/assets/{asset_id}/milestones", response_model=StudioChatMilestoneListResponse)
async def list_studio_chat_asset_milestones(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudioChatMilestone)
        .where(StudioChatMilestone.asset_id == asset_id)
        .order_by(StudioChatMilestone.created_at.desc())
    )
    return StudioChatMilestoneListResponse(
        milestones=[_manifest_response(milestone) for milestone in result.scalars().all()]
    )


@router.post(
    "/assets",
    response_model=StudioChatAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_chat_asset(
    body: StudioChatAssetCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    await _get_thread_or_404(db, body.thread_id)
    existing = await db.execute(
        select(StudioChatAsset).where(
            StudioChatAsset.thread_id == body.thread_id,
            StudioChatAsset.asset_id == body.asset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Studio chat asset already exists for this thread")
    now = _now()
    asset = StudioChatAsset(
        thread_id=body.thread_id,
        asset_id=body.asset_id,
        base_builder=body.base_builder,
        current_revision=1,
        state_json=body.state_json,
        source_blend_path=body.source_blend_path,
        glb_path=body.glb_path,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    await db.flush()
    revision = await _record_asset_revision(
        db,
        asset=asset,
        revision_number=1,
        parent_revision=None,
        message_id=None,
        job_id=None,
        state_before={},
        edit_delta={"operation": "manual_asset_state_create"},
        state_after=body.state_json,
        source_blend_path=body.source_blend_path,
        glb_path=body.glb_path,
        status_value="created",
    )
    await record_studio_chat_trace(
        db,
        body.thread_id,
        "asset.state.created",
        "backend",
        "Studio Chat asset state created",
        {
            "asset": _asset_response(asset).model_dump(mode="json"),
            "revision": _revision_response(revision).model_dump(mode="json"),
        },
    )
    await db.commit()
    await db.refresh(asset)
    return _asset_response(asset)


@router.get("/assets/{asset_id}/state", response_model=StudioChatAssetResponse)
async def get_studio_chat_asset_state(
    asset_id: str,
    thread_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_chat_asset_or_404(db, asset_id, thread_id)
    return _asset_response(asset)


@router.get("/assets/{asset_id}/revisions", response_model=StudioChatAssetRevisionListResponse)
async def list_studio_chat_asset_revisions(
    asset_id: str,
    thread_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_chat_asset_or_404(db, asset_id, thread_id)
    result = await db.execute(
        select(StudioChatAssetRevision)
        .where(StudioChatAssetRevision.chat_asset_id == asset.id)
        .order_by(StudioChatAssetRevision.revision)
    )
    return StudioChatAssetRevisionListResponse(
        asset=_asset_response(asset),
        revisions=[_revision_response(revision) for revision in result.scalars().all()],
    )


@router.post("/assets/{asset_id}/edits", response_model=StudioChatAssetEditResponse)
async def create_studio_chat_asset_edit(
    asset_id: str,
    body: StudioChatAssetEditRequest,
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_chat_asset_or_404(db, asset_id, body.thread_id)
    if body.base_revision != asset.current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Asset revision conflict",
                "current_revision": asset.current_revision,
                "requested_base_revision": body.base_revision,
            },
        )
    now = _now()
    state_before = dict(asset.state_json or {})
    edit_delta = {
        **body.edit_delta,
        "target": body.target,
        "operation": body.operation,
        "view": body.view,
        "semantic_direction": body.semantic_direction,
        "amount": body.amount,
        "preserve": body.preserve,
    }
    state_after, diagnostics, compiled = _compile_asset_edit_state(state_before, edit_delta)
    revision_number = asset.current_revision + 1
    asset.current_revision = revision_number
    asset.state_json = state_after
    asset.updated_at = now
    job = None
    review_url = None
    asset_review_url = None
    if compiled:
        try:
            job, _pending_review_url, asset_review_url = _edit_build_job_from_state(
                asset=asset,
                revision_number=revision_number,
                state_after=state_after,
                edit_delta=edit_delta,
            )
            db.add(job)
            await db.flush()
            review_url = f"/review/jobs/{job.id}"
            job.payload = {
                **(job.payload or {}),
                "review_url": review_url,
            }
        except Exception as exc:
            job = None
            review_url = None
            asset_review_url = None
            diagnostics.append({
                "type": "job_compile_failed",
                "message": str(exc),
            })
    revision = await _record_asset_revision(
        db,
        asset=asset,
        revision_number=revision_number,
        parent_revision=body.base_revision,
        message_id=body.message_id,
        job_id=job.id if job else None,
        state_before=state_before,
        edit_delta=edit_delta,
        state_after=state_after,
        source_blend_path=asset.source_blend_path,
        glb_path=asset.glb_path,
        status_value="job_created" if job else "delta_recorded",
    )
    await _record_thread_event(
        db,
        asset.thread_id,
        "asset_edit_compiled" if job else "asset_edit_recorded",
        {
            "asset": _asset_response(asset).model_dump(mode="json"),
            "revision": _revision_response(revision).model_dump(mode="json"),
            "job": JobSummary.model_validate(job).model_dump(mode="json") if job else None,
            "review_url": review_url,
            "asset_review_url": asset_review_url,
            "diagnostics": diagnostics,
        },
        message_id=body.message_id,
        job_id=job.id if job else None,
        asset_id=asset.asset_id,
    )
    await record_studio_chat_trace(
        db,
        asset.thread_id,
        "asset.edit.compiled" if job else "asset.edit.recorded",
        "backend",
        "Studio Chat asset edit delta compiled" if job else "Studio Chat asset edit delta recorded",
        {
            "asset": _asset_response(asset).model_dump(mode="json"),
            "revision": _revision_response(revision).model_dump(mode="json"),
            "job": JobSummary.model_validate(job).model_dump(mode="json") if job else None,
            "review_url": review_url,
            "asset_review_url": asset_review_url,
            "diagnostics": diagnostics,
        },
        message_id=body.message_id,
        job_id=job.id if job else None,
    )
    await db.commit()
    await db.refresh(asset)
    await db.refresh(revision)
    if job:
        await db.refresh(job)
    return StudioChatAssetEditResponse(
        asset=_asset_response(asset),
        revision=_revision_response(revision),
        accepted=True,
        job_created=job is not None,
        job=JobSummary.model_validate(job) if job else None,
        review_url=review_url,
        asset_review_url=asset_review_url,
        diagnostics=diagnostics,
    )


@router.post("/assets/{asset_id}/revert", response_model=StudioChatAssetRevertResponse)
async def revert_studio_chat_asset(
    asset_id: str,
    body: StudioChatAssetRevertRequest,
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_chat_asset_or_404(db, asset_id, body.thread_id)
    if body.base_revision != asset.current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Asset revision conflict",
                "current_revision": asset.current_revision,
                "requested_base_revision": body.base_revision,
            },
        )
    target_result = await db.execute(
        select(StudioChatAssetRevision).where(
            StudioChatAssetRevision.chat_asset_id == asset.id,
            StudioChatAssetRevision.revision == body.target_revision,
        )
    )
    target_revision = target_result.scalar_one_or_none()
    if not target_revision:
        raise HTTPException(status_code=404, detail="Target revision not found")

    state_before = dict(asset.state_json or {})
    state_after = dict(target_revision.state_after or {})
    revision_number = asset.current_revision + 1
    asset.current_revision = revision_number
    asset.state_json = state_after
    asset.source_blend_path = target_revision.source_blend_path
    asset.glb_path = target_revision.glb_path
    asset.updated_at = _now()
    revision = await _record_asset_revision(
        db,
        asset=asset,
        revision_number=revision_number,
        parent_revision=body.base_revision,
        message_id=body.message_id,
        job_id=None,
        state_before=state_before,
        edit_delta={"operation": "revert", "target_revision": body.target_revision},
        state_after=state_after,
        source_blend_path=asset.source_blend_path,
        glb_path=asset.glb_path,
        status_value="reverted",
    )
    await _record_thread_event(
        db,
        asset.thread_id,
        "asset_reverted",
        {
            "asset": _asset_response(asset).model_dump(mode="json"),
            "revision": _revision_response(revision).model_dump(mode="json"),
            "reverted_to_revision": body.target_revision,
        },
        message_id=body.message_id,
        asset_id=asset.asset_id,
    )
    await record_studio_chat_trace(
        db,
        asset.thread_id,
        "asset.reverted",
        "backend",
        "Studio Chat asset reverted",
        {
            "asset": _asset_response(asset).model_dump(mode="json"),
            "revision": _revision_response(revision).model_dump(mode="json"),
            "reverted_to_revision": body.target_revision,
        },
        message_id=body.message_id,
    )
    await db.commit()
    await db.refresh(asset)
    await db.refresh(revision)
    return StudioChatAssetRevertResponse(
        asset=_asset_response(asset),
        revision=_revision_response(revision),
        reverted_to_revision=body.target_revision,
    )


@router.get("/milestones/{milestone_id}", response_model=StudioChatMilestoneResponse)
async def get_studio_chat_milestone(
    milestone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StudioChatMilestone).where(StudioChatMilestone.id == milestone_id))
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return _manifest_response(milestone)


@router.get("/milestones/{milestone_id}/files/{relative_path:path}")
async def get_studio_chat_milestone_file(
    milestone_id: uuid.UUID,
    relative_path: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(StudioChatMilestone).where(StudioChatMilestone.id == milestone_id))
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    bundle_root = Path(milestone.bundle_path).resolve()
    file_path = (bundle_root / relative_path).resolve()
    if not file_path.is_relative_to(bundle_root) or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Milestone file not found")
    return FileResponse(file_path, filename=file_path.name)


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
    asset_state = None
    asset_revision = None
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
        asset_state, asset_revision = await _upsert_asset_state_from_build(
            db,
            thread_id=effective_thread_id,
            message_id=body.message_id,
            job=job,
            spec=spec.model_dump(mode="json"),
            build_payload=payload["payload"],
        )
        await _record_thread_event(
            db,
            effective_thread_id,
            "asset_revision_created",
            {
                "asset": _asset_response(asset_state).model_dump(mode="json"),
                "revision": _revision_response(asset_revision).model_dump(mode="json"),
            },
            message_id=body.message_id,
            job_id=job.id,
            asset_id=spec.canonical_id,
        )
        await record_studio_chat_trace(
            db,
            effective_thread_id,
            "asset.revision.created",
            "backend",
            "Studio Chat asset revision created",
            {
                "asset": _asset_response(asset_state).model_dump(mode="json"),
                "revision": _revision_response(asset_revision).model_dump(mode="json"),
            },
            message_id=body.message_id,
            job_id=job.id,
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
        asset=_asset_response(asset_state) if asset_state else None,
        revision=_revision_response(asset_revision) if asset_revision else None,
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
    readiness = {
        "requested_views": normalize_review_views(review_config.get("views") or []),
        "registered_views": [],
        "uploaded_views": [],
        "missing_registered_views": normalize_review_views(review_config.get("views") or []),
        "missing_uploaded_views": normalize_review_views(review_config.get("views") or []),
        "gallery_ready": False,
        "diagnostics": [],
    }
    missing_views = _chat_review_views(readiness["missing_registered_views"])
    gallery_ready = False
    phase = build_job.status

    if review_job:
        phase = f"review_{review_job.status}"
        artifact_result = await db.execute(
            select(Artifact).where(Artifact.job_id == review_job.id).order_by(Artifact.created_at)
        )
        review_artifacts = artifact_result.scalars().all()
        by_view = image_artifacts_by_view(asset_id, review_artifacts)
        readiness = review_artifact_readiness(review_job, review_artifacts)
        missing_views = _chat_review_views(readiness["missing_registered_views"])
        gallery_ready = review_job.status == "completed" and readiness["gallery_ready"]
        if review_job.status == "completed" and not gallery_ready:
            phase = "review_completed_attention"
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
        requested_views=_chat_review_views(readiness["requested_views"]),
        registered_views=_chat_review_views(readiness["registered_views"]),
        uploaded_views=_chat_review_views(readiness["uploaded_views"]),
        missing_views=missing_views,
        missing_registered_views=missing_views,
        missing_uploaded_views=_chat_review_views(readiness["missing_uploaded_views"]),
        diagnostics=readiness["diagnostics"],
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
    elif review_job and review_job.status == "completed" and not gallery_ready:
        event_type = "review_attention"
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
                (
                    "review.ready"
                    if event_type == "review_ready"
                    else "review.attention"
                    if event_type == "review_attention"
                    else "review.failed"
                ),
                "harness",
                (
                    "Review renders ready"
                    if event_type == "review_ready"
                    else "Review render needs attention"
                    if event_type == "review_attention"
                    else "Review render failed"
                ),
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
