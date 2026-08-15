#!/usr/bin/env python3
"""casting_director.py -- the casting role
(docs/planning/CASTING-DIRECTOR-PLAN.md), relocated out of
tools/producer.py's --primitive-fallback per the 2026-08-10 discovery
there: Producer had accreted this role's job (resolve a speaking
character's placeholder casting) directly into its own per-scene loop,
same shape of finding as Set Designer/Director before it.
`primitive_fallback()`'s `role`/`role_location` loops are gone from
producer.py; this is what resolves them now.

Runs as a job on the existing worker-agent job queue
(docs/planning/WORKER-AGENT-PLAN.md), via the *existing*
BlenderCLIAdapter's `script_file` payload mode -- no new adapter.
Deliberately stdlib-only, matching tools/set_designer.py's own
convention, so it runs identically under Blender's bundled Python
(worker dispatch) or the project's own .venv (direct CLI use/testing).

**Real ordering dependency, not just a missing role** (the plan doc's
own discovery): registering a role needs the scene's location already
resolved (to anchor a spawn_mark against). A casting job for a scene
whose location is *also* unmapped is enqueued with `depends_on_job_id`
set to that location job's id (docs/planning/CASTING-DIRECTOR-PLAN.md
Open Question #1) -- the harness never offers this job to a worker
until the location job's status is "completed", and cascade-fails this
job if the location job fails outright. By the time this script
actually runs, *location_tag* is guaranteed to be resolvable -- but
not necessarily as a direct data/resolver_map.json locations[] key: a
tier-1 stand-in match (tools/set_designer.py's resolve_location())
never adds one under the raw scripted tag, only a
data/standins.json location_standins[] mapping to the real set's key.
resolve_role() below resolves through that mapping the same way
set_designer.py's own tier-1 check does, before the direct-match
fallback (fixed 2026-08-12: the first live re-triage run found this
unresolved -- every stand-in-location scene retried forever with
"location ... is not resolved yet").

**Classification is a pure per-name keyword check, no whole-episode
tally needed** (decision 2026-08-10: recurrence never auto-promotes a
background role to principal -- that needs human approval, a mechanism
not designed yet -- so the whole-episode scene-count tally the plan
doc originally sketched for that purpose isn't needed for
classification itself). A name matching FUNCTIONAL_LABEL_KEYWORDS is
background; everything else is principal.

**Visual identity is not a design goal** (user, 2026-08-10: "we had
success using oblongs in place of characters, it's 3D animation not
rocket surgery"). Principal vs. background is about *registration*,
not looks: every background name shares BACKGROUND_CHARACTER_ID (one
placeholder asset, built once, never rebuilt per name) so a real
character build can later replace an individual principal role without
touching any other -- background roles are never individually
replaceable, by design. Each background name still gets its own
role_tag/spawn_mark, though: sharing the asset is not the same as
sharing a position, and two background characters can appear in the
same scene at once.

CLI:
  .venv/bin/python tools/casting_director.py \\
      --speaker-name "marqui" --location-tag journeyblaster_cockpit \\
      --script scripts/pilot/pilot.md --episode pilot --scene-number 5
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placeholder_blueprint  # noqa: E402
import llm_asset_match  # noqa: E402

CONFIG_PATH = "oeb.config.json"
RESOLVER_MAP_PATH = "data/resolver_map.json"
STANDINS_PATH = "data/standins.json"
PLACEHOLDER_ASSETS_ROOT = "assets/placeholders"
VENV_PY = ".venv/bin/python"

# The one shared background placeholder character -- built once,
# reused by every background name episode-wide. See module docstring.
BACKGROUND_CHARACTER_ID = "placeholder_character_background_A"

# A lookup vocabulary, not free classification -- verified against
# every real blocked-role name from the 81-scene pilot triage (15/15
# real functional labels match, 0/8 real proper names false-positive).
# Extend only when real evidence demands it, same discipline as
# tools/index_assets.py's TAG_VOCABULARY /
# tools/placeholder_blueprint.py's VAST_SCALE_KEYWORDS.
FUNCTIONAL_LABEL_KEYWORDS = (
    # generic job/occupational titles
    "guard", "officer", "technician", "official", "secretary",
    "pilot", "waiter", "waitress", "clerk", "attendant", "operator",
    "dispatcher", "receptionist", "steward", "medic", "engineer",
    "mechanic", "crewman", "soldier", "trooper", "marine", "worker",
    "staff",
    # system/comms voices
    "announcer", "controller", "control", "voice", "computer",
    # ordinal/numbered generic labels -- almost always background/extras
    "first", "second", "third", "fourth", "fifth",
)


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _write_json(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def classify_cast(speaker_name: str) -> str:
    """"principal" or "background" -- a pure per-name keyword check,
    see module docstring for why no episode-wide tally is needed.
    """
    lname = speaker_name.strip().lower()
    if any(kw in lname for kw in FUNCTIONAL_LABEL_KEYWORDS):
        return "background"
    return "principal"


def _role_tag_for(speaker_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", speaker_name.strip().lower()).strip("_") or "actor"


def ensure_background_character(
    config_path: str = CONFIG_PATH,
    placeholder_assets_root: str = PLACEHOLDER_ASSETS_ROOT,
) -> None:
    """Build the one shared background placeholder MESH, if it doesn't
    already exist on disk/in the registry. Idempotent -- safe to call
    once per background name resolved, only ever builds once.

    This registers BACKGROUND_CHARACTER_ID itself as the underlying
    built asset -- but per-role casting now registers its OWN
    character_id against this same file/node (see
    ensure_background_role_asset()) rather than using
    BACKGROUND_CHARACTER_ID directly as a role's character_id.
    """
    config = _load_json(config_path)
    if BACKGROUND_CHARACTER_ID in config.get("assets", {}):
        return
    bp = placeholder_blueprint.default_placeholder_blueprint(
        BACKGROUND_CHARACTER_ID, "character", "Background")
    placeholder_blueprint.build_placeholder_glb(
        bp, f"{placeholder_assets_root}/{BACKGROUND_CHARACTER_ID}.glb",
        f"out/blueprint_builds/{BACKGROUND_CHARACTER_ID}.blend",
        f"out/blueprint_builds/{BACKGROUND_CHARACTER_ID}.manifest.json")
    placeholder_blueprint.register_placeholder_asset(
        config_path, BACKGROUND_CHARACTER_ID, "character",
        f"placeholders/{BACKGROUND_CHARACTER_ID}.glb", source="casting_director")


def _is_background_character_id(character_id: str) -> bool:
    return character_id == BACKGROUND_CHARACTER_ID \
        or character_id.startswith(BACKGROUND_CHARACTER_ID + "__")


def ensure_background_role_asset(
    role_tag: str,
    config_path: str = CONFIG_PATH,
    placeholder_assets_root: str = PLACEHOLDER_ASSETS_ROOT,
) -> str:
    """Register (idempotently) a background role's OWN character_id,
    pointing at the one shared built mesh -- fixed 2026-08-13:
    tools/resolve_intent.py's R3 rule rejects two actors in the same
    scene resolving to the identical character_id (E_DUPLICATE_CHARACTER),
    which every background role sharing the literal
    BACKGROUND_CHARACTER_ID always eventually triggered once a scene
    had two or more background speakers (e.g. 'first_guard' and
    'second_guard' both present). The plan doc's own intent was never
    to collapse every background role into one interchangeable
    identity -- "sharing the asset is not the same as sharing a
    position, and two background characters can appear in the same
    scene at once" -- just to avoid rebuilding a mesh per name. So:
    one build (ensure_background_character(), unchanged, zero extra
    Blender cost), one registry entry per role_tag, same underlying
    file+node.

    Returns the per-role character_id to use for this role.
    """
    ensure_background_character(config_path, placeholder_assets_root)
    per_role_id = f"{BACKGROUND_CHARACTER_ID}__{role_tag}"
    config = _load_json(config_path)
    if per_role_id not in config.get("assets", {}):
        placeholder_blueprint.register_placeholder_asset(
            config_path, per_role_id, "character",
            f"placeholders/{BACKGROUND_CHARACTER_ID}.glb",
            source="casting_director", node=BACKGROUND_CHARACTER_ID)
    return per_role_id


def resolve_role(
    speaker_name: str,
    location_tag: str,
    *,
    scene_evidence: str | None = None,
    config_path: str = CONFIG_PATH,
    resolver_map_path: str = RESOLVER_MAP_PATH,
    standins_path: str = STANDINS_PATH,
    placeholder_assets_root: str = PLACEHOLDER_ASSETS_ROOT,
) -> dict:
    """Resolve *speaker_name* -- a raw dialogue-cue name Producer's
    vocabulary sweep found with no cast mapping, OR an already-cast
    name with no spawn_mark for *location_tag* yet (the old
    "role_location" case) -- handled by the same path here, since
    register_placeholder_role() already merges a new location's
    spawn_mark into an existing role rather than overwriting it.
    *location_tag* must already be a real resolver_map.json
    locations[] entry (guaranteed by the depends_on_job_id dependency
    this job was enqueued with, see module docstring).

    *scene_evidence* (docs/planning/LLM-ASSET-MATCHING-PLAN.md) is the
    scene's own dialogue/action text -- when given and the exact-match
    "already cast" lookup misses, grounds two LLM-assisted checks
    before falling to brand-new placeholder registration: is
    *speaker_name* actually an alias/nickname of someone already cast
    this episode, and (for a genuinely new principal) does it match a
    real, already-built character asset. Optional so every existing
    caller degrades to the original exact-match-or-build behavior
    unchanged.

    Returns {"tier": "principal"|"background"|None, "role_tag": str|None,
    "error": str|None}.
    """
    rmap = _load_json(resolver_map_path)
    standins = _load_json(standins_path)

    # *location_tag* is the raw scripted tag Producer passes through
    # unchanged -- same tag tools/set_designer.py's resolve_location()
    # receives. A tier-1 stand-in match (the common case) never gets
    # its own resolver_map.json locations[] entry under that raw tag --
    # only data/standins.json's location_standins[] records the
    # mapping to the real set's key (see resolve_location()'s tier-1
    # comment). register_placeholder_role() needs an actual
    # locations[] key (its own docstring: keyed by "the resolver_map.
    # json locations key"), so resolve through the same stand-in
    # mapping set_designer.py's tier-1 check uses before falling back
    # to a direct-match lookup.
    standin = standins.get("location_standins", {}).get(location_tag)
    if standin and standin in rmap.get("locations", {}):
        resolved_location_tag = standin
    else:
        resolved_location_tag = location_tag
    loc_entry = rmap.get("locations", {}).get(resolved_location_tag)
    if loc_entry is None:
        return {"tier": None, "role_tag": None,
                "error": f"location '{location_tag}' is not resolved yet"}
    location_set_id = loc_entry.get("set_id")

    lname = speaker_name.strip().lower()
    existing_role_tag = standins.get("cast", {}).get(lname)

    # Tier 1.5a (docs/planning/LLM-ASSET-MATCHING-PLAN.md): is this
    # actually an alias/nickname of someone already cast this episode
    # ("Cap"/"the captain"/"Captain Reyes"), rather than a genuinely
    # new speaker? Only checked against THIS episode's own cast (not
    # the whole library) -- cross-episode aliasing isn't a real risk
    # worth the candidate-set noise. A confirmed match is persisted as
    # a new cast[] entry so the next occurrence hits tier-1 directly.
    #
    # Guarded to principal-shaped names on BOTH sides (fixed
    # 2026-08-14, found live): classify_cast() already reliably tells
    # a specific name apart from a generic functional label
    # (FUNCTIONAL_LABEL_KEYWORDS) -- aliasing a generic label ("voice")
    # to an unrelated specific named principal ("casey") is never
    # correct, but the model did exactly that once, unguarded,
    # reintroducing E_DUPLICATE_CHARACTER through a brand-new path the
    # very first time this ran live. Never offer or accept a
    # background-tier name on either side of an alias match.
    if not existing_role_tag and scene_evidence and classify_cast(speaker_name) == "principal":
        already_cast = standins.get("cast", {})
        alias_candidates = [
            {"id": name, "display_name": name, "description": f"already cast as role '{tag}'"}
            for name, tag in already_cast.items()
            if not _is_background_character_id(
                rmap.get("roles", {}).get(tag, {}).get("character_id", ""))
        ]
        if alias_candidates:
            alias_result = llm_asset_match.match_existing_asset(
                speaker_name, scene_evidence, alias_candidates, "character")
            if alias_result["matched_id"] and llm_asset_match.grounded(
                    alias_result["evidence"], scene_evidence):
                existing_role_tag = already_cast[alias_result["matched_id"]]
                standins.setdefault("cast", {})[lname] = existing_role_tag
                _write_json(standins_path, standins)

    try:
        if existing_role_tag:
            # Already cast, already has a built asset -- just extend
            # the existing role with a spawn_mark for this new
            # location. No rebuild, no reclassification.
            role_entry = rmap.get("roles", {}).get(existing_role_tag, {})
            character_id = role_entry.get("character_id")
            if not character_id:
                return {"tier": None, "role_tag": None,
                        "error": f"role '{existing_role_tag}' has no character_id registered"}
            placeholder_blueprint.register_placeholder_role(
                resolver_map_path, existing_role_tag, character_id, resolved_location_tag, location_set_id)
            tier = "background" if _is_background_character_id(character_id) else "principal"
            return {"tier": tier, "role_tag": existing_role_tag, "error": None}

        tier = classify_cast(speaker_name)
        role_tag = _role_tag_for(speaker_name)
        if tier == "background":
            character_id = ensure_background_role_asset(role_tag, config_path, placeholder_assets_root)
        else:
            # Tier 1.5b (docs/planning/LLM-ASSET-MATCHING-PLAN.md): a
            # genuinely new principal -- but does the name match a
            # real, already-built character asset (e.g. a hand-built
            # hero) before spending a Blender build on yet another
            # crude cylinder? Skipped cleanly if there's nothing real
            # to check against, or no scene_evidence was given.
            character_id = None
            if scene_evidence:
                config = _load_json(config_path)
                real_characters = [
                    {"id": cid, "display_name": cid, "description": ""}
                    for cid, a in config.get("assets", {}).items()
                    if a.get("kind") == "character" and not a.get("placeholder")
                ]
                if real_characters:
                    match_result = llm_asset_match.match_existing_asset(
                        speaker_name, scene_evidence, real_characters, "character")
                    if match_result["matched_id"] and llm_asset_match.grounded(
                            match_result["evidence"], scene_evidence):
                        character_id = match_result["matched_id"]

            if character_id is None:
                canonical_id = placeholder_blueprint.slugify_placeholder_id(speaker_name, "character")
                bp = placeholder_blueprint.default_placeholder_blueprint(
                    canonical_id, "character", speaker_name)
                placeholder_blueprint.build_placeholder_glb(
                    bp, f"{placeholder_assets_root}/{canonical_id}.glb",
                    f"out/blueprint_builds/{canonical_id}.blend",
                    f"out/blueprint_builds/{canonical_id}.manifest.json")
                placeholder_blueprint.register_placeholder_asset(
                    config_path, canonical_id, "character", f"placeholders/{canonical_id}.glb",
                    source="casting_director")
                character_id = canonical_id

        placeholder_blueprint.register_placeholder_role(
            resolver_map_path, role_tag, character_id, resolved_location_tag, location_set_id)
        placeholder_blueprint.register_placeholder_cast(standins_path, lname, role_tag)
    except Exception as exc:  # noqa: BLE001 -- must not crash the job
        return {"tier": None, "role_tag": None, "error": str(exc)}

    return {"tier": tier, "role_tag": role_tag, "error": None}


def trigger_continuation(script: str, episode: str, scene_number: int, *, extra_args: list[str] | None = None) -> int:
    """Re-invoke producer.py for just the now-unblocked scene, same
    convention as tools/set_designer.py's own trigger_continuation().

    Always passes --no-render (fixed 2026-08-13): nothing threads the
    original triage run's render intent through the job payload, and
    without it producer.py's default is to actually render (real
    headless-Blender video, tens of minutes) as a side effect of a
    worker job whose only purpose is to unblock casting. This job's
    role is registration/continuation only -- rendering stays an
    explicit, separate pass, never an implicit side effect of a
    background job completing. Found live: a duplicate-job dispatch
    bug (producer.py doesn't dedupe already-pending/running jobs for
    the same blocker across repeated runs) meant this fired repeatedly
    for the same scene, stacking up multiple concurrent real renders
    of the same output file for nearly an hour before being caught.
    """
    cmd = [VENV_PY, "tools/producer.py", "--script", script,
           "--primitive-fallback", "--scenes", str(scene_number), "--no-render"]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    # Same Blender-launch argv convention as tools/set_designer.py:
    # only what's after `--` belongs to this script when run under
    # `blender --background --python ... -- <args>`.
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    p = argparse.ArgumentParser(prog="casting_director")
    p.add_argument("--speaker-name", required=True)
    p.add_argument("--location-tag", required=True,
                   help="This scene's resolved location_tag; must already exist "
                        "in data/resolver_map.json's locations[]")
    p.add_argument("--script", required=True, help="Episode script path, for continuation")
    p.add_argument("--episode", required=True)
    p.add_argument("--scene-number", type=int, required=True)
    p.add_argument("--scene-context", default=None,
                   help="Scripted dialogue/action text for this scene "
                        "(docs/planning/LLM-ASSET-MATCHING-PLAN.md tier-1.5 "
                        "grounding); omitted means alias/real-asset matching "
                        "is skipped, same exact-match-or-build behavior as "
                        "before it existed")
    p.add_argument("--config", default=CONFIG_PATH)
    p.add_argument("--resolver-map", default=RESOLVER_MAP_PATH)
    p.add_argument("--standins", default=STANDINS_PATH)
    p.add_argument("--placeholder-assets-root", default=PLACEHOLDER_ASSETS_ROOT)
    p.add_argument("--no-continue", action="store_true",
                   help="Resolve only; skip re-invoking producer.py (testing aid)")
    args = p.parse_args(argv)

    result = resolve_role(
        args.speaker_name, args.location_tag,
        scene_evidence=args.scene_context,
        config_path=args.config,
        resolver_map_path=args.resolver_map,
        standins_path=args.standins,
        placeholder_assets_root=args.placeholder_assets_root,
    )
    print(json.dumps({"speaker_name": args.speaker_name, **result}, indent=2))

    if result["error"] or not result["role_tag"]:
        print(f"[casting_director] FAILED to resolve '{args.speaker_name}'; scene stays NEEDS_ASSETS")
        return 1

    print(f"[casting_director] resolved '{args.speaker_name}' as "
          f"{result['tier']} -> {result['role_tag']}")

    if args.no_continue:
        return 0

    return trigger_continuation(args.script, args.episode, args.scene_number)


if __name__ == "__main__":
    sys.exit(main())
