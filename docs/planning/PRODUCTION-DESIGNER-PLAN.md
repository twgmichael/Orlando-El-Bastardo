---
title: Production Designer Plan
created: 2026-07-11T21:32:45-04:00
updated: 2026-08-10T09:55:26-04:00
doc_type: plan
production_area: sets
department: art
status: draft
canonical: true
canonical_for: production_designer_agent
wiki: true
wiki_group: Planning
wiki_page: Production-Designer-Plan
wiki_order: 80
---
# Production designer plan — a set-building worker agent

Recorded 2026-07-11 (designed with the project owner). Status: **PLANNED,
not built.** Extends the crew with an agent that can be assigned set and
asset tickets, survey the library, and compose sets by kitbashing
approved pieces — formalizing the process that built the sci-fi bar.
Updated 2026-08-08 per docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md
section 5 — this is the plan that plan's "set designer" role means;
see the "Non-goals" section below for what changed.

**Updated 2026-08-10 — role split from Producer, automatic loop
adopted.** See "2026-08-10 discussion and discovery" below for the full
finding: `tools/producer.py`'s `--primitive-fallback` had accreted this
role's core responsibility (set/location resolution and primitive
construction) directly into Producer, under time pressure to show
progress, in direct contradiction of `PRODUCER-PLAN.md`'s own charter
("never to improvise, substitute, or build"). This update accepts that
finding: the location-handling code identified below relocates out of
Producer, this role becomes an **automatic loop that picks up
immediately after Producer** rather than the human-dispatched/
GitHub-Issues model the rest of this document originally described (see
"Assignment interface" for what changed there specifically), and
Producer returns to strictly logistics + tickets, per its own original
charter, with no fallback-building of its own.

## Why this works: the proven template

The bar set (`tools/build_scifi_bar.py`) established the pattern:
**layout-as-data** — a table of (piece, position, z-rotation) assembled
deterministically, canonical node naming, marks and cameras carried
through, material fixes applied at build time. The layout was authored
by hand through a look-adjust-look loop over review renders. Two
findings de-risk the agent version: the modular CC0 pieces compose well,
and even grey-box massing read acceptably from the start — so the
agent's floor is "usable placeholder" and its ceiling is "kitbashed
final," a forgiving gradient.

## Division of labor (unchanged principles)

- The **producer** (local LLM) files tickets naming what a scene lacks.
  It never designs and never commands agents (DECISIONS 2026-07-07).
  **Reaffirmed 2026-08-10: strictly logistics + tickets** — no
  fallback-building of its own; see discovery section below for why
  this needed reaffirming, not just restating.
- The **production designer** (worker-tier agent) consumes a ticket and
  delivers a set. Spatial/aesthetic judgment against rendered frames is
  frontier-model work — not the local 3B's job.
- **Dispatch and aesthetic sign-off stay human — for the kitbash tier.**
  Updated 2026-08-10: the rough tier (primitive/stand-in placement) runs
  as an automatic loop with no human dispatch or sign-off step; see
  "Assignment interface" for the two-tier split. The designer never
  downloads or generates new source assets in either tier — acquisitions
  remain human-approved (standing constraint); it composes ONLY what the
  provenance-registered library already holds, plus primitives.

## 2026-08-10 discussion and discovery

**Finding:** `tools/producer.py`'s `--primitive-fallback` (built
2026-08-09) does exactly what this document assigns to the production
designer — resolve a missing location against approved stand-ins first,
fall back to building it from primitives otherwise, then let the scene
continue — except it does so *inside Producer itself*, as an inline
function call in Producer's own per-scene loop. This happened under
real time pressure to keep showing rendered progress, and it directly
contradicts `PRODUCER-PLAN.md`'s own charter: "the producer's job is to
stop that scene and emit an obvious, structured MISSING/NEEDED
response, never to improvise, substitute, or build" — restated almost
verbatim in `DIRECTOR-ROLE-PLAN.md`. Producer had, in effect, absorbed
this role's job (and part of the not-yet-built Director role's) rather
than delegating to it, because neither role existed yet to delegate to.

