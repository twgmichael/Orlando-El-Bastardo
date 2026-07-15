import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, require_admin_or_worker
from app.config import get_settings
from app.database import get_db
from app.models.asset import Asset
from app.models.audit import AuditEvent
from app.schemas.asset import AssetCreate, AssetRead, AssetSeedResponse, AssetUpdate

router = APIRouter(prefix="/assets", tags=["assets"])

ASSET_KINDS = {
    "character",
    "set",
    "prop",
    "ship",
    "animation",
    "skeleton",
    "material",
    "camera_rig",
    "lighting_rig",
    "location",
}
ASSET_STATUSES = {"available", "wip", "needed", "missing"}


def _validate_kind(kind: str) -> None:
    if kind not in ASSET_KINDS:
        raise HTTPException(status_code=422, detail=f"Invalid asset kind: {kind}")


def _validate_status(asset_status: str) -> None:
    if asset_status not in ASSET_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid asset status: {asset_status}")


def _asset_kwargs(body: AssetCreate | AssetUpdate) -> dict:
    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] is not None:
        _validate_kind(data["kind"])
    if "status" in data and data["status"] is not None:
        _validate_status(data["status"])
    if "metadata" in data:
        data["asset_metadata"] = data.pop("metadata")
    return data


async def _get_asset(db: AsyncSession, canonical_id: str) -> Asset:
    result = await db.execute(select(Asset).where(Asset.canonical_id == canonical_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("", response_model=list[AssetRead])
async def list_assets(
    kind: str | None = None,
    asset_status: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    query = select(Asset)
    if kind:
        _validate_kind(kind)
        query = query.where(Asset.kind == kind)
    if asset_status:
        _validate_status(asset_status)
        query = query.where(Asset.status == asset_status)
    if q:
        query = query.where(Asset.canonical_id.startswith(q))
    query = query.order_by(Asset.kind, Asset.canonical_id)
    result = await db.execute(query)
    return [AssetRead.model_validate(asset) for asset in result.scalars().all()]


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_asset(body: AssetCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Asset).where(Asset.canonical_id == body.canonical_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Asset already exists")

    asset = Asset(**_asset_kwargs(body))
    db.add(asset)
    db.add(AuditEvent(
        event_type="asset.created",
        actor_type="user",
        actor_id="admin",
        resource_type="asset",
        resource_id=asset.canonical_id,
        details={"kind": asset.kind},
    ))
    await db.commit()
    await db.refresh(asset)
    return AssetRead.model_validate(asset)


@router.post("/seed", response_model=AssetSeedResponse, dependencies=[Depends(require_admin)])
async def seed_assets(force: bool = False, db: AsyncSession = Depends(get_db)):
    config_path = Path(get_settings().oeb_config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid config JSON: {exc}") from exc

    assets = config.get("assets")
    if not isinstance(assets, dict):
        raise HTTPException(status_code=422, detail="Config does not contain an assets map")

    created = 0
    skipped = 0
    errors: list[str] = []
    seeded_at = datetime.now(timezone.utc).isoformat()

    for canonical_id, entry in assets.items():
        if not isinstance(entry, dict):
            errors.append(f"{canonical_id}: asset entry must be an object")
            continue

        kind = entry.get("kind")
        if kind not in ASSET_KINDS:
            errors.append(f"{canonical_id}: invalid kind {kind!r}")
            continue

        file_path = entry.get("file")
        payload = {
            "canonical_id": canonical_id,
            "name": canonical_id,
            "kind": kind,
            "file_path": file_path,
            "node_name": entry.get("node"),
            "format": Path(file_path).suffix.removeprefix(".").lower() if file_path else None,
            "status": "available",
            "provenance": {"source": "oeb.config.json", "seeded_at": seeded_at},
            "tags": [],
            "asset_metadata": {},
        }

        result = await db.execute(select(Asset).where(Asset.canonical_id == canonical_id))
        existing = result.scalar_one_or_none()
        if existing:
            if not force:
                skipped += 1
                continue
            for key, value in payload.items():
                if key != "canonical_id":
                    setattr(existing, key, value)
            existing.updated_at = datetime.now(timezone.utc)
            continue

        db.add(Asset(**payload))
        created += 1

    db.add(AuditEvent(
        event_type="asset.seeded",
        actor_type="user",
        actor_id="admin",
        resource_type="asset",
        resource_id="oeb.config.json",
        details={"created": created, "skipped": skipped, "errors": errors, "force": force},
    ))
    await db.commit()
    return AssetSeedResponse(created=created, skipped=skipped, errors=errors)


@router.get("/{canonical_id}", response_model=AssetRead)
async def get_asset(
    canonical_id: str,
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    return AssetRead.model_validate(await _get_asset(db, canonical_id))


@router.put("/{canonical_id}", response_model=AssetRead, dependencies=[Depends(require_admin)])
async def update_asset(canonical_id: str, body: AssetCreate, db: AsyncSession = Depends(get_db)):
    if body.canonical_id != canonical_id:
        raise HTTPException(status_code=409, detail="Body canonical_id must match path")

    asset = await _get_asset(db, canonical_id)
    for key, value in _asset_kwargs(body).items():
        setattr(asset, key, value)
    asset.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(asset)
    return AssetRead.model_validate(asset)


@router.patch("/{canonical_id}", response_model=AssetRead, dependencies=[Depends(require_admin)])
async def patch_asset(canonical_id: str, body: AssetUpdate, db: AsyncSession = Depends(get_db)):
    asset = await _get_asset(db, canonical_id)
    data = _asset_kwargs(body)
    if "canonical_id" in data and data["canonical_id"] != canonical_id:
        existing = await db.execute(select(Asset).where(Asset.canonical_id == data["canonical_id"]))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Asset already exists")
    for key, value in data.items():
        setattr(asset, key, value)
    asset.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(asset)
    return AssetRead.model_validate(asset)


@router.delete("/{canonical_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
async def delete_asset(canonical_id: str, db: AsyncSession = Depends(get_db)):
    asset = await _get_asset(db, canonical_id)
    await db.delete(asset)
    db.add(AuditEvent(
        event_type="asset.deleted",
        actor_type="user",
        actor_id="admin",
        resource_type="asset",
        resource_id=canonical_id,
    ))
    await db.commit()
