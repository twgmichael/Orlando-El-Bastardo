from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_or_worker
from app.database import get_db
from app.schemas.asset import AssetRead
from app.services.missing_asset_fallback import resolve_missing_asset
from app.services.registry_resolution import is_ambiguous, resolve_reference

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/resolve")
async def resolve(
    q: str = Query(..., min_length=1, description='"Load X" query, e.g. "jb100" or "pirate escape"'),
    kind: str | None = Query(default=None, description='Restrict to one kind, e.g. "scene"'),
    fallback: bool = Query(
        default=False,
        description="If true and nothing matches, run the two-tier missing-asset fallback "
                    "(docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 6/7) instead of 404ing.",
    ),
    db: AsyncSession = Depends(get_db),
    _caller: dict = Depends(require_admin_or_worker),
):
    """Resolve a chat "load X" command against the asset/scene registry.

    Response shape mirrors Studio Chat's existing needs_clarification
    compiler outcome (services/studio_chat.py) rather than inventing a
    new interaction pattern: a single confident match resolves directly;
    multiple close matches come back as `needs_clarification: true` with
    `candidates` for a chooser, each candidate carrying enough to render
    a hero/review-render thumbnail (canonical_id) client-side.

    `fallback=true` is opt-in, not the default -- a plain lookup (e.g.
    the Placeholders review page checking what exists) should never have
    the side effect of registering a new placeholder and filing a
    ticket. Callers that specifically want "never blocks, worst case
    register a draft-tier placeholder" (Studio Chat's live asset-intent
    resolution, Producer) pass it explicitly.
    """
    matches = await resolve_reference(db, q, kind=kind)
    if not matches:
        if not fallback:
            raise HTTPException(status_code=404, detail=f"No registry entry matches {q!r}")
        requested_by = f"registry-api:{_caller.get('type', 'unknown')}"
        outcome = await resolve_missing_asset(db, q, kind or "prop", requested_by=requested_by)
        await db.commit()
        return {
            "needs_clarification": False,
            "resolved": AssetRead.model_validate(outcome.asset),
            "score": 0.0,
            "fallback_tier": outcome.tier,
            "ticket_path": outcome.ticket_path,
        }

    if not is_ambiguous(matches):
        top = matches[0]
        return {
            "needs_clarification": False,
            "resolved": AssetRead.model_validate(top.asset),
            "score": top.score,
        }

    return {
        "needs_clarification": True,
        "clarification_question": f"Multiple matches for {q!r} — which one?",
        "candidates": [
            {"asset": AssetRead.model_validate(m.asset), "score": m.score}
            for m in matches[:8]
        ],
    }
