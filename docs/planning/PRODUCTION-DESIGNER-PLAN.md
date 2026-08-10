---
title: Production Designer Plan
created: 2026-07-11T21:32:45-04:00
updated: 2026-08-10T16:45:00-04:00
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

Recorded 2026-07-11 (designed with the project owner). Status: **both
tiers BUILT and live-verified 2026-08-10** — rough tier
(`tools/set_designer.py`) and kitbash tier (`tools/build_set.py`,
`tools/index_assets.py`, `.claude/agents/production-designer.md`,
human sign-off via `/review/kitbash` in oeb-studio-harness). See each
tier's own "2026-08-10 built" section below. Still open: qualification
drills, the pipeline-verifier gate, the casting/role-location question,
and real GitHub Issues/Project integration (explicitly deferred,
"eventually" per the user). Extends
the crew with an agent that can be assigned set and asset tickets,
survey the library, and compose sets by kitbashing approved pieces —
formalizing the process that built the sci-fi bar. Updated 2026-08-08
per docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 5 — this
is the plan that plan's "set designer" role means; see the "Non-goals"
section below for what changed.

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

**What the automatic loop needs to run standalone**, once relocated —
all four **built and verified 2026-08-10** (see "2026-08-10 built"
above); the "Input" bullet below is superseded by the push-enqueue
mechanism actually delivered, kept here for the historical record:

- **Input**: ~~watches `out/production/<episode>/tickets/NEEDED-*.json`
  for `kind: "location"` entries~~ — built instead as Producer itself
  enqueueing a job on the existing worker queue at ticket-write time
  (`enqueue_set_designer_job()`). The NEEDED ticket is still always
  written first and remains the source of truth for what's blocked;
  Producer still never commands agents directly (unchanged DECISIONS
  2026-07-07) beyond this one best-effort enqueue call.
- **Shared registries**, same three files Producer already touches:
  `oeb.config.json`, `data/resolver_map.json`, `data/standins.json` — no
  parallel store, same principle section 7 of the unified pipeline plan
  already established. Confirmed: `tools/set_designer.py` reads/writes
  these directly, nothing new introduced.
- **Blender subprocess capability**, for the primitive-build path —
  delivered via the existing `BlenderCLIAdapter`, no new adapter.
- **A continuation trigger**: re-invoke just the unblocked scene once
  its location is resolved — `tools/producer.py --scenes N` against the
  same script/episode, not a full re-render of everything already
  delivered. Implemented as `trigger_continuation()`.

**Open, not yet decided:** where casting (role/role_location blockers)
and the not-yet-built Director role's responsibilities land. This
document only claims the *location* half of what `--primitive-fallback`
does today; the role/character half of that same function still needs a
home, either staying with Producer, moving to a future Casting-flavored
role, or folding into `DIRECTOR-ROLE-PLAN.md`'s still-open producer
integration point.

## 2026-08-10 built: rough tier, dispatched via the existing worker queue

Built and live-verified against the real Docker harness
(`oeb_studio_harness_local_api`/`_postgres`), not just unit-tested:

