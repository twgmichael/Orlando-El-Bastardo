"""Two-tier missing-asset fallback: tier-1 real-asset stand-in, tier-2
crude primitive placeholder. docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md
section 7.

Tier 1 reuses two things that already exist rather than inventing a
third: `data/standins.json`'s screenplay-vocabulary normalization (cast/
location_standins), and this session's own registry_resolution.py
tag/keyword matching (section 6) to turn a normalized stand-in tag into
a real registered Asset.

Tier 2, when nothing in tier 1 matches, registers a new Asset row with
status="unapproved" (review_placeholders.html's review queue), files a
NEEDED ticket in the same `tools/tickets.py` .json+.md format/directory
convention (adapted from scene-level to single-asset-level), and links
the two bidirectionally so neither is ever orphaned -- ticket carries
the registered canonical_id, the Asset's `asset_metadata.needed_ticket`
carries the ticket path.

What this does NOT do: actually execute the tier-2 placeholder's
Blueprint through Blender. It constructs a minimal, deliberately crude
default Blueprint (per section 4/7's guardrail -- never a freehand
"finished-looking" design) and stores it in
`asset_metadata.placeholder_blueprint`, ready to submit as a real build
job via the existing tools/blueprint_interpreter.py /
tools/submit_blueprint_job.py machinery. Actually submitting and running
that job needs a live harness Job row and worker, which this pure
service function doesn't orchestrate -- that's the caller's job (e.g.
Producer, per section 4/5, or a human via Studio Chat).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.asset import Asset
from app.services.registry_resolution import is_ambiguous, resolve_reference

def _data_root() -> Path:
    """Resolved from Settings.data_root (OEB_DATA_ROOT), not a fixed
    __file__ ancestor count: this module ships inside
    oeb-studio-harness/server, which is bind-mounted into the local
    Docker stack at a shallower path (/app) than its host checkout, so
    a fixed parents[N] index is correct on the host and wrong in the
    container -- same reasoning as Settings.oeb_config_path/asset_root.
    """
    return Path(get_settings().data_root).resolve()


def _tickets_root() -> Path:
    return Path(get_settings().tickets_root).resolve()

# Deliberately crude, kind-agnostic default geometry -- section 7's own
# "cup -> small cylinder with a handle" example generalizes to: one
# primary primitive sized plausibly for the kind, nothing more. This is
# not meant to look finished; see section 4's guardrail.
_DEFAULT_PRIMITIVE_BY_KIND = {
    "prop": {"type": "cylinder", "transform": {"location": [0, 0, 0.25], "scale": [0.2, 0.2, 0.5]}},
    "character": {"type": "cylinder", "transform": {"location": [0, 0, 0.9], "scale": [0.25, 0.25, 1.8]}},
    "vehicle": {"type": "cube", "transform": {"location": [0, 0, 0.5], "scale": [1.5, 0.8, 0.8]}},
    "set": {"type": "cube", "transform": {"location": [0, 0, 0.1], "scale": [3.0, 3.0, 0.1]}},
    "scene": {"type": "cube", "transform": {"location": [0, 0, 0.1], "scale": [3.0, 3.0, 0.1]}},
}
_DEFAULT_PRIMITIVE_FALLBACK = {"type": "cube", "transform": {"location": [0, 0, 0.5], "scale": [0.5, 0.5, 0.5]}}


@dataclass
class FallbackOutcome:
    tier: int  # 1 or 2
    asset: Asset
    ticket_path: str | None = None
    created: bool = False


def load_standins(path: Path | None = None) -> dict:
    standins_path = path or (_data_root() / "standins.json")
    if not standins_path.is_file():
        return {}
    return json.loads(standins_path.read_text())


def normalize_via_standins(query: str, standins: dict) -> str | None:
    """Look `query` up in standins.json's cast/location_standins maps
    (case/whitespace-insensitive on the key) and return the normalized
    stand-in tag, or None if nothing matches.
    """
    key = re.sub(r"[^a-z0-9]+", "_", query.strip().lower()).strip("_")
    for section in ("location_standins", "cast"):
        table = standins.get(section) or {}
        if key in table:
            return table[key]
    return None


def slugify_placeholder_id(query: str, kind: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", query.strip().lower()).strip("_")
    return f"placeholder_{kind}_{slug}_A"


def default_placeholder_blueprint(canonical_id: str, kind: str, name: str) -> dict:
    primitive = dict(_DEFAULT_PRIMITIVE_BY_KIND.get(kind, _DEFAULT_PRIMITIVE_FALLBACK))
    primitive["id"] = "body"
    return {
        "schema_version": "0.1.0",
        "canonical_id": canonical_id,
        "name": name,
        "kind": kind,
        "units_per_meter": 1.0,
        "primitives": [primitive],
        "operations": [],
    }


def build_needed_ticket(canonical_id: str, query: str, kind: str, requested_by: str | None) -> dict:
    """Same shape/fields as tools/tickets.py's write_ticket(), adapted
    from scene-level ("this scene needs these N things") to single
    asset-level ("this one asset was not found") -- same `ticket`/
    `status`/`created`/`next_step` fields, `missing` narrowed to one
    entry so both remain visually/structurally the same ticket family.
    """
    return {
        "ticket": f"NEEDED-{canonical_id}",
        "status": "NEEDS_ASSET",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_by": requested_by,
        "missing": [{
            "kind": kind,
            "name": query,
            "source": "missing_asset_fallback tier-2",
            "detail": f"No approved or stand-in asset found for {query!r}; "
                      f"a draft-tier primitive placeholder was registered as {canonical_id!r}.",
        }],
        "placeholder_canonical_id": canonical_id,
        "next_step": "Source or build a real asset for this reference, then either "
                     "promote the placeholder (if simple enough) or replace it and "
                     "reject the placeholder via the Placeholders review queue.",
    }


def write_needed_ticket(ticket: dict, tickets_root: Path | None = None) -> str:
    root = tickets_root or _tickets_root()
    root.mkdir(parents=True, exist_ok=True)
    canonical_id = ticket["placeholder_canonical_id"]
    json_path = root / f"NEEDED-{canonical_id}.json"
    json_path.write_text(json.dumps(ticket, indent=2) + "\n")

    md_lines = [
        f"# NEEDED — {canonical_id}", "",
        "This asset is a draft-tier placeholder pending review. The library "
        "did not have anything close to:", "",
    ]
    for m in ticket["missing"]:
        md_lines.append(f"- **{m['kind']}**: `{m['name']}`  ({m['source']})")
    md_lines += ["", f"Details: `{json_path.name}` alongside this file.",
                 "Review the placeholder in Studio Harness under Placeholders, then "
                 "source/build the real asset.", ""]
    (root / f"NEEDED-{canonical_id}.md").write_text("\n".join(md_lines))
    return str(json_path)


def resolve_needed_ticket(ticket_path: str) -> None:
    """Section 7 item 5: promoting a placeholder to Tier 1 is "the one
    path that resolves the NEEDED ticket, since the real need is now
    actually satisfied" -- reject/draft_fallback deliberately leave the
    ticket open (a rejected placeholder needs a fresh one next time; a
    draft fallback is reusable but still not the real asset). Missing
    or already-resolved ticket files are a no-op, not an error -- a
    placeholder can be promoted without a linked ticket (e.g. one
    registered by hand) and this must not block that.
    """
    path = Path(ticket_path)
    if not path.is_file():
        return
    ticket = json.loads(path.read_text())
    if ticket.get("status") == "RESOLVED":
        return
    ticket["status"] = "RESOLVED"
    ticket["resolved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ticket["resolution"] = "promoted_to_tier1"
    path.write_text(json.dumps(ticket, indent=2) + "\n")

    md_path = path.with_suffix(".md")
    if md_path.is_file():
        canonical_id = ticket.get("placeholder_canonical_id", "")
        md_path.write_text(
            md_path.read_text()
            + f"\n---\n\n**RESOLVED** — `{canonical_id}` was promoted to a Tier 1 "
              f"Canonical Asset at {ticket['resolved_at']}. The real need is satisfied.\n",
        )


async def resolve_missing_asset(
    db: AsyncSession,
    query: str,
    kind: str,
    *,
    requested_by: str | None = None,
    standins: dict | None = None,
) -> FallbackOutcome:
    standins = standins if standins is not None else load_standins()

    # Tier 1a: standins.json normalization, then registry lookup.
    standin_tag = normalize_via_standins(query, standins)
    if standin_tag:
        matches = await resolve_reference(db, standin_tag, kind=kind)
        if matches and not is_ambiguous(matches):
            return FallbackOutcome(tier=1, asset=matches[0].asset)

    # Tier 1b: direct registry lookup (query itself matches a real asset's
    # tags/canonical_id/name -- no stand-in normalization needed).
    matches = await resolve_reference(db, query, kind=kind)
    if matches and not is_ambiguous(matches):
        return FallbackOutcome(tier=1, asset=matches[0].asset)

    # Tier 2: nothing close enough exists. Register an unapproved
    # placeholder, ticketed and bidirectionally linked, never orphaned.
    canonical_id = slugify_placeholder_id(query, kind)
    ticket = build_needed_ticket(canonical_id, query, kind, requested_by)
    ticket_path = write_needed_ticket(ticket)

    blueprint = default_placeholder_blueprint(canonical_id, kind, name=query)
    asset = Asset(
        canonical_id=canonical_id,
        name=query,
        kind=kind,
        status="unapproved",
        tags=[query],
        provenance={"source": "missing_asset_fallback", "tier": 2},
        asset_metadata={
            "placeholder": True,
            "source_query": query,
            "needed_ticket": ticket_path,
            "placeholder_blueprint": blueprint,
        },
    )
    db.add(asset)
    await db.flush()
    return FallbackOutcome(tier=2, asset=asset, ticket_path=ticket_path, created=True)
