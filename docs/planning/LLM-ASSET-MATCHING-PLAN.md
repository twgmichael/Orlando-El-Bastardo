---
title: LLM Asset & Character Matching Plan
created: 2026-08-13T23:45:00-04:00
updated: 2026-08-13T23:45:00-04:00
doc_type: plan
production_area: pipeline
department: production
status: draft
canonical: true
canonical_for: llm_asset_matching
wiki: true
wiki_group: Planning
wiki_order: 190
---
# LLM Asset & Character Matching Plan

Recorded 2026-08-13, following `docs/planning/VEHICLE-DISCOVERY-PLAN.md`'s
Open Question 2 ("what does content-based asset discovery actually
look like") and the same day's live `small_bar_interior` saga -- a
real, hand-curated set that every deterministic string-matching layer
(location tags, camera `subject_marks`) missed entirely until a human
manually diagnosed and patched three separate registries by hand.
**Status: design doc, scoping only -- nothing built from this
document.**

## Why this exists

Every discovery mechanism audited today (`docs/planning/
VEHICLE-DISCOVERY-PLAN.md` Discoveries 1 and 4, plus the standalone
casting-director/production-designer/producer Q&A the same day) turned
out to be the same shape: an **exact-match lookup against a flat,
human-curated table**, falling straight to placeholder generation the
moment a script's wording doesn't literally match. That floor is
correct and should stay -- exact match is fast, free, and
unambiguous when it hits. The gap is what happens when it *misses*:
today, nothing. This plan adds exactly one more tier, in four places,
before placeholder generation: a constrained LLM match against the
real, already-built library.

## Cross-cutting design (applies to every integration point below)

- **Constrained candidate-set selection only.** The LLM is always
  handed a *finite* list of real, already-existing IDs (assets, cast
  names, cameras, location stand-ins) plus an explicit `"none"`/`"new"`
  option, and its output is constrained to that enum via
  `--json-schema` decoding at `--temp 0.0` -- the exact mechanism
  `tools/producer.py`'s `llm_review()` and `tools/director.py` already
  use (confirmed live 2026-08-13: `llama-completion -m
  llm/qwen2.5-3b-instruct-q4_k_m.gguf -p ... --json-schema {...}
  --temp 0.0 --seed 1 -n 1024 -c 4096 --no-display-prompt`). It can
  never emit a free-text name or invent a new ID -- the schema's enum
  is the real candidate list, nothing else is a valid output.
- **Grounded, not asserted.** A match must be justified against real,
  checkable evidence from the scene's own text -- same rule
  `director.py`'s arrival/departure evidence check already enforces
  (`tools/validate_spec.py`-adjacent convention: "a claimed flag whose
  evidence isn't an actual substring of the scene text is discarded").
  A match with a fabricated or non-substring "evidence" field is
  discarded exactly like an ungrounded arrival/departure claim is
  today, and the caller falls through to the deterministic path as if
  the LLM step had found nothing.
- **Persisted, asked once.** A confirmed match is written into the
  *same deterministic table* each role already reads first --
  `data/standins.json["location_standins"]`, `data/standins.json["cast"]`,
  `data/camera_grammar.json`'s `subject_marks` -- so it becomes an
  ordinary, human-indistinguishable data entry for every future run.
  The LLM is consulted once per unresolved name, not on every
  invocation; the tier-1 exact-match check every role already has is
  what makes the second occurrence free.
- **Deterministic fallback always.** Model unavailable, call errors,
  times out, or returns `"none"`/`"new"` -- the caller falls straight
  through to the existing placeholder-build path, unchanged. Same
  `try/except ... # noqa: BLE001 -- must not crash the run` discipline
  already wrapping every primitive-fallback call in `casting_director.py`
  / `set_designer.py` / `producer.py`.
- **One shared implementation, four call sites.** All four roles need
  the identical "given N real candidates + scene evidence, pick one or
  none" operation. Build it once:

  ```python
  # tools/llm_asset_match.py (new)
  def match_existing_asset(
      subject_text: str,       # the scripted name/phrase to match
      scene_evidence: str,     # surrounding text for grounding
      candidates: list[dict],  # [{"id": ..., "display_name": ..., "description": ...}, ...]
      kind: str,                # "character" | "vehicle" | "location" | "camera"
  ) -> dict:
      """Returns {"matched_id": str|None, "evidence": str|None}.
      matched_id is always either one of candidates[]["id"] or None --
      enforced by --json-schema enum, not by trusting the model.
      evidence, if given, must be verified as an actual substring of
      scene_evidence by the caller before being trusted (grounding
      check -- this function does not verify its own output).
      """
  ```

  Each role's call site builds its own `candidates` list from
  `oeb.config.json`/`data/resolver_map.json`/`data/camera_grammar.json`
  and does its own grounding check + persistence write; this shared
  function only owns the LLM call and schema.

## Producer

Producer's own charter is "notice the gap, never resolve it" (per
`docs/planning/PRODUCER-PLAN.md`), so this plan does **not** add
matching to Producer's location/cast blocking checks directly. The one
legitimate spot: **props/set-dressing**, since `llm_review()`
(`tools/producer.py`) already runs an LLM pass per scene and already
produces `mentioned_items`. When an item isn't in
`data/standins.json["known_items"]`, before writing it as a
non-blocking "unknown item" note, call `match_existing_asset()` against
`oeb.config.json`'s real (`"placeholder"` absent) `kind: "prop"`
assets, using the scene's own beat description as `scene_evidence`. A
confirmed match gets appended to `known_items` (a flat list -- no new
schema needed) instead of surfacing an avoidable "unknown item" ticket
note. No new LLM call site -- richer use of the one already running
per scene.

## Production Designer (`tools/set_designer.py`)

Highest-value, first-to-build candidate (see Sequencing below).
`resolve_location()`'s tier-1 stand-in check
(`standins.get("location_standins", {}).get(location_name)`) is
exact-match only; a miss falls straight to tier-2 primitive-placeholder
build, blind to the real library -- confirmed live today as exactly
what would have silently built a redundant placeholder bar instead of
reusing `small_bar_interior`, had that stand-in mapping not already
existed by luck.

**New tier-1.5**, inserted between the existing tier-1 exact-match and
tier-2 primitive build:

```python
def resolve_location(location_name, *, int_ext=None, ...):
    ...
    # Tier 1 (existing): exact stand-in match
    standin = standins.get("location_standins", {}).get(location_name)
    if standin and standin in rmap.get("locations", {}):
        return {"tier": "stand_in", "resolved_tag": location_name, "error": None}

    # Tier 1.5 (new): LLM match against real, non-placeholder locations
    real_locations = [
        {"id": tag, "display_name": tag, "description": entry.get("marks", [])}
        for tag, entry in rmap.get("locations", {}).items()
        if not entry.get("placeholder")
    ]
    if real_locations:
        result = match_existing_asset(
            subject_text=location_name,
            scene_evidence=scene_heading_and_context,  # passed in from caller
            candidates=real_locations,
            kind="location",
        )
        if result["matched_id"] and _grounded(result["evidence"], scene_heading_and_context):
            standins.setdefault("location_standins", {})[location_name] = result["matched_id"]
            _write_json(standins_path, standins)
            return {"tier": "llm_stand_in", "resolved_tag": location_name, "error": None}

    # Tier 2 (existing): primitive placeholder build
    ...
```

`resolve_location()` currently doesn't receive scene text at all
(only `location_name`/`int_ext`) -- its caller
(`register_vehicle_placeholder`'s sibling call path in
`tools/producer.py`) already has the scene object in scope, so this
requires threading one new parameter through, not a new data source.

**New tier name `"llm_stand_in"`** (distinct from `"stand_in"`) so the
production report and any future audit can tell a human-curated match
from an LLM-proposed one apart -- worth keeping distinguishable at
least until this mechanism has a track record (see Risks).

## Casting Director (`tools/casting_director.py`)

Two integration points inside `resolve_role()`, both before the
existing "new speaker -> classify + build" branch:

1. **Alias/nickname resolution.** "Cap," "the captain," "Captain
   Reyes" should be one role; `resolve_role()`'s "already cast" check
   (`standins.get("cast", {}).get(lname)`) is exact `speaker_name`
   match, so today they're three placeholder characters. Before
   falling to `classify_cast()`, call `match_existing_asset()` with
   `candidates` built from `standins["cast"]`'s existing keys (already
   cast in *this episode*, not the whole library -- aliasing across
   unrelated episodes isn't a real risk worth the candidate-set noise),
   grounded against the scene's own dialogue/action text. A confirmed
   match adds a new `cast` entry pointing at the *existing* `role_tag`
   -- same shape `register_placeholder_cast()` already writes, just
   sourced from a match instead of a fresh registration.
2. **Real-asset matching.** Same pattern as Set Designer: before
   building a placeholder for a genuinely new speaker, check them
   against real (non-placeholder) `kind: "character"` assets in
   `oeb.config.json` the same way `earth_starfighter_hero_A`-style
   ships would be checked for vehicles.

Both share one constraint the other three roles don't have:
`FUNCTIONAL_LABEL_KEYWORDS`' principal/background classification must
still run **after** matching, not before -- an LLM-matched alias
inherits the matched role's existing tier, it doesn't get
re-classified.

## Director (`tools/director.py` / `tools/resolve_intent.py`)

Already the most LLM-integrated role (`llm_review`, the per-scene
staging/blocking call). The gap is one level downstream, in
`resolve_intent.py`'s R3 camera check (`E_NO_CAMERA`): exact list
equality, `c.get("subject_marks") == [spawn_mark]` -- confirmed live
today as the exact mechanism that hard-failed scene 15 until a human
manually added the right entry to `cam_medium_bartender`'s
`subject_marks`.

Proposed: extend the **existing** director staging call (not a new
call site) so its own constrained schema also returns an optional
camera preference when the deterministic match is about to fail.
Concretely, `resolve_intent.py`'s R3 loop, on `len(matches) != 1`,
calls `match_existing_asset()` with `candidates` built from
`grammar["cameras"]` filtered to the right `framing`, `scene_evidence`
the shot's own description/dialogue, `kind="camera"`. A confirmed
match gets written into that camera's `subject_marks` list in
`data/camera_grammar.json` -- the exact hand-edit made today,
automated. This is a resolver-time check today (`resolve_intent.py`,
not `director.py` itself), so this is a new call site, not an
extension of the existing director LLM call -- noted as a difference
from the other three roles.

## Sequencing

1. **Set Designer first.** Highest current pain (today's whole
   `small_bar_interior` saga), smallest blast radius (one function,
   one new tier, one persistence target), clearest grounding signal (a
   location heading vs. real set descriptions -- least ambiguous of
   the four).
2. **Casting Director second.** Same shape, slightly fuzzier grounding
   (dialogue attribution/nicknames vs. a location heading).
3. **Producer's prop-matching third.** Lowest risk (non-blocking today
   regardless -- a miss just stays an "unknown item" note, never a
   blocked scene), reuses an existing call, good low-stakes place to
   validate the shared `match_existing_asset()` implementation before
   it gates anything blocking.