- **`tools/set_designer.py`** (new, stdlib-only, matching
  `tools/placeholder_blueprint.py`'s no-extra-deps convention):
  `resolve_location()` — the relocated tier-1 stand-in / tier-2
  primitive-build logic, unchanged in substance from what
  `primitive_fallback()` used to do inline — and
  `trigger_continuation()`, which re-invokes
  `tools/producer.py --scenes N` for just the now-unblocked scene. Runs
  identically under the project's own `.venv` (direct CLI use/testing)
  or Blender's bundled Python (worker dispatch, below); its `main()`
  slices `sys.argv` to the portion after `--` before parsing, the same
  convention every other Blender-invoked script in this project uses
  (e.g. `attach_ship.py`), since Blender's own launch args otherwise
  pollute `sys.argv` ahead of the script's own.
- **`tools/producer.py`**: the main-loop location block now *only*
  direct-matches or blocks+tickets — the tier-1/tier-2 resolution
  described above as item 1 for relocation is gone from Producer
  entirely; `primitive_fallback()`'s location-handling block (item 2) is
  deleted, with an explicit `still_blocking` pass-through added so
  location blockers aren't silently dropped from its return value.
  Producer is now strictly logistics + tickets for locations, per its
  own charter.
- **Dispatch mechanism actually built — corrects the "Assignment
  interface" section below:** not a separate process watching
  `NEEDED-*.json` ticket files. Per the 2026-08-10 cron-worker
  discussion ("extend the existing worker system... require either
  script run or this chatbot initiated"), Producer's own scene loop
  calls a new `enqueue_set_designer_job()` right after writing a
  `kind: "location"` NEEDED ticket, POSTing a job to the *existing*
  `oeb-studio-harness/worker/` job queue (`POST /api/v1/jobs`,
  `docs/planning/WORKER-AGENT-PLAN.md`) with
  `required_capabilities: ["blender.command_line"]` and a
  `script_file: "tools/set_designer.py"` payload — dispatched through
  the **existing** `BlenderCLIAdapter`'s `script_file` mode, no new
  adapter written. A live harness worker (`render-mac-01`) picked up
  and completed a real enqueued job end-to-end during verification: job
  claimed, `blender --background --python tools/set_designer.py --
  ...` executed, location resolved (primitive tier), `producer.py
  --scenes N` continuation triggered, scene `DELIVERED`.
- **Optional/best-effort by design:** if `OEB_HARNESS_URL` or
  `API_ADMIN_TOKEN` is unset, `enqueue_set_designer_job()` silently
  no-ops — Producer stays usable standalone with no live harness
  dependency; the NEEDED ticket is written regardless and remains the
  source of truth for what's blocked. `tools/set_designer.py` can also
  be invoked directly for a specific location/scene without the queue
  at all.
- **`tools/placeholder_blueprint.py`**: `register_placeholder_asset()`
  and `register_placeholder_location()` gained an optional `source`
  parameter (default preserves prior callers' behavior) so
  `set_designer.py`'s registrations are provenance-tagged
  `"set_designer"` rather than the old `"producer
  --primitive-fallback"` literal.
- **Verified**, not assumed: tier-1 and tier-2 resolution against
  scratch registry copies; Producer's new always-block behavior;
  `enqueue_set_designer_job()` really posting to the live harness;
  worker registration, job claim, and — after fixing the `sys.argv`
  slicing bug above — a real `BlenderCLIAdapter.execute(job)` run
  returning `SUCCESS: True` against a genuinely claimed job; the full
  `oeb-studio-harness/server` pytest suite (382 tests) unaffected.

**Still not built (as of the rough-tier landing above):** the kitbash
tier (steps 1-5 under "Build order" below, the designer agent profile,
`tools/build_set.py`) and the casting/role-location open question
above.

## 2026-08-10 built: kitbash tier, human sign-off via oeb-studio-harness

Built and live-verified end-to-end against the real Docker harness and
a real production worker (`render-mac-01`), same discipline as the
rough tier above. Direct answer to "how will humans approve": **reuse
the harness's existing `Asset` DB table + review-render pipeline (the
same one `/review/assets`/`/review/placeholders` already use), not
GitHub Issues/Project.** GitHub Issues/Project integration is still
wanted "eventually" (explicit user direction) but deliberately not
built now — see "Deferred" below.

- **`schemas/setspec.schema.json` + `tools/build_set.py`** (step 2):
  generalizes `tools/build_scifi_bar.py`'s hardcoded `LAYOUT` table
  into data — kit-piece layout, primitive-prop stacks (box/cylinder,
  generalizing the bar's bespoke bmesh barstool/counter code),
  marks (add-or-reposition), cameras (position + aim-at-point-or-mark),
  a `force_opaque` material fix, canonical join node. **Acceptance met
  exactly**: `data/setspecs/bar_scene_scifi.setspec.json` rebuilds the
  real sci-fi bar with an *identical* node inventory and identical
  20-placement/5762-poly/23-material-slot counts to the original
  hand-written script, verified by a real Blender run and a real glTF
  node-name diff, not assumed.
- **`tools/index_assets.py`** (step 1): stdlib-only, no Blender launch
  needed — parses each `.glb`'s own glTF JSON chunk directly (accessor
  min/max for bbox, indexed triangle count) rather than importing every
  piece. Run for real: 739 pieces across 17 packs (assets/ dirs,
  broader than the "12 packs" estimate since this also indexes
  `props`/`locations`/`ships`/etc., not just the big CC0 kits) in
  seconds. `data/asset_index.json` is regenerated output, not
  hand-authored — added to `.gitignore` alongside `assets/` itself
  rather than tracked and left to go stale.
- **Human sign-off, decided and built:** a kitbash build is dispatched
  via a new `POST /api/v1/jobs/kitbash-builds` (admin) endpoint —
  runs `tools/build_set.py` on a worker through the *existing*
  `BlenderCLIAdapter`, no new adapter. Completion is wired through the
  **existing, generalized** `post_build_review` mechanism
  (`_create_post_build_review_job` in `oeb-studio-harness/server/app/
  routers/jobs.py`, previously Studio-Chat-only and hardcoded to
  `status="available"`) — extended with an `initial_status` and
  `extra_metadata` field rather than duplicated, so a kitbash build
  lands as `kitbash_pending` (not auto-approved) with its own turntable
  review renders auto-generated for free, through the same pipeline
  Studio Chat assets already used.
- **`/review/kitbash`** (new router `app/routers/kitbash_ui.py` +
  service `app/services/kitbash_review.py`): index + detail + decision
  UI, structurally identical to the existing
  `/review/placeholders`/`placeholder_review.py` tier-2 pattern (same
  `Asset` table, same `AuditEvent` audit trail, same
  reject/approve-shaped state machine) — no new table, no migration.
  Detail page reuses `review_asset.html`'s exact angle-grid/lightbox
  gallery code, since the auto-generated review renders are literally
  the same `asset.review_render` job type.
- **Approval propagates to the real file registries, not just a status
  flip:** "approve" enqueues a `kitbash.register` job
  (`tools/register_kitbash_set.py`, stdlib-only, same Blender-argv
  `sys.argv` slicing convention as `set_designer.py`) that writes the
  real `oeb.config.json`/`data/resolver_map.json` entries a worker's
  checkout can reach — `placeholder: false`,
  `source: "set_designer_kitbash"`. If `--location-tag` names a
  location with an existing entry (the common case: upgrading a prior
  stand-in/placeholder), its marks are *merged*, not replaced, since a
  kitbash `SetSpec` typically only lists marks it adds or repositions,
  carrying the rest from its `base_placeholder`. The harness `Asset`
  row only becomes `"available"` once this job actually completes
  (`mark_registered()`, called from the job-completion path) — never
  the moment renders exist, so a still-pending or failed registration
  can't silently read as approved.
- **Verified live, full round trip, not just unit-tested:** a real
  `POST /api/v1/jobs/kitbash-builds` job was picked up and completed by
  the real `render-mac-01` worker (not a manual adapter invocation this
  time — an actually-running production worker); its
  `post_build_review` follow-up auto-created the `Asset` row and a
  review-render job, also completed by the same real worker;
  `/review/kitbash` and the detail page showed the real pending set
  with real rendered angles; approving it enqueued and the same worker
  completed the `kitbash.register` job; the real `oeb.config.json`/
  `data/resolver_map.json` on this machine received the entries; the
  set then appeared in `/review/assets` (status `available`),
  confirming the whole chain. Full `oeb-studio-harness/server` pytest
  suite (382 tests) unaffected; `tools/security_sweep.py` clean; all
  test registry entries, the test `Asset` row (via the harness's own
  `DELETE /api/v1/assets/{id}`), and scratch build output cleaned up
  afterward.
- **Known limitation, stated rather than silently skipped:**
  `register_kitbash_set.py` does not register `data/camera_grammar.json`
  entries for any new cameras a set spec defines — `SetSpec.cameras[]`
  has no framing-purpose field (`establishing`/`two_shot`/`close_on`/
  `medium_on`) to derive one from without inventing data. Cameras still
  export into the built GLB; wiring them into the resolver's camera
  vocabulary is left as human/Director follow-up.
- **`.claude/agents/production-designer.md`** (step 3): the first
  worker-tier agent profile ever authored in this repo — there was no
  prior profile or `_TEMPLATE.md` to build against, so it's written
  directly from `AGENT-WORKFLOW-PLAN.md` §4's 8 authoring rules.
  Working loop: Survey (`index_assets.py`) → Compose (author + validate
  a SetSpec against `schemas/setspec.schema.json`) → Look (local
  `build_set.py` iteration) → Deliver (`POST .../kitbash-builds`, then
  stop — approval and file-registry propagation are correctly a human
  decision plus a follow-on job, not this profile's job). Not yet
  exercised by an actual orchestrator/worker run — `AGENT-WORKFLOW-PLAN.md`'s
  tiered-delegation system itself remains unbuilt; this profile is
  ready for it, not proof it exists.

**Deferred, explicit user direction ("eventually," not now):** real
GitHub Issues/Project integration for kitbash dispatch/tracking. The
original "Assignment interface" section below still describes that as
the kitbash tier's intended near-term-to-later dispatch surface; what
actually shipped instead is the harness-hosted review queue above,
which the user explicitly named as the better near-term fit
("oeb-studio-harness seems the best candidate with a simple index,
details, view and approval process"). `AGENT-BUS-PLAN.md` remains
unbuilt/aspirational for this tier, same as it already was for the
rough tier per the 2026-08-10 note in the unified pipeline plan.

**Still not built:** step 4 (qualification drills) and step 5
(pipeline-verifier gate) under "Build order" below, and the
casting/role-location open question from the rough-tier section above.

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

**Built 2026-08-10** — see the "2026-08-10 built: kitbash tier" section
above. Authored directly against `AGENT-WORKFLOW-PLAN.md` §4's rules
(no `_TEMPLATE.md` existed to co-author against; this is the first
profile in the repo). **Order correction from what's below**: Register
now happens *after* Deliver, not before, and is not the agent's own
step at all — the agent's loop ends at Deliver (submit to the harness);
a human reviews and approves via `/review/kitbash`, which is what
triggers registration (a `kitbash.register` job,
`tools/register_kitbash_set.py`), automatically. The agent never writes
`oeb.config.json`/`data/resolver_map.json` itself. Original design
below, kept for the historical record:

1. **Requirements in** — the ticket + script text: needed marks,
   cameras, props, mood, rough dimensions.
2. **Survey** — query the asset index for candidates.
3. **Compose** — write/edit the set spec; run the assembler.
4. **Look** — headless review renders from standard angles; judge;
   adjust; repeat. (The craft loop, now the agent's inner loop.)
5. ~~**Register** — oeb.config.json entry, resolver-map location entry,
   marks present in the GLB, camera-grammar additions if any,
   docs/PROVENANCE.md line for the assembled set.~~ superseded, see above.
6. **Deliver** — set GLB + set spec + review stills attached to the
   ticket; hand to pipeline-verifier. **Built as**: `POST
   /api/v1/jobs/kitbash-builds`, which builds AND generates the review
   stills itself (`post_build_review`) — the agent doesn't build once
   locally then separately request renders, "Look" (local iteration)
   and "Deliver" (harness submission + auto review-render) are the only
   two build invocations.

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

- **Rough tier (primitive/stand-in, automatic, no human step) — BUILT
  2026-08-10, see "2026-08-10 built" above for what actually
  shipped:** Set Designer runs as **an automatic loop that picks up
  immediately after Producer**, not a claimed ticket. Originally
  designed as a separate process watching
  `out/production/<episode>/tickets/NEEDED-*.json` for `kind:
  "location"` entries; what was actually built instead is **push, not
  poll** — Producer's own scene loop enqueues a job on the existing
  `oeb-studio-harness/worker/` queue the moment it writes a `kind:
  "location"` NEEDED ticket (per the 2026-08-10 cron-worker decision to
  extend the existing worker system and require either a script run or
  chatbot-initiated trigger, rather than run a standalone watcher
  daemon). `tools/set_designer.py` resolves the location via the tier-1
  stand-in check first (`data/standins.json`'s `location_standins`),
  falls to building a primitive placeholder only when no stand-in
  exists, then **continues the production process itself** —
  re-invoking Producer for just that scene (`tools/producer.py
  --scenes N`) now that the location exists, no human sign-off gate for
  this tier.
- **Kitbash tier (library composition, human-supervised):** the
  survey/compose/look loop and human sign-off gate are unchanged from
  the original design here. **Dispatch/sign-off surface built
  differently, 2026-08-10** — not ticket files, not GitHub Issues +
  Project board (still wanted "eventually," per the user, not built):
  submission is `POST /api/v1/jobs/kitbash-builds`, sign-off is
  `/review/kitbash` in oeb-studio-harness (reject/approve, same `Asset`
  table + `AuditEvent` pattern as `/review/placeholders`). Approval
  dispatches `tools/register_kitbash_set.py` as a follow-on job rather
  than a verifier pass closing a ticket — pipeline-verifier integration
  (step 5 under "Build order") is still unbuilt. This tier is for real
  kitbashed sets, not rough blocking, and keeps its human gate.

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