**Code identified for relocation out of `tools/producer.py`:**

1. The location tier-1/tier-2 resolution block in the main scene loop
   ("Location: direct, stand-in, or blocked" — checks `rmap['locations']`
   directly, then `data/standins.json`'s `location_standins`, then falls
   to a blocking ticket). This *is* "approved sets/locations first,"
   just currently inline in Producer instead of a separate consult.
2. `primitive_fallback()`'s **location-handling block only** (not the
   role/character or role_location blocks in the same function — those
   are casting, a different concern, out of scope for this document).
   Builds a placeholder location via `tools/placeholder_blueprint.py`,
   registers it in `oeb.config.json`/`data/resolver_map.json`.
3. `tools/placeholder_blueprint.py`'s location-building functions
   (`register_placeholder_location`, `default_placeholder_blueprint`
   with `kind="location"`, `build_placeholder_glb`) — already reasonably
   decoupled utilities; the production designer owns or imports these
   directly rather than Producer holding them.

**What the automatic loop needs to run standalone**, once relocated:

- **Input**: real Producer output, not a function call — watches
  `out/production/<episode>/tickets/NEEDED-*.json` for `kind: "location"`
  entries (and/or `production_report.json`) the moment Producer writes
  them. Producer still never commands agents directly (unchanged
  DECISIONS 2026-07-07); the designer watches on its own.
- **Shared registries**, same three files Producer already touches:
  `oeb.config.json`, `data/resolver_map.json`, `data/standins.json` — no
  parallel store, same principle section 7 of the unified pipeline plan
  already established.
- **Blender subprocess capability**, for the primitive-build path.
- **A continuation trigger**: re-invoke just the unblocked scene once
  its location is resolved — `tools/producer.py --scenes N` against the
  same script/episode, not a full re-render of everything already
  delivered.

**Open, not yet decided:** where casting (role/role_location blockers)
and the not-yet-built Director role's responsibilities land. This
document only claims the *location* half of what `--primitive-fallback`
does today; the role/character half of that same function still needs a
home, either staying with Producer, moving to a future Casting-flavored
role, or folding into `DIRECTOR-ROLE-PLAN.md`'s still-open producer
integration point.

## Build order

### 1. Asset index (deterministic enabler — useful regardless)

`tools/index_assets.py` → `data/asset_index.json`: walk the converted
GLB packs and record per piece — name, pack, file, bounding box, poly
count, name-derived tags (wall/floor/door/table/panel/...). The library
is ~750 pieces across 12 packs; "review available assets" must be a
query, not a per-session expedition. Regenerate on pack additions;
deterministic ordering.

### 2. Generic set assembler (deterministic)

Generalize `build_scifi_bar.py` into `tools/build_set.py` reading a
**set spec** (JSON): layout rows (piece, position, rotation), primitive
props, marks, cameras, canonical set node name, material fixes, export
targets. The designer authors DATA, not code — reviewable, diffable,
and bounded by what the assembler permits. Acceptance: rebuilding the
existing bar from a spec reproduces it (verified by introspection
manifest / node inventory, allowing for nondeterministic binary bytes).

### 3. The designer profile (`.claude/agents/production-designer.md`)

Authored per AGENT-WORKFLOW-PLAN §4 (post-author-tier: human +
reviewer-tier co-authoring against `_TEMPLATE.md`). The working loop:

1. **Requirements in** — the ticket + script text: needed marks,
   cameras, props, mood, rough dimensions.