4. **Director/camera-matching last.** Different code path
   (`resolve_intent.py`, not a role file), and mismatches surfaced so
   far are believed to be new-content-only (today's fix covered the
   one real hand-curated set currently in the library) -- lowest
   near-term volume of the four, worth building once the shared
   function is proven on the other three.

## Risks / open questions

- **Model reliability is unproven for this task shape.**
  `docs/planning/DIRECTOR-ROLE-PLAN.md`'s own 2026-08-10 finding:
  "Live testing against the local 3B director model showed it isn't
  reliable enough on its own to safely replace the regex" for
  arrival/departure detection -- a simpler task than candidate
  selection. This plan's grounding requirement is the same mitigation
  already proven there (union of LLM + deterministic signal, never LLM
  alone), but matching-by-candidate-list is untested for this model at
  this size and needs its own live validation pass per role, not an
  assumption it'll behave like the arrival/departure case.
- **Human review gate?** This project's established pattern for other
  consequential automated decisions is a human-approval gate (kitbash
  build approval via `/review/kitbash`). Whether an LLM-confirmed match
  should write directly into `location_standins`/`cast`/`camera_grammar.json`
  (as drafted above) or land in a pending/needs-review state first is
  not decided here -- the `"llm_stand_in"` vs `"stand_in"` tier
  distinction (Production Designer section) is one way to keep that
  door open without deciding it now.
