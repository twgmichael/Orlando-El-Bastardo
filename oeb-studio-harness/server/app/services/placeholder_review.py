"""Tier-2 placeholder review queue.

See docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 7: a
generated placeholder (e.g. a crude cup or block-cluster) is registered
as an Asset row with status "unapproved". A human review resolves it to
one of three outcomes -- "rejected" (discard, regenerate fresh next
time), "draft_fallback" (reusable, permanently non-final), or promoted
to a real Tier-1 asset (status becomes "available", same as any
human-designed Canonical Asset).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset

PLACEHOLDER_STATUSES = ("unapproved", "draft_fallback", "rejected")

# unapproved: pending review, may be rejected/draft_fallback/promoted.
# draft_fallback: reusable stand-in, may still be promoted later.
# rejected: terminal; not offered further decisions.
DECISION_ALLOWED_FROM = {
    "reject": {"unapproved"},
    "draft_fallback": {"unapproved"},
    "promote": {"unapproved", "draft_fallback"},
}
DECISION_TO_STATUS = {
    "reject": "rejected",
    "draft_fallback": "draft_fallback",
    "promote": "available",
}


async def list_placeholder_assets(db: AsyncSession) -> list[Asset]:
    result = await db.execute(
        select(Asset)
        .where(Asset.status.in_(PLACEHOLDER_STATUSES))
        .order_by(Asset.status, Asset.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_placeholder_asset(db: AsyncSession, canonical_id: str) -> Asset | None:
    result = await db.execute(select(Asset).where(Asset.canonical_id == canonical_id))
    asset = result.scalar_one_or_none()
    if asset is None or asset.status not in PLACEHOLDER_STATUSES:
        return None
    return asset


def apply_decision(asset: Asset, decision: str) -> None:
    """Mutate *asset* in place per *decision*. Raises ValueError if the
    decision isn't valid from the asset's current status.
    """
    if decision not in DECISION_TO_STATUS:
        raise ValueError(f"Unknown decision: {decision!r}")
    if asset.status not in DECISION_ALLOWED_FROM[decision]:
        raise ValueError(
            f"Cannot apply decision {decision!r} to a placeholder in status {asset.status!r}"
        )
    asset.status = DECISION_TO_STATUS[decision]
    asset.updated_at = datetime.now(timezone.utc)
    if decision == "promote":
        provenance = dict(asset.provenance or {})
        provenance["promoted_from"] = "tier2_placeholder"
        asset.provenance = provenance