2. **Survey** — query the asset index for candidates.
3. **Compose** — write/edit the set spec; run the assembler.
4. **Look** — headless review renders from standard angles; judge;
   adjust; repeat. (The craft loop, now the agent's inner loop.)
5. **Register** — oeb.config.json entry, resolver-map location entry,
   marks present in the GLB, camera-grammar additions if any,
   docs/PROVENANCE.md line for the assembled set.
6. **Deliver** — set GLB + set spec + review stills attached to the
   ticket; hand to pipeline-verifier.

Standing constraints (inherits the roster's): repo-relative paths only,
no absolute paths, no downloads, no git write operations, escalation
per ESCALATION-PROTOCOL when blocked.

### 4. Qualification (per AGENT-WORKFLOW-PLAN §7)

- **Dry run**: rebuild the existing sci-fi bar from its ticket — a
  known-good target with an objective comparison.
- **Drill**: a ticket requesting something the library cannot provide
  (e.g. a rideable horse-drawn carriage) — must report the gap
  precisely and stop; improvisation or acquisition attempts fail the
  drill. Mirrors the producer's missing-asset discipline.

### 5. Verification gates (unchanged discipline)

pipeline-verifier checks (canonical node, marks in GLB, clean headless
import), then a real scene render through the pipeline, then human
aesthetic sign-off. A delivered set that no scene can render is not
done.

## Assignment interface

**Superseded 2026-08-10** (see "2026-08-10 discussion and discovery"):
the human-dispatched model below described the *kitbash-from-library,
aesthetic-sign-off* tier of this role's work — real, and still the
right model for that tier. It never designed for the fast, unattended,
rough-primitive tier `--primitive-fallback` actually proved out this
session, which has no human dispatch step and needs to run
automatically. Two tiers now exist under this one role, dispatched
differently:

- **Rough tier (primitive/stand-in, automatic, no human step):**
  Set Designer runs as **an automatic loop that picks up immediately
  after Producer**, not a claimed ticket. It watches
  `out/production/<episode>/tickets/NEEDED-*.json` (and/or
  `production_report.json`) for `kind: "location"` entries the moment
  Producer writes them, resolves each via the tier-1 stand-in check
  first (`data/standins.json`'s `location_standins`) and falls to
  building a primitive placeholder only when no stand-in exists, then
  **continues the production process itself** — re-invoking Producer
  for just that scene (`tools/producer.py --scenes N`) now that the
  location exists, no human sign-off gate for this tier. This is the
  loop `--primitive-fallback`'s location-handling code relocates into
  (see discovery section).
- **Kitbash tier (library composition, human-supervised):** unchanged
  from the original design above — ticket dispatch (near-term: the same
  ticket files, watched rather than claimed; later: GitHub Issues +
  Project board), the designer profile's full survey/compose/look loop,
  and human aesthetic sign-off before the verifier pass closes the
  ticket. This tier is for real kitbashed sets, not rough blocking, and
  keeps its human gate.

A rough-tier placeholder registered automatically remains eligible for
later kitbash-tier replacement — placeholder-tagged entries in
`oeb.config.json`/`data/resolver_map.json` are exactly the backlog the
kitbash tier's ticket queue already draws from.

## First real assignments (already queued in PROJECT-TODO)

1. Orbital-lounge dressing: instrument panels + viewports (Modular
   Sci-Fi MegaKit), booths/tables (House Interior pack), station
   personnel EXCLUDED (characters are not set dressing).
2. Bar furniture (counter/stool/glass/bottle upgrades — House Interior
   donors).
3. `rooftop_garden` — the standing ep_001 ticket.

## Non-goals

- No autonomous acquisition of new packs.
- No self-approval: the designer never closes its own ticket.

**Superseded 2026-08-08** (docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md
section 5): this list used to also say "No generative geometry/textures;
composition of approved assets only." That constraint existed because
generative construction wasn't trustworthy when this plan was written
(2026-07-11), well before the Blueprint propose -> validate -> repair
loop (REVIEW-AUDIT.md sections 13-19) exist and its full audit trail
(every Studio Chat thread already traced via `studio_chat_trace_events`)
made generative construction safe to allow. The designer may now use
Studio Chat for real generative work -- "first level access," per the
same plan section, real/direct tool access paired with full audit of
every use, not a sandboxed subset. Composing from the approved library
via `tools/build_set.py` remains the preferred, still-supported path
where it already covers what's needed; Studio Chat access is additive,
subject to the same guardrails Producer has (UNIFIED-BLUEPRINT-PIPELINE-PLAN.md
section 4): no story invention, no freehanding a finished-looking hero
or production asset.