- **Latency/cost per scene.** An extra constrained LLM call only fires
  on a tier-1 miss (rare once a script's vocabulary stabilizes across
  an episode), not per scene unconditionally -- but the first full
  triage pass of a new episode would hit it often. Not measured; worth
  timing before wiring this into an unattended full-episode run.

## Build status (2026-08-14)

Implemented in the order this document recommended. `tools/llm_asset_match.py`
exists: `match_existing_asset()` (constrained candidate-set selection)
and `grounded()` (whitespace/comma-tolerant substring check --
discovered live that the model reliably swaps a comma for a newline
when quoting scene text, so a naive exact check would reject genuinely
correct matches). One correction to the original system-prompt design:
the first version's heavy caution framing ("never invent... if not
confident, answer none") made the 3B model decline *every* match,
including maximally obvious ones (a candidate description reading
verbatim "The Red Dragon Inn bar interior" for subject "RED DRAGON
INN" still returned `"none"`). A neutral, task-focused system prompt
fixed this completely -- worth remembering for any future constrained-
match prompt in this pipeline: caution language that reads as
reasonable to a human can suppress a small model's willingness to
commit to a correct answer at all.

**Live validation results per role** (the plan's own flagged risk --
"needs its own live validation pass per role, not an assumption"):

- **Set Designer (tier-1.5 in `resolve_location()`)**: validated
  working. A brand-new tag with no stand-in ("the rusty tavern")
  correctly matched `small_bar_interior` and persisted into
  `location_standins`; an unrelated new tag ("the ice cave") correctly
  fell through to tier-2 with no false match.
- **Casting Director (both tiers in `resolve_role()`)**: validated
  working. Alias resolution ("the captain" -> already-cast
  `captain_reyes`) matched and persisted correctly; a genuinely new
  speaker ("nervous ensign") correctly did not false-match and got its
  own new role. Real-asset matching for new principals is wired but
  untested live -- zero real (non-placeholder) character assets exist
  in the library yet to test against.
- **Producer (prop matching in the `mentioned_items` loop)**: validated
  working against the real registry -- "a tumbler glass" correctly
  matched `prop_glass_tumbler_A` from the actual `oeb.config.json` prop
  list, grounded correctly.
- **Director / `resolve_intent.py` (camera tier-1.5)**: **built, but
  did not pass live validation.** Deliberately scoped to only ever
  claim a camera with a genuinely empty `subject_marks` list (never
  append to or replace an already-assigned one -- appending would
  silently break `resolve_intent`'s own exact-list-equality match
  check, the identical bug caught and reverted by hand during the
  scene 15 fix earlier the same day). Tested against a real scene
  (pilot_sc15) with one camera's `subject_marks` cleared to simulate a
  newly-authored, unassigned camera: the model declined the match even
  with a single, highly relevant candidate and simplified phrasing.
  Camera-to-actor matching appears to be a harder relationship for this
  3B model than location/character identity matching -- consistent
  with this document's own predicted risk. The code is safe to leave
  in place (never destructive, degrades to the exact prior
  `E_NO_CAMERA` behavior when no match fires) but should not be
  considered proven; a follow-up pass (different prompt framing, or
  accepting this integration may need a larger model) is undecided.

**Regression check**: did not pass clean on the first full run. Two
passes plateaued at 73/8/0, exposing three real bugs, all now fixed:

1. **Report-merge regression** (pre-existing, newly exposed) -- a slow
   full-episode pass could silently overwrite a concurrent worker
   continuation's fresher `DELIVERED` with its own stale outcome.
   Fixed: an on-disk `DELIVERED` is never regressed by this run's own
   outcome for the same scene.
2. **`export_blender.py` actor_map gap** -- a background role that's
   the only actor on its shared node in a scene skipped the
   `actor_map` update the shared-instancing branch already had,
   breaking downstream move/animation cues. Fixed.
3. **Alias-matching false positive** -- unguarded, the model aliased
   the generic label `"voice"` to the named principal `"casey"`, and
   `"orion pilot"` to `"orlando"`, reintroducing `E_DUPLICATE_CHARACTER`.
   Fixed by restricting alias-matching to principal-shaped names on
   both sides; the two corrupted `data/standins.json` entries were
   found and removed.

After all three fixes: verified **81/81 delivered, 0 blocked, 0
failed**. Takeaway: a single clean pass isn't sufficient evidence with
the worker online concurrently -- confirm via two consecutive clean
passes with the queue drained first.

Nothing committed yet.
