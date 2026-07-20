from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.artifact import Artifact
from app.models.asset import Asset
from app.models.audit import AuditEvent
from app.models.job import Job

REVIEW_VIEWS = ("top", "bottom", "left", "right", "front", "back", "action")
ANGLE_VIEWS = ("front", "back", "left", "right", "top", "bottom")
RENDER_QUALITIES = {"draft", "preview", "final"}


@dataclass(frozen=True)
class ReviewAsset:
    asset_id: str
    asset_path: str
    name: str
    aliases: tuple[str, ...] = ()


KNOWN_REVIEW_ASSETS: tuple[ReviewAsset, ...] = (
    ReviewAsset(
        asset_id="ventradi_cruiser",
        asset_path="assets/ships/ventradi_cruiser.glb",
        name="Ventradi Cruiser",
        aliases=("ventradi", "ventradi cruise", "ventradi cruiser"),
    ),
    ReviewAsset(
        asset_id="jb5k",
        asset_path="assets/ships/jb5k.glb",
        name="JB5k",
        aliases=("jb 5k", "jb-5k", "jb45", "jb 45", "journey blaster 5000"),
    ),
    ReviewAsset(
        asset_id="prop_jb100_A",
        asset_path="assets/ships/jb100.glb",
        name="JourneyBlaster 100",
        aliases=("jb100", "jb 100", "journey blaster 100", "journeyblaster 100"),
    ),
    ReviewAsset(
        asset_id="ellipso_flyer_mk1",
        asset_path="assets/ships/ellipso_flyer_mk1.glb",
        name="Ellipso Flyer",
        aliases=("ellipso", "ellipso flyer", "ellispso flyer", "ellipso flyer mk1"),
    ),
)


