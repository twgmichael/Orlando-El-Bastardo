"""Set Designer kitbash-tier review queue (docs/planning/
PRODUCTION-DESIGNER-PLAN.md, "Build order" step 5/"Assignment
interface" kitbash tier): a real, human-approved set assembled from
approved library kit pieces (tools/build_set.py) is registered as an
Asset row with status "kitbash_pending" once its turntable review
renders exist. A human decides here -- "reject" (discard, the designer
tries again) or "approve" (dispatches a kitbash.register job that
writes the real oeb.config.json/data/resolver_map.json entry a worker
can reach; resolve_intent.py/producer.py only ever read those file
registries, never this harness DB, so approval must propagate out, not
just flip a status bit here).

Deliberately reuses the SAME Asset table + AuditEvent pattern as
app/services/placeholder_review.py's tier-2 placeholder queue (see that
module's docstring) -- a different review question (is this a good
kitbashed set? vs. does this placeholder ever get promoted?), same
generic "assets row + status state machine + audit trail" mechanism,
no new table needed.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.audit import AuditEvent
from app.models.job import Job

KITBASH_STATUSES = ("kitbash_pending", "kitbash_rejected")

# kitbash_pending: pending review, may be rejected or approved.
# kitbash_rejected: terminal for this build; resubmitting (a fresh
#   build job) creates/updates the same Asset row back to kitbash_pending.
DECISION_ALLOWED_FROM = {
    "reject": {"kitbash_pending"},
    "approve": {"kitbash_pending"},
}
DECISION_TO_STATUS = {
    "reject": "kitbash_rejected",
    "approve": "kitbash_pending",  # stays pending until registration completes; see apply_decision
}


async def list_kitbash_sets(db: AsyncSession) -> list[Asset]:
    result = await db.execute(
        select(Asset)
        .where(Asset.kind == "set", Asset.status.in_(KITBASH_STATUSES))
        .order_by(Asset.status, Asset.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_kitbash_set(db: AsyncSession, canonical_id: str) -> Asset | None:
    result = await db.execute(select(Asset).where(Asset.canonical_id == canonical_id))
    asset = result.scalar_one_or_none()
    if asset is None or asset.kind != "set" or asset.status not in KITBASH_STATUSES:
        return None
    return asset


def apply_decision(asset: Asset, decision: str) -> None:
    """Mutate *asset* in place per *decision*. Raises ValueError if the
    decision isn't valid from the asset's current status. "approve"
    does NOT flip status to "available" here -- that column change is
    supposed to be earned only by kitbash.register actually writing the
    file registry on a worker; see mark_registered() below, called from
    the job-completion path once that real work is confirmed done.
    """
    if decision not in DECISION_TO_STATUS:
        raise ValueError(f"Unknown decision: {decision!r}")
    if asset.status not in DECISION_ALLOWED_FROM[decision]:
        raise ValueError(
            f"Cannot apply decision {decision!r} to a kitbash set in status {asset.status!r}"
        )
    if decision == "reject":
        asset.status = DECISION_TO_STATUS[decision]
        asset.updated_at = datetime.now(timezone.utc)


def mark_approval_dispatched(asset: Asset, register_job_id: str) -> None:
    """Record that a kitbash.register job was enqueued for *asset*
    without changing its status yet -- "available" is set by
    mark_registered() once that job actually completes, so a failed or
    still-running registration never silently reads as approved.
    """
    metadata = dict(asset.asset_metadata or {})
    metadata["register_job_id"] = register_job_id
    asset.asset_metadata = metadata
    asset.updated_at = datetime.now(timezone.utc)


async def create_kitbash_register_job(db: AsyncSession, asset: Asset, *, actor_id: str) -> Job:
    """Enqueued on "approve" -- writes the real oeb.config.json/
    data/resolver_map.json entry a worker's checkout can reach.
    tools/register_kitbash_set.py is stdlib-only (no bpy needed, same
    as tools/set_designer.py) but still runs through the *existing*
    BlenderCLIAdapter's script_file mode -- no new adapter, per the
    2026-08-10 decision to extend the existing worker system.
    """
    metadata = asset.asset_metadata or {}
    payload = {
        "job_type": "kitbash.register",
        "canonical_id": asset.canonical_id,
        "script_file": "{workspace_root}/tools/register_kitbash_set.py",
        "cwd": "{workspace_root}",
        "script_args": [
            "--canonical-id", asset.canonical_id,
            "--glb-path", asset.file_path or "",
            "--spec-path", metadata.get("spec_path") or "",
        ] + (["--location-tag", metadata["location_tag"]] if metadata.get("location_tag") else []),
    }
    job = Job(
        title=f"Register kitbash set {asset.canonical_id}",
        description=f"Write the approved set {asset.canonical_id} into the file registry",
        required_capabilities=["blender.command_line"],
        policy="run_anywhere",
        priority=5,
        payload=payload,
        is_idempotent=True,
    )
    db.add(job)
    await db.flush()
    db.add(AuditEvent(
        event_type="job.kitbash_register.created",
        actor_type="user",
        actor_id=actor_id,
        resource_type="job",
        resource_id=str(job.id),
        details={"canonical_id": asset.canonical_id},
    ))
    return job


def mark_registered(asset: Asset, *, location_tag: str | None) -> None:
    """Called once a kitbash.register job completes successfully: the
    file registry now really has this set, so the harness's own record
    can finally say "available" too.
    """
    asset.status = "available"
    asset.updated_at = datetime.now(timezone.utc)
    provenance = dict(asset.provenance or {})
    provenance["promoted_from"] = "kitbash_review"
    if location_tag:
        provenance["location_tag"] = location_tag
    asset.provenance = provenance