def normalize_asset_query(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def slug_asset_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def asset_review_gallery_url(asset_id: str, public_base_url: str | None = None) -> str:
    path = f"/review/assets/{asset_id}"
    if not public_base_url:
        return path
    return f"{public_base_url.rstrip('/')}{path}"


def _known_aliases(asset: ReviewAsset) -> set[str]:
    return {
        normalize_asset_query(asset.asset_id),
        normalize_asset_query(asset.asset_id.replace("_", " ")),
        normalize_asset_query(asset.name),
        *(normalize_asset_query(alias) for alias in asset.aliases),
    }


def _asset_path_for_db_asset(asset: Asset) -> str | None:
    if not asset.file_path:
        return None
    path = Path(asset.file_path)
    if path.is_absolute():
        return asset.file_path
    asset_root = Path(get_settings().asset_root)
    if path.parts[:len(asset_root.parts)] != asset_root.parts:
        path = asset_root / path
    if path.suffix.lower() == ".glb":
        return path.as_posix()
    if path.suffix:
        return path.with_suffix(".glb").as_posix()
    return path.as_posix()


async def list_review_assets(db: AsyncSession | None) -> list[ReviewAsset]:
    assets: dict[str, ReviewAsset] = {asset.asset_id: asset for asset in KNOWN_REVIEW_ASSETS}
    if db is None:
        return sorted(assets.values(), key=lambda asset: asset.name.lower())

    result = await db.execute(select(Asset).where(Asset.status == "available"))
    for row in result.scalars().all():
        asset_path = _asset_path_for_db_asset(row)
        if not asset_path:
            continue
        assets.setdefault(
            row.canonical_id,
            ReviewAsset(
                asset_id=row.canonical_id,
                asset_path=asset_path,
                name=row.name or row.canonical_id,
                aliases=tuple(str(tag) for tag in (row.tags or [])),
            ),
        )
    return sorted(assets.values(), key=lambda asset: asset.name.lower())


async def resolve_review_asset(
    db: AsyncSession,
    *,
    asset_query: str | None = None,
    asset_id: str | None = None,
    asset_path: str | None = None,
) -> ReviewAsset:
    if asset_path and asset_id:
        return ReviewAsset(asset_id=asset_id, asset_path=asset_path, name=asset_id)

    query = asset_query or asset_id or asset_path
    if not query:
        raise HTTPException(status_code=422, detail="Provide asset_name, asset_id, or asset_path")

    normalized = normalize_asset_query(query)
    candidates = await list_review_assets(db)
    exact = [asset for asset in candidates if normalized in _known_aliases(asset)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise HTTPException(
            status_code=409,
            detail={"message": "Asset name is ambiguous", "candidates": [asset.asset_id for asset in exact]},
        )

    fuzzy = [
        asset
        for asset in candidates
        if normalized and any(normalized in alias or alias in normalized for alias in _known_aliases(asset))
    ]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise HTTPException(
            status_code=409,
            detail={"message": "Asset name is ambiguous", "candidates": [asset.asset_id for asset in fuzzy]},
        )

    if asset_path:
        inferred_id = asset_id or slug_asset_id(Path(asset_path).stem)
        return ReviewAsset(asset_id=inferred_id, asset_path=asset_path, name=inferred_id)

    raise HTTPException(
        status_code=404,
        detail={
            "message": "Asset not found",
            "known_assets": [asset.asset_id for asset in candidates],
        },
    )


async def create_asset_review_render_job(
    db: AsyncSession,
    *,
    asset: ReviewAsset,
    views: Iterable[str] = REVIEW_VIEWS,
    quality: str = "preview",
    output_namespace: str | None = None,
    artifact_prefix: str | None = None,
    priority: int = 10,
    preferred_worker_id: str | None = None,
    width: int | None = None,
    height: int | None = None,
    samples: int | None = None,
    output_path: str | None = None,
    require_gpu_cycles: bool = False,
    actor_id: str = "admin",
) -> Job:
    if quality not in RENDER_QUALITIES:
        raise HTTPException(status_code=422, detail="quality must be draft, preview, or final")

    view_list = list(views)
    required_capabilities = ["blender.final_render" if quality == "final" else "blender.preview_render"]
    if require_gpu_cycles:
        required_capabilities.append("gpu.cycles_render")
    resolved_artifact_prefix = artifact_prefix or output_namespace or asset.asset_id
    resolved_output_path = output_path or "{output_root}/oeb-studio-harness/review-renders/{job_id}"
    payload = {
        "job_type": "asset.review_render",
        "asset_path": asset.asset_path,
        "asset_id": asset.asset_id,
        "asset_name": asset.name,
        "views": view_list,
        "quality": quality,
        "output_namespace": output_namespace,
        "artifact_prefix": resolved_artifact_prefix,
        "require_gpu_cycles": require_gpu_cycles,
        "script_file": "{workspace_root}/tools/render_asset_review.py",
        "cwd": "{workspace_root}",
        "output_path": resolved_output_path,
    }
    for key, value in (("width", width), ("height", height), ("samples", samples)):
        if value is not None:
            payload[key] = value

    job = Job(
        title=f"Review render {asset.asset_id}",
        description=f"Render {asset.name} review views from {asset.asset_path}",
        required_capabilities=required_capabilities,
        policy="wait_for_preferred_worker" if preferred_worker_id else "run_anywhere",
        preferred_worker_id=preferred_worker_id,
        priority=priority,
        payload=payload,
        is_idempotent=True,
    )
    db.add(job)
    await db.flush()
    db.add(AuditEvent(
        event_type="job.asset_review_render.created",
        actor_type="user",
        actor_id=actor_id,
        resource_type="job",
        resource_id=str(job.id),
        details={
            "asset_id": asset.asset_id,
            "asset_path": asset.asset_path,
            "views": view_list,
            "quality": quality,
            "require_gpu_cycles": require_gpu_cycles,
        },
    ))
    return job


def view_from_artifact(asset_id: str, artifact: Artifact) -> str | None:
    metadata = artifact.review_metadata or {}
    view = metadata.get("view")
    if view in REVIEW_VIEWS:
        return view

    stem = Path(artifact.filename).stem
    prefix = f"{asset_id}_"
    if stem.startswith(prefix):
        view = stem[len(prefix):]
    else:
        view = stem.rsplit("_", 1)[-1]
    return view if view in REVIEW_VIEWS else None


def image_artifacts_by_view(asset_id: str, artifacts: Iterable[Artifact]) -> dict[str, Artifact]:
    by_view: dict[str, Artifact] = {}
    for artifact in artifacts:
        if not artifact.mime_type or not artifact.mime_type.startswith("image/"):
            continue
        view = view_from_artifact(asset_id, artifact)
        if view:
            by_view[view] = artifact
    return by_view


def missing_uploaded_views(job: Job, artifacts: Iterable[Artifact]) -> list[str]:
    payload = job.payload or {}
    if payload.get("job_type") != "asset.review_render":
        return []
    asset_id = payload.get("asset_id")
    if not asset_id:
        return list(payload.get("views") or REVIEW_VIEWS)
    requested = set(payload.get("views") or REVIEW_VIEWS)
    uploaded = {
        view
        for view, artifact in image_artifacts_by_view(asset_id, artifacts).items()
        if view in requested and artifact.provenance == "uploaded"
    }
    return [view for view in REVIEW_VIEWS if view in requested and view not in uploaded]
