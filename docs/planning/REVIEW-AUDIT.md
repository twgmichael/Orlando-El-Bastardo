---
title: Studio Chat / Blender MCP Review — Discussion Audit
created: 2026-08-07T17:27:35-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: reference
production_area: pipeline
department: pipeline
status: active
canonical: false
wiki: true
wiki_group: Planning
---
# Studio Chat / Blender MCP Review — Discussion Audit

Date: 2026-08-06

Status: discussion record, not a decision doc. Captures the reasoning and
opinions exchanged while reviewing Studio Chat against the Blender MCP
ecosystem, including points that are not written down anywhere else. See
[Studio Chat vs. Blender MCP Review Criteria](STUDIO-CHAT-VS-BLENDER-MCP-REVIEW-CRITERIA.md)
and [OEB Studio Chat Lightweight Plan](OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md)
for the underlying evidence (function inventory, installed-server findings,
job-worker trace). This doc is the narrative of the discussion itself.

## 1. Why this review started

Directive from the user's cousin: Blender now has an official experimental
MCP server (Blender Lab). Recommendation was to evaluate and integrate with
the Blender MCP ecosystem first rather than designing a competing Blender
protocol from scratch, with OEB Studio sitting above/alongside it to add
production-specific capabilities (canonical asset identity, Blueprint
execution, SceneSpec/ShotSpec, revision history, render orchestration,
asset promotion, permissions/validation, project memory). Scope was
narrowed, by the user's choice, to: official Blender Lab MCP server only
(community project as fallback), deliverable a function-by-function
keep/drop table, local install/testing authorized, source of truth
`Orlando-El-Bastardo.src`.

## 2. Function inventory result

27 grouped entries catalogued across `services/studio_chat.py`,
`routers/studio_chat.py`, `routers/studio_chat_ui.py`, and
`tools/studio_chat.py`. Headline results:

- 0 entries touch a live Blender session — Studio Chat only authors specs
  and enqueues jobs; Blender execution happens downstream.
- 0 entries have any code-execution exposure — the LLM is hard-constrained
  to a fixed primitive schema; prompts explicitly forbid writing Blender
  code.
- ~21 of 27 entries are OEB-owned production concerns with no Blender-
  control surface to even compare against MCP.
- Two loose ends were chased down and resolved: `tools/studio_chat.py`
  (the standalone CLI) and the legacy bare `POST /studio-chat` endpoint
  turned out to be two ends of the same still-live path (the CLI calls
  that endpoint by default), not dead code.
- The job-worker trace found the actual Blender invocation:
  `BlenderCLIAdapter._execute_script` runs `blender --background --python
  tools/primitive_asset_builder.py` — one-shot headless, no dynamic code.

Full detail is in the review-criteria doc's "Function Inventory" section.

## 3. Official Blender MCP server — installed and inspected

Installed via Blender's CLI extension manager (`blender --command
extension repo-add/sync/install`, adding the `https://lab.blender.org/`
repo) and read directly from the installed source
(`~/Library/Application Support/Blender/5.1/extensions/blender_lab/mcp/`).

Key findings, discussed at the time:

- **No per-tool schema exists.** The entire capability surface is one
  generic operation: send Python code over a local TCP socket, it gets
  `exec()`'d, a `result` dict comes back as JSON. This overturned the
  original plan's assumption that there would be a tool catalog to diff
  function-by-function against Studio Chat.
- **Both headless and interactive modes are real.** `blender --background
  --command blender_mcp` (headless, blocking) and an interactive
  `bpy.app.timers`-polled mode (persistent desktop session, supports
  deferred/long-running calls) both exist. Default `localhost:9876`
  either way. This corrected an earlier assumption (drawn from third-party
  docs before the source was read) that the official server was
  desktop-only.
- **Safety is explicitly weak, by the maintainers' own admission.**
  `weak_sandbox.py`'s own docstring says it "isn't really a sandbox."
  It blocks exactly `sys.exit()` and four destructive operators
  (`wm.quit_blender`, `wm.read_factory_settings`,
  `wm.read_factory_userpref`, `wm.read_userpref`). Everything else —
  file I/O, network access, deleting scene data — is open. The official
  `blender.org/lab/mcp-server/` page states this directly as a security
  warning recommending a VM or an isolated machine.
- **Recommendation reached in discussion:** do not route Studio Chat's
  existing headless build path through this mechanism. It would trade a
  zero-code-execution pipeline for one with acknowledged unguarded
  execution, for no capability gain — OEB already has headless Blender
  invocation today via its own worker. The official server is better
  scoped as a separate, gated, interactive/exploratory assistant surface,
  not a production-path replacement.

## 4. Community Blender MCP (ahujasid/blender-mcp) — inspected for learning

Explicitly out of scope for the formal keep/drop review, but the user
asked to download and inspect it anyway "for integration opportunity or
just learning what the community is working on." Cloned to a scratch
directory (not installed into Blender, not added to this repo) and read
from source, v1.8.0.

Discussion points:

- **Genuinely worth learning from:** unlike the official server, this
  project defines 23 distinct named MCP tools with real per-tool
  parameters, including a working asset-sourcing suite — PolyHaven,
  Sketchfab, and AI mesh generation via Hyper3D/Rodin and Hunyuan3D. If
  OEB ever wants external asset sourcing as a build-pipeline input, this
  is a working reference for that integration shape.
- **A concrete concern surfaced during inspection, not a hypothetical
  one:** the project's telemetry code sends tool-usage events (and,
  behind a consent toggle, raw prompt text, executed code, and viewport
  screenshots) to a third-party Supabase backend by default (opt-out via
  env var, not opt-in). Its own `TERMS_AND_CONDITIONS.md` states *"I do
  not collect: Screenshots or images of your viewport"* — the code
  (`get_viewport_screenshot` → `telemetry.upload_screenshot`) does exactly
  that when consent is on. This is a documented mismatch between stated
  policy and actual behavior, verified by reading the code, not asserted
  from marketing copy.
- **Same underlying execution risk as the official server** —
  `execute_blender_code` is the same class of unguarded `exec()` against
  `bpy`. Nothing here changed the recommendation about not routing
  production builds through either project's code-execution path.
- Both projects default to the same `localhost:9876` port, so they can't
  run simultaneously without reconfiguration — a minor practical note, not
  a decision-relevant one.

Full detail, including exact file:line citations, is in the review-criteria
doc's "Community Blender MCP" section.

## 5. Should OEB's own endpoints conform to MCP?

A separate question from "should OEB route through Blender's MCP" — this
one is about whether Studio Chat's *own* production-layer endpoints
(threads, assets, build jobs, revisions, graph edits) should be exposed as
MCP tools for external clients (Claude, etc.) to call directly.

Discussion conclusion: this is a much better fit for MCP than the
Blender-control question, and not a new idea for this project —
`Orlando-El-Bastardo.src/docs/ARCHITECTURE.md` already frames "Agent and
MCP interfaces" as resources/tools/prompts, and the roadmap already marked
Milestone 16 ("expose agent/MCP-style scene resources and mutation tools
separately from translation prompts") done. Because OEB's own tools are
already schema-constrained and validated (unlike raw Blender code exec),
converting them to MCP tools doesn't introduce the safety problem that
made adopting Blender's MCP for the build path a bad idea. Framed as
**additive** — a second interface next to the existing REST API — not a
reason to build it before there's an actual MCP client that needs it.

## 6. "What if it replaced the REST API instead, since REST is behind schedule?"

The user asked this directly, prompted by frustration that the homegrown
REST API isn't progressing as quickly as hoped. Position taken in
discussion, for the record:

- Pushed back on the framing. A slow-moving API is almost never a wrong-
  protocol problem — the hard part is the underlying logic (resolver,
  validation gates, revision/graph-edit semantics), and that work doesn't
  get easier reimplemented as MCP tool schemas; it's the same ~27
  functions' worth of logic, just under a different transport.
- Replacing (not adding) also means giving up things already built and
  working: Alembic migrations (`migrations/versions/0007-0010_studio_chat_*`),
  auth, and an existing test suite tied to the current REST shape.
- MCP's own tooling/ecosystem is comparatively young — the official
  Blender server inspected in this same session is a v1.0.0, single-
  generic-tool project, not evidence of a mature ecosystem to lean on.
- Conclusion offered: swapping protocols is unlikely to be the lever that
  fixes velocity, and doing so now risks stalling further via a mid-flight
  rewrite. The actual bottleneck (scope, staffing, complexity) should be
  named and addressed directly rather than attributed to REST vs. MCP.

## 7. "Is your cousin nerfing the local LLM, and are we on track for a product?"

The user's sharpest question: does the constrained, deterministic
architecture (fixed primitive registry, no LLM-authored Blender code,
heavy validation/repair pipeline) represent unnecessary "nerfing" of the
local LLM's own abilities, and is Studio Chat converging on an actual
product or going in circles? Position taken in discussion:

**Distinguish two different things that were being conflated:**

- **Not nerfing — legitimate engineering, would be true for any LLM.**
  Constraining the LLM to propose intent while a deterministic layer
  compiles and validates the actual geometry, gating job submission on
  `compiled` status, and keeping revision history/undo. This is the same
  positive safety/determinism finding already recorded in the function
  inventory (criterion 4 — zero code-execution exposure) and is not a
  trust issue with the model; it's what any production pipeline needs.
- **Actually nerfing, and worth pushing back on.** The heuristic layer
  sitting on top of the validated core — `default_components_for`,
  `enrich_scene_plan_details`, `detail_hints_for_request`, `infer_kind`
  (`services/studio_chat.py:3156-3469`, inventory row 15) — is hand-rolled
  Python guessing at things ("what components should this object have,"
  "what kind of object is this") that the LLM is already better at, ahead
  of the model's own reasoning. That's not a safety boundary; it's a
  bespoke, weaker reimplementation of what a prompt plus a validated
  output schema could do directly.

**Verdict on product vs. circles:** leans circles, not because the
constrain-and-validate approach is wrong, but because of what the
constraint machinery has been spent building. After 16+ milestones, the
expressive vocabulary is still primitives-plus-hierarchical-geometry — the
user-facing "what can it actually build" surface hasn't grown much.
Meanwhile this review surfaced a live, still-in-use legacy duplicate path
(`tools/studio_chat.py` CLI + bare `POST /studio-chat`), an unresolved
auth-coverage gap (only the legacy endpoint has explicit `require_admin`;
newer thread/asset/edit/revert/milestone endpoints show no endpoint-level
auth in the router file itself), and an ever-growing
trace/milestone/revision infrastructure layer. That pattern —
infrastructure velocity outpacing product velocity, plus hand-rolled
heuristics substituting for the model rather than validating it — is the
concrete evidence behind the "going in circles" read. The suggested
correction: cut the heuristic-guessing layer, let the LLM propose richer
structured output directly against a wider validated schema, and treat
"can it build something visually interesting, not just boxy primitives"
as the metric that actually decides whether this is progressing.

## 8. Salvage plan — where the "boxy primitives" ceiling actually is

Follow-up to section 7: the user asked to lean into "cut the heuristic-
guessing layer, let the LLM propose richer structured output against a
wider validated schema" and determine, from the actual code, what to keep
versus jettison. This required reading past the function inventory into
the implementation itself, and **corrects part of section 7's framing**:
the LLM was not actually being starved at the prompt layer the way that
discussion implied. The real bottleneck is one specific, previously
unexamined layer downstream of it.

**Correction: the LLM-facing schema is already rich.** `scene_plan_prompt`
(`services/studio_chat.py:4107-4154`) already asks the model for a full
semantic graph per object — free-text `shape.primary_form`,
`corner_style`, `edge_profile`, `required_features`, `style_details`,
`materials.finish`, and inter-object `relationships`. This is not a boxy,
under-specified prompt; section 7's implication that widening what's asked
of the LLM is the fix was too imprecise.

**The real ceiling: `_compile_typed_object_primitives`
(`services/studio_chat.py:3762-3870`) discards nearly all of that
richness.** Every semantic object collapses to `{type, material,
transform}` plus a `shape_modifiers` list matched against exactly five
hardcoded substrings (`half`, `flat`, `squished`, `flattened`,
`hemisphere`, line 3810). Fields like `corner_style="rounded"`,
`edge_profile="beveled"`, and `style_details` are captured from the model,
carried through as inert metadata into `tools/primitive_asset_builder.py`
(confirmed present but unused as geometry at line 480), and never turned
into an actual Blender operation — no bevel modifier, no subsurf, no
non-primitive mesh op. This is the concrete, file/line-level explanation
for why the product ceiling has stayed at "boxy primitives" through 16+
milestones: not model capability, not prompt design, but a geometry
compiler that only knows how to place raw primitives.

**Cut — confirmed genuine dead weight, not just "too cautious":**
`infer_kind`, `default_components_for`, `detail_hints_for_request`, and
`_fallback_payload_from_intent` (`services/studio_chat.py:3113-3499` and
`1386-1503`, ~400+ combined lines). Regex/keyword guessing at object kind
and style details from raw text, running as a routine parallel path next
to a model already asked the same questions structurally via
`scene_plan_prompt`. Recommendation: reduce to a thin last-resort fallback
for outright LLM-call failure, not a routine parallel path.

**Keep and build on — already the right pattern:**
- `resolve_primitive_spec` / `resolve_asset_intent_normalization`
  (`services/studio_chat.py:1555-1814`) — the propose → validate →
  LLM-repair retry loop. This already is "let the LLM propose against a
  validated schema"; it should be extended, not replaced.
- `validate_primitive_spec` / `primitive_registry`
  (`services/studio_chat.py:752-1041`) — the contract boundary. Keep as
  the validation gate; widen what it accepts as the compiler layer below
  gains the ability to act on richer fields.
- The relationship-placement math — `on_top_of`, `attached_to` spatial
  solving (`services/studio_chat.py:3823-3870`) — legitimate deterministic
  geometry compilation, not guessing. Keep.
- The entire production layer (threads, canonical assets, revisions,
  build-job orchestration, milestones — inventory rows 4-6, 16-27) is
  unaffected by this question and should be kept regardless.

**Separate technical-debt flag, independent of the LLM question:**
`compile_studio_chat_build_pipeline` is a single 828-line function
(`services/studio_chat.py:2272-3100`), and there are at least four
overlapping intermediate representations in play — `scene_plan`,
`asset_intent`, primitive `spec`, and the construction graph — bridged by
functions like `_scene_plan_from_asset_intent`, `normalize_spec`, and
`derive_spec_from_scene_plan` (`services/studio_chat.py:3911-4106`). This
looks like accretion across the 16+ milestones referenced in section 7,
not a deliberate design, and is worth consolidating to one canonical
intermediate representation independent of the heuristic-layer cut.

**Net recommendation:** keep the propose/validate/repair loop and the
primitive-registry contract; cut the ~400-line keyword-guessing layer down
to a bare last-resort fallback; redirect that freed effort into the
compiler/builder layer so it actually consumes the rich fields the LLM
already produces instead of discarding them; consolidate the four
intermediate schemas into one. This combination is expected to move the
"visually interesting, not boxy" metric from section 7 — re-widening the
prompt again would not, since the prompt was never the actual bottleneck.

## 9. Plan outline — move forward, salvage what works, clean out debt

Requested outline synthesizing sections 7-8 into a phased plan. Sequencing
rationale: low-risk cleanup first (doesn't touch behavior, removes
ambiguity found during the review), then subtract the heuristic layer only
once the propose/validate/repair loop has regression coverage to prove
removal is safe, then spend the freed effort on the one change expected to
actually move the product metric, then consolidate/refactor once the
churn from that change has settled, then measure.

**Phase 0 — low-risk debt cleanup (no behavior change, do first)**
1. Resolve the auth-coverage gap (section 7): either add explicit auth
   deps to the thread/asset/edit/revert/milestone endpoints, or confirm
   app-wide middleware already covers them and document it.
2. Decide the fate of the legacy pair — `tools/studio_chat.py` CLI + bare
   `POST /studio-chat` (both confirmed live and intentionally paired,
   section 2/4): either formally document them as the supported
   manual/ops path, or consolidate the CLI into a thin wrapper over the
   thread/build-jobs pipeline so there's one code path, not two that can
   drift.

**Phase 1 — cut the heuristic-guessing layer**
1. Reduce `infer_kind`, `default_components_for`,
   `detail_hints_for_request`, `_fallback_payload_from_intent`
   (`services/studio_chat.py:3113-3499`, `1386-1503`, ~400+ lines) to a
   bare last-resort fallback, only triggered when the LLM call fails
   outright — not a routine parallel path to `scene_plan_prompt`.
2. Before deleting, add regression coverage around `resolve_primitive_spec`
   / `resolve_asset_intent_normalization` (`services/studio_chat.py:1555-1814`)
   using the same creative-request cases the heuristics currently handle,
   so removal is provably safe rather than assumed safe.

**Phase 2 — fix the actual product ceiling (the real unlock, per section 8)**
1. Extend `_compile_typed_object_primitives` / `tools/primitive_asset_builder.py`
   to consume `shape.corner_style`, `edge_profile`, `required_features`,
   and `style_details` as real Blender operations (bevel modifier,
   subsurf, boolean ops) instead of discarding them into inert metadata
   (currently: `services/studio_chat.py:3762-3870`,
   `tools/primitive_asset_builder.py:480`).
2. Widen the primitive vocabulary in `primitive_registry` only as needed
   to support what the compiler can now realize — not before, or the
   "captured but unused" problem just reproduces at a wider vocabulary.

**Phase 3 — consolidate the intermediate representations**
1. Collapse `scene_plan` / `asset_intent` / primitive `spec` / construction
   graph (bridged today by `_scene_plan_from_asset_intent`,
   `normalize_spec`, `derive_spec_from_scene_plan`,
   `services/studio_chat.py:3911-4106`) into one canonical representation,
   now that Phase 1 removed the code that made four representations seem
   necessary.
2. Break up the 828-line `compile_studio_chat_build_pipeline`
   (`services/studio_chat.py:2272-3100`) into composable stages as part
   of this pass, once the shape of the single canonical representation is
   settled.

**Phase 4 — replace milestone-count with a real product metric**
1. Define a fixed benchmark set of creative prompts and track actual
   rendered output variety/detail across them as the progress signal,
   replacing "how many milestones shipped."
2. Re-run this benchmark after Phase 2 specifically, since that's the
   phase making a measurable claim about output quality — it needs a
   before/after to prove out.

**Explicitly out of scope for this plan:** no MCP protocol adoption for
OEB's own API (section 5 treated this as additive-only, not urgent), no
routing the Blender build path through Blender's MCP server (sections 3-4),
no changes to the production layer — threads, canonical assets, revisions,
build-job orchestration, milestones (inventory rows 4-6, 16-27) — none of
which bear on the boxy-primitives problem this plan addresses.

## 10. Phase 0-2 execution results, and why Phase 3 stopped at a plan

Phases 0-2 from section 9 were implemented and verified (not just planned).
Summary, full detail in commit-ready working-tree diffs:

- **Phase 0:** Auth gap confirmed real via cross-router audit (34/35
  `studio_chat.py` endpoints unauthed vs. ~100% coverage on every other
  data-mutating router). Left unauthenticated per explicit decision — no
  client-side token mechanism exists anywhere in this app, so adding auth
  blind would break the working local UI. Added a scoped `PROJECT-TODO.md`
  entry instead of code changes. Also located and documented the
  `oeb-studio-harness-local` Docker test stack (sibling
  `Orlando-El-Bastardo.docker/`, intentionally kept out of this repo) and
  fixed an absolute-path bug in `test_primitive_builder_routing.py` that
  made 23 tests uncollectible outside that container.
- **Phase 1:** Found a third duplicate heuristic-layer copy in
  `routers/conversations.py` (byte-identical to `services/studio_chat.py`)
  not accounted for in the original plan. Consolidated it to import the
  canonical implementation. `tools/studio_chat.py`'s copy stays separate by
  necessity (stdlib-only CLI, no FastAPI dependency) but a real bug was
  found and fixed there during the drift-check: an undefined-variable
  `NameError` in the motorcycle-detection branch.
- **Phase 2:** Corrected the plan's own diagnosis first — the LLM prompt
  (`scene_plan_prompt`) was already rich, not the bottleneck. The actual
  gap: `scene_object_category()` discarded the LLM's own structured
  `category` field (`seating`/`storage`/`bed`, from the same schema) for
  entire object classes, falling back to guessing from label text even
  though `make_chair`/`make_cabinet`/`make_bed` already existed. Wired the
  category directly to those recipes. Verified with real headless Blender
  (not just mocked tests): a `storage`-category object with a label
  containing no recognizable keyword now correctly builds the 3-part
  cabinet mesh instead of a generic cube.
- Test baseline throughout: 268/268 to start (after fixing the path bug),
  270/270 by the end, run against real Postgres in the Docker stack, not
  just mocked units.

**Phase 3 was investigated, not executed, and that was a deliberate stop,
not a stall.** Before touching `compile_studio_chat_build_pipeline` or the
four intermediate representations, checked how contained the blast radius
actually is:

- `StudioChatAsset.state_json` (`app/models/studio_chat.py:118`) stores
  asset state as an opaque JSON blob in the real database. Existing rows
  already contain whatever internal shape (`scene_plan`/`asset_intent`/
  `construction_graph`) was current at write time. Changing that internal
  shape is a **data-migration-class change** for already-existing assets,
  not a pure code refactor — this wasn't visible from reading the service
  code alone.
- `studio_chat.js` reads `stateJson.asset_intent` directly (line 928-929)
  and `parsed.asset_intent` elsewhere (8 total references to these field
  names). Consolidating representations means frontend changes too.
- `compile_studio_chat_build_pipeline` has roughly 19 distinct early-return
  points, each constructing a diagnostic-laden `StudioChatBuildPipelineResult`
  at a different pipeline stage (ingestion, intent routing, asset-intent
  normalization ×2, hierarchy planning, geometry inspection, resolver
  repair ×2-3, spec compilation, validation, success), threading ~15 local
  variables across them. Splitting it is feasible in principle — the
  return points already mark natural stage boundaries — but doing it
  correctly requires reading and understanding all 828 lines in full and
  preserving every branch's exact diagnostic output, not a mechanical
  split.

Given those three findings together (DB migration exposure, frontend
coupling, and a stage-split that needs full-function comprehension before
a single edit), this is a different risk tier than Phases 0-2: closer to a
dedicated migration project than a cleanup pass. Attempting it in the same
sweep as 0-2 risked exactly the kind of rushed, hard-to-verify change this
whole review pushed back on in section 7. Recommend treating Phase 3 as
its own explicitly-scoped effort — likely: (a) design the single canonical
representation and a `state_json` migration/back-compat strategy first,
(b) update `studio_chat.js`'s field reads to match, (c) only then split
the pipeline function against the new, settled shape — rather than folding
it into this pass.

Phase 4 (benchmark prompt set) does not depend on Phase 3 and was done
separately — see
[Studio Chat Visual-Variety Benchmark](benchmarks/STUDIO-CHAT-VISUAL-VARIETY-BENCHMARK.md).
Built `tools/studio_chat_benchmark.py` (a fixed 8-prompt set run against
the real live harness — real LLM, real resolver, real worker, real
Blender, not mocked) and ran a real baseline against the actual running
`oeb-studio-harness-local` stack: 8/8 completed, 38 total primitives, but
**only 3 distinct primitive kinds (Cube/Cylinder/Sphere) appeared across
all 8 prompts** — no Cone/Torus/wedge/hemisphere anywhere, confirming
section 8's finding with real numbers. This is now the number future
geometry-coverage work should move, tracked in an append-only
`docs/planning/benchmarks/results.jsonl`.

## 11. Design plan — unified operation-vocabulary model (supersedes Phase 3 as scoped)

Follow-up to sections 7-8 and the "product or circles" verdict: the two
product paths on `oeb-studio-harness` are the production teleplay-to-render
pipeline (in strong shape — GPU farming across `render-mac-01`/
`render-pc-01` is a real win) and Studio Chat as a conversational asset
builder. Decision: focus effort on the conversational path, specifically on
getting the local LLM to carry more of the load that today is done by
hand-rolled heuristics or frontier-model escalation for what should be
simple builds/edits — "move that back," "add an oblong" should not require
new hardcoded shape functions or a frontier-model round trip.

Three scoping decisions were made before drafting this plan:

1. **Both the creation and edit paths together**, not one first — they
   likely share the same underlying representation, so solving one without
   the other risks solving it twice.
2. **Expand the tool/operation vocabulary** — a richer but still fixed,
   schema-validated set of operations (combine, boolean, bevel, array,
   mirror — not just "create primitive"), explicitly *not* free-form code
   generation. This session's Blender MCP research (sections 3-4) found
   that unrestricted `exec()`-based code execution is the exact risk both
   the official and community Blender MCP servers carry with no real
   guard; Studio Chat's zero-code-execution design (function inventory
   criterion 4) is a real strength to preserve, not a limitation to lift.
3. **This absorbs/supersedes Phase 3 as scoped in section 10**, rather than
   running alongside the existing four representations — a new operation
   vocabulary sitting on top of `scene_plan`/`asset_intent`/primitive
   `spec`/`construction_graph` would just be a fifth representation. The
   representation consolidation Phase 3 flagged as needed now has an actual
   reason to happen, and a concrete target shape to consolidate toward.

### Anchor point — this finishes a stated direction, it doesn't invent one

`OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md` already carries this as a Decision:
*"The generic semantic graph and headless operation compiler are the
canonical editable core; primitive geometry is a derived worker
projection."* `Orlando-El-Bastardo.src/docs/ARCHITECTURE.md` already
specifies the MCP-style split of resources (scene summary, part catalog,
constraints) from tools (inspect, propose, validate, apply, undo, render).
Roadmap Milestone 16 already partially built this — `POST
/assets/{asset_id}/operations/propose|validate|apply` already exist
(`routers/studio_chat.py:2165-2212`). This plan proposes finishing that
line of work, not replacing it.

### Core idea

Stop asking the LLM to fill a *document* (`scene_plan`/`asset_intent`)
that a compiler then interprets. Ask it to propose a *sequence of
operations* against a semantic graph — the same graph whether building
fresh or editing. Creation is operations against an empty graph. Editing
is operations against an existing graph with `base_revision` (the
optimistic-concurrency field already in use for asset edits). This is the
literal mechanism that unifies the two paths per decision 1 above.

### Operation vocabulary (v1 proposal)

Each operation is a named, schema-validated function — never LLM-authored
code, matching decision 2:

- **Structural** (already exist): `add_part`, `remove_part`,
  `retarget_part`
- **Transform**: `set_transform` (location/rotation/scale, relative or
  absolute) — covers "move that back"
- **Shape**: `set_primitive_type`, `set_dimensions`, `set_shape_detail`
  (`corner_style`/`edge_profile` → real bevel/subsurf modifiers, closing
  the gap section 8/10 already identified: these fields are captured from
  the LLM today and discarded) — covers "add an oblong" as a box with
  non-uniform dimensions, no new shape function required
- **Composition**: `combine` (boolean union/subtract/intersect),
  `array_along_axis`, `mirror` — the actual unlock for symmetric/repeated
  parts (four legs, two wings) without a bespoke `make_X` recipe function
  per object type
- **Material**: `set_material` (color/finish/roughness — currently
  captured and discarded, same as the shape fields)

New object *types* stop requiring new Python recipe functions once this
lands — they become compositions of the fixed vocabulary above. That is
the concrete mechanism for "not every shape explained in code ahead of
time."

### How the LLM drives it

Reuse the propose → validate → repair retry loop already proven in
`resolve_primitive_spec` (`services/studio_chat.py:1555-1631`) rather than
inventing a new interaction pattern. The LLM proposes an operation
sequence; the server validates each operation against its schema and the
current graph state; invalid operations trigger a bounded repair prompt
back to the LLM. Never falls back to keyword-guessing — the heuristic
layer stays cut per Phase 1.

### Representation consolidation

- The semantic graph (parts + relationships + per-part shape/material/
  transform) becomes the one canonical representation, replacing
  `scene_plan`/`asset_intent`/primitive `spec`/`construction_graph`.
- `StudioChatAsset.state_json` (`app/models/studio_chat.py:118`) is an
  opaque JSON blob in the real Postgres database today — add a
  `schema_version` field and a compatibility read-path rather than a bulk
  migration. Old assets keep working under the old shape; new writes use
  the new graph shape. This directly addresses the data-migration-class
  risk section 10 flagged, without requiring a risky one-shot migration.
- `studio_chat.js`'s 8 hardcoded reads of `asset_intent`/`scene_plan`
  fields get updated to the new shape as part of this work, not as an
  afterthought discovered later.
- `compile_studio_chat_build_pipeline`'s 828 lines and ~19 diagnostic
  early-return branches (section 10) get split along the new pipeline
  stages (propose → validate → apply → compile-to-Blender) once this
  shape is settled — section 10 blocked the split specifically on
  "settle the shape first," which this plan does.

### Geometry realization

**Amended by section 12 — see below.** This subsection originally scoped
geometry realization to `tools/primitive_asset_builder.py` only (Blender
via the Studio Chat worker path). Section 12 revises this: Blueprint
execution should route through the existing multi-target exporters
(`export_blender.py`/`export_usd.py`/`export_godot.py`) instead. Left
as-written below for the historical record of what was originally
proposed.

`tools/primitive_asset_builder.py` gains a generic operation compiler —
one function per vocabulary operation (`apply_combine`, `apply_array`,
`apply_bevel`, etc.) — alongside, not replacing, the existing
`make_chair`/`make_table_like`-style recipes (kept as fast paths for
common furniture; the graph can still invoke them as shorthand). This is
where real bevel/subsurf modifiers replace the currently-discarded style
fields.

### Measuring progress

`tools/studio_chat_benchmark.py` (built in Phase 4, section 10) gets
extended to also track *distinct operation types used* per build, not
just primitive kind. Re-run the existing 8-prompt baseline
(`docs/planning/benchmarks/results.jsonl`) after each phase below — the
number to move is the one already captured: 3 distinct primitive kinds
across all 8 baseline prompts.

### Phasing (multi-session, staged — not a single sweep)

1. Finalize the operation vocabulary schema (spec only, no code) against
   the existing graph-operation endpoints.
2. Implement server-side validate/apply for the new operations, extending
   the existing propose/validate/apply contract.
3. Implement Blender-side realization for each operation in
   `tools/primitive_asset_builder.py`.
4. Point the LLM prompts at operation-sequence proposals, reusing the
   existing repair-loop machinery.
5. Add `schema_version` + compatibility read-path to `state_json`; update
   `studio_chat.js`'s 8 read sites.
6. Split `compile_studio_chat_build_pipeline` along the now-settled stage
   boundaries.
7. Re-run the benchmark; compare against the baseline in section 10.
8. Retire the old four representations and the remaining heuristic
   fallback once the benchmark and a burn-in period confirm parity or
   improvement.

## 12. Studio ontology (from the cousin's planning) and reconciliation with section 11

The user relayed extended planning discussion establishing a permanent
studio vocabulary for the conversational 3D production studio. Recorded
here verbatim in substance, then reconciled against the section 11 plan.

### The architecture principle

Creative intelligence and deterministic construction are cleanly
separated by model role, not by treating every model as equally capable
at every task:

- **Frontier models**: imagination, concept development, artistic
  direction, novel design problems.
- **Local models**: engineering assistants — building, assembling,
  validating, and repairing assets once creative direction is set.
- **The studio harness**: authoritative scheduler — decides what work
  happens, which model handles it, validates results, and determines when
  human review or frontier escalation is needed.

Key claim: local models don't need frontier-level reasoning to generate
sophisticated programmatic geometry. Success depends far more on the
*environment* — narrow assignments, authoritative context, typed outputs,
deterministic tools, executable feedback, known-good examples, controlled
repair loops — than on raw model intelligence. This directly matches the
propose → validate → repair loop pattern already proven in
`resolve_primitive_spec` and reused throughout section 11.

### Abandoning the Shape Library

Enumerating finished shapes (a growing catalog of named objects) fails as
soon as an undefined variation appears — "a half sphere" breaks a
100-shape library the same way it breaks a 10-shape one. The fix isn't a
bigger catalog; it's treating geometry as *mathematical construction*
rather than a collection of finished objects. A half sphere isn't a
unique stored asset — it's a sphere, then a bisect operation, then a cap
operation. This is the same conclusion section 8's audit reached from the
code side (`_compile_typed_object_primitives` discarding style fields;
`scene_object_category` only routing a closed set of named categories to
bespoke recipe functions) — independently arrived at from the
architecture-planning side. The 1990s original Orlando El Bastardo assets
(e.g. the Bugblatter Interceptor: three oblongs, a spline spine, three
circular engine sections, mirrored "P"-derived wing profiles, a "U"-shaped
tail) are cited as precedent: sophistication came from composition and
proportion, not a large custom-geometry catalog.

### Permanent vocabulary

- **Primitive** — a mathematical definition (sphere, cylinder, curve,
  plane), described through parameters, not stored as a file.
- **Operation** — a deterministic transformation (extrude, bevel, bisect,
  mirror, boolean, loft, sweep) that modifies or combines primitives.
- **Blueprint** — replaces "Recipe." A portable construction spec
  recording design intent: primitives, operations, dimensions,
  relationships, attachment points, material regions, constraints,
  semantic names, validation expectations. Intentionally independent of
  Blender, USD, Godot, or any future rendering platform.
- **Canonical Asset** — the approved master realization of a Blueprint,
  authoritative after artistic review; may carry topology, UVs, rigging,
  materials, and other production-specific work that shouldn't be
  regenerated per use.
- **Production Variant** — an optimized implementation of a Canonical
  Asset for a specific renderer/engine/platform/polygon budget.
- **Render Artifact** — temporary output: rendered frames, baked sims,
  caches, exports, previews, compiled data.

Guiding statement: *"At the center of every 3D model are mathematics and
language. Mathematics defines what can exist. Language defines what is
intended. Blueprints connect the two by describing mathematical
constructions in human terms so that any compatible builder can
deterministically realize the same creative vision."*

### Reconciliation with section 11 — three decisions

1. **Blueprint execution integrates with the existing multi-target
   exporters** (`export_blender.py` / `export_usd.py` / `export_godot.py`
   — the same exporters the main teleplay-to-render production pipeline
   already uses against `SceneSpec`), not a Blender-only path via
   `tools/primitive_asset_builder.py` as section 11 originally scoped
   (see the amendment note on that section's "Geometry realization"
   subsection above). **Corrected and scoped in detail in section 13** —
   the exporters turned out to be scene *assemblers* that reference
   already-built `.glb` assets, not asset builders, so the integration is
   "Blueprint execution produces assets the exporters already know how to
   consume" rather than literal code changes inside the three exporters.
   Section 11's "Operation vocabulary" and "propose → validate → repair"
   design stand as written; section 13 corrects and scopes the realization
   target.
2. **Canonical Asset reframes the existing Milestone system** rather than
   introducing a new parallel approval mechanism. A Milestone becoming a
   Canonical Asset is a promotion/labeling concern on top of the existing
   snapshot mechanism (`StudioChatMilestone`, inventory row 27), not new
   schema built from scratch.
3. **Scope stays split.** Section 11 (operation vocabulary +
   `scene_plan`/`asset_intent`/spec/`construction_graph` consolidation)
   remains the near-term plan, now amended per decision 1 above. The full
   Canonical Asset / Production Variant / Render Artifact lifecycle
   (promotion workflow, per-platform variant generation) is recorded here
   as direction and context, not folded into section 11's phasing — it is
   its own later-phased initiative, to be scoped explicitly when picked
   up.

### Mapping table (this project's existing terms → the permanent vocabulary)

| Ontology term | Closest existing thing today |
|---|---|
| Primitive | `PRIMITIVE_REGISTRY_V01` (`services/studio_chat.py`) / primitive types in `tools/primitive_asset_builder.py` |
| Operation | Section 11's proposed operation vocabulary (`set_transform`, `combine`, `array_along_axis`, `set_shape_detail`, etc.) plus the existing `POST /assets/{id}/operations/*` endpoints |
| Blueprint | Section 11's target canonical representation (replacing `scene_plan`/`asset_intent`/spec/`construction_graph`) — renderer-agnostic input to the new Blueprint interpreter scoped in section 13, not itself shaped like `SceneSpec` (see section 13 correction) |
| Canonical Asset | `StudioChatMilestone`, reframed per decision 2; artifact shape is the existing but unpopulated `StudioChatAsset.source_blend_path` + `.glb_path` pair (section 13) |
| Production Variant | The `.glb` a Blueprint interpreter emits, already the common currency all three exporters consume today (confirmed in section 13) — `.usdc`/Godot `PackedScene` are derived from it by the existing exporters, not built separately |
| Render Artifact | `Artifact` model / `artifact_type: "asset_build"` records already in use (confirmed via the section 10 benchmark run's real job output) |

## 13. Detailed scope — Blueprint/exporter integration (corrects section 12 decision 1)

Requested detailed scoping of section 12's decision 1. Investigating the
actual exporter code before writing this scope overturned part of that
decision's premise — recorded here rather than silently revised in place,
same convention as the section 11 amendment.

### The correction

`export_blender.py`, `export_usd.py`, and `export_godot.py` do not build
geometry from a spec. They are scene *assemblers*. Confirmed directly from
source:

- `SceneSpec`'s schema (`schemas/scenespec.schema.json`) has
  `ActorSpec.character_id` and `SetSpec.set_id` as plain string references
  — `"Character asset ID (e.g. char_hero_v1)"` — not embedded geometry.
- `export_blender.py:284` calls
  `bpy.ops.import_scene.gltf(filepath=glb_path)` — it imports a pre-built
  `.glb`, it does not construct one.
- `export_usd.py` maps `rel_glb → abs_usdc_path` (`_collect_distinct_files`,
  the `stage = Usd.Stage.CreateNew(...)` flow) — it converts existing
  `.glb` files to `.usdc`.
- `export_godot.py` references `.glb` files directly as `PackedScene`
  resources in the generated `.tscn` (`_make_tscn`, `glb_basename`).

**glTF (`.glb`) is already the one common asset currency all three
exporters consume.** None of them contain construction logic for a
Blueprint interpreter to plug into. There is also no existing general
"build an asset from a construction spec" engine anywhere in the main
production pipeline to model this on: `tools/resolve_intent.py` is
scene-composition-level (`SceneIntent → SceneSpec`, same abstraction as
the exporters); `tools/make_placeholders.py` is bespoke per-canonical-ID
grey-box code — the exact Shape Library anti-pattern section 12 rejects,
not a reusable interpreter. `tools/primitive_asset_builder.py` (Studio
Chat's own) is the only construction-from-spec engine that exists today,
anywhere in this codebase.

### Corrected architecture

Blueprint execution is a **new, separate build stage**, not a
modification to the three exporters. It produces a Canonical Asset as a
`.glb`, registered under a canonical ID, exactly like an artist-made asset
would be. The exporters then consume it unchanged, through the reference
mechanism they already have. Blueprint-built and artist-built assets
become indistinguishable to the scene-assembly layer — which is a cleaner
integration than editing exporter code would have been.

### Concrete scope

1. **A Blueprint interpreter — IMPLEMENTED (v0.1), verified live.** Built
   as `tools/blueprint_interpreter.py`: a standalone shared engine, not
   folded into `tools/primitive_asset_builder.py` — it imports primitive
   creation from a newly-extracted `tools/oeb_blender/primitives.py` that
   both tools now share, rather than duplicating that code a third time.
   Headless Blender is the runtime, as planned. v0.1 operation vocabulary
   is intentionally narrower than the full ontology list: `bevel`,
   `mirror`, `array` (native Blender modifiers, add + apply) — `boolean`,
   `bisect`, `extrude`, `loft`/`sweep` are documented as deferred future
   work in the file's own docstring, added one at a time via the same
   `_apply_<op>` pattern as needed, not built speculatively. Verified with
   a real headless Blender run, not just the 8 mocked unit tests in
   `test_blueprint_interpreter.py`: a cube with `bevel`+`mirror` applied
   came out to 768 verts/376 faces versus a bare cube's 8/6, and a
   cylinder with `array` (count 3) came out to 576 verts/372 faces —
   confirming the modifiers actually baked into the exported geometry,
   not just recorded as metadata. Full suite 278/278 (host + Docker).
   Caught and fixed a real ordering bug while writing tests: material
   creation ran before primitive-type validation, so an unknown type
   still fired a real `bpy` call before raising.

   **Not yet wired up.** The interpreter exists and works standalone but
   nothing calls it yet — Studio Chat's actual build path still runs
   through `tools/primitive_asset_builder.py`, unchanged. Connecting the
   two (having Studio Chat emit a Blueprint instead of a primitive spec,
   or routing new builds through the interpreter) is a separate decision,
   not yet made or scoped in this document.
2. **Dual artifact output, not just glTF — satisfied by the new
   interpreter, not by Studio Chat's existing builder.** `StudioChatAsset`
   already has both `source_blend_path` and `glb_path` columns
   (`app/models/studio_chat.py:119-120`) — this exact pattern (editable
   Blender source + portable glTF Production Variant) was anticipated in
   the schema but, before this pass, populated by nothing general-purpose.
   `tools/blueprint_interpreter.py` now writes both on every build: the
   `.blend` as the editable Canonical Asset, the `.glb` as the Production
   Variant the exporters consume — verified as a valid Blender 5 file in
   the same live test run above. `tools/primitive_asset_builder.py`
   (Studio Chat's own builder) still only produces a `.glb`; this item is
   closed for the new interpreter, not retrofitted onto the old one.
3. **Canonical-ID reconciliation.** Studio Chat's `canonical_id` scheme
   (`kind_description_A` slugs) and the main pipeline's asset-ID scheme
   (`character_id`/`set_id`/prop IDs referenced by `SceneSpec`) need to
   resolve to the same registry, or Blueprint-built assets can't be placed
   into a production `SceneSpec` at all. This is real integration work,
   not a naming convention. **Investigated and scoped in section 14** —
   turned out narrower than "known dependency": the two ID schemes are
   already the same shape, this is a missing registration step, not a
   redesign.
4. **USD-native construction is explicitly out of scope for v1.** Build
   once via the Blender path; let `export_usd.py`'s existing glb→usdc
   conversion carry it, same as everything else. Only reconsider direct
   USD construction if a real need surfaces that Blender's operator set
   can't express — don't build a second Blueprint interpreter
   speculatively.
5. **No changes needed to `export_blender.py`/`export_usd.py`/
   `export_godot.py` themselves** — they already do exactly the
   reference-and-assemble job this requires.

### Revised section-11 phase 3

Original phase 3 text: *"Implement Blender-side realization for each
operation in `tools/primitive_asset_builder.py`."* Corrected: build the
Blueprint interpreter as a standalone headless-Blender tool producing
`.blend` + `.glb` per Canonical Asset, register it through whatever
canonical-ID system item 3 above resolves on, and leave the three
exporters untouched. This is a larger, more clearly-bounded piece of work
than the original phase 3 line implied — closer to "build a new
production-pipeline stage" than "extend one Studio Chat script." Section
11's phases 1-2 and 4-8 are unaffected by this correction.

## 14. Realignment — closing the canonical-ID/registry dependency now

The user flagged (correctly) that section 13's exporter scoping pulled the
production pipeline into what was meant to be a conversational-asset-
creation-focused effort, and asked to address that specific dependency now
rather than let it ride as an assumed prerequisite. Investigated
`tools/validate_spec.py` and `oeb.config.json` (both previously flagged as
"not yet read" in section 13 item 3) before writing this plan.

### Finding: it's a missing registration step, not a scheme mismatch

`oeb.config.json`'s `assets` map is the **entire** main-pipeline asset
registry — a small (9 entries as of this writing), git-tracked, hand-edited
JSON file: `canonical_id → {file, node, kind[, skeleton]}`. Example:

```json
"set_bar_small_A": {"file": "sets/bar_scene_scifi.glb", "node": "set_bar_small_A", "kind": "set"}
```

`tools/validate_spec.py` validates `SceneSpec.set.set_id` and
`actors[].character_id` against this map's keys as hard errors, and prop
`asset_id` as a warning (`_run_checks`, lines ~243-271). No writer script
was found among the tools that reference this file (`tickets.py`,
`export_usd.py`, `script_desk.py`, `validate_spec.py`, `export_godot.py`,
`producer.py`, `export_blender.py`, `resolve_intent.py`) — git history
shows entries added by hand-authored commits (e.g. "JB5K/JB100 ships +
design doc"). Registration is manual today.

**The good news:** Studio Chat's `canonical_id` slugs
(`prop_round_dining_table_rounded_A`, `vehicle_two_wheeled_motorcycle_low_A`
— real examples from the section 10 benchmark run) are already the exact
same shape as the registry's existing keys (`prop_bar_counter_A`,
`prop_stool_A`). This is not a naming-scheme reconciliation problem. It's
a missing *registration* step — nothing writes Studio Chat's finished
assets into `oeb.config.json`, so the main pipeline simply doesn't know
they exist yet.

The `node` field in every existing registry entry equals the `canonical_id`
itself (`set_bar_small_A` → node `"set_bar_small_A"`) — a convention, not
a coincidence across all 9 entries. If the Blueprint interpreter (section
13) names its glTF root node after the `canonical_id` it's building, the
`node` field can be populated automatically with zero guessing.

### Kind-taxonomy mismatch — RESOLVED

`oeb.config.json` only recognizes three `kind` values:
`prop`/`character`/`set`. Studio Chat's own kind inference
(`infer_kind`/`slug_kind_prefix`, `services/studio_chat.py`) produces a
wider set: `asset`/`location`/`prop`/`vehicle`/`character`/`set` (plus the
`ship_` canonical-ID prefix as a special case of vehicle). Resolved by
direct code search across all three exporters: `kind` is not read by
`export_blender.py`, `export_godot.py`, or `export_usd.py` at all — none
of them branch on it. The only downstream consumer was
`tools/validate_spec.py`'s V8 `unknown_audio` check (`kind == 'audio'`),
which has since been removed (audio isn't part of the studio yet; its two
dangling references in `tools/tickets.py` and
`schemas/validationreport.schema.json` were cleaned up in the same pass —
see the "Remove unused audio validator" commit). With that gone, `kind` is
purely descriptive registry metadata with no exporter behavior riding on
it, so the mapping is final, not provisional:

- `location` → `set` (conceptually the same thing under a different name)
- `vehicle`/`ship`/generic `asset` → `prop` — confirmed safe; no exporter
  treats vehicles differently from static props, since none of them
  consult `kind` at all
- `character` → `character` (already aligned)

### Plan

1. **Build a registration step** — this is literally "asset promotion,"
   the term used in the very first message that started this whole review
   (OEB's owned production concerns: "canonical asset identity; Blueprint
   execution; ...; asset promotion; ...") and echoed in the Canonical
   Asset definition in section 12. Given a Studio Chat Canonical Asset
   (`canonical_id`, `.glb` path, kind), it writes/updates the matching
   entry in `oeb.config.json`'s `assets` map, applying the kind mapping
   above.
2. **RESOLVED** — confirmed `kind` is not consumed downstream by any
   exporter; `vehicle`/`ship` register as `prop`, no separate registry
   `kind` value needed. See "Kind-taxonomy mismatch — RESOLVED" above.
3. **Respect the git-read-only rule.** `oeb.config.json` is git-tracked.
   The registration step writes the file; it does not commit it — same
   pattern as every other change made this session. Given the Canonical
   Asset definition explicitly requires "artistic review" before an asset
   becomes authoritative, this also naturally gates registration behind a
   human reviewing and committing the updated config, not an unattended
   write.
4. **Sequencing** — pull this forward as an explicit early item in section
   13's phasing (originally item 3, "known dependency, not yet scoped");
   it's now substantially de-risked and should be built alongside or just
   before the Blueprint interpreter itself, since the interpreter's glTF
   root-node naming convention (finding above) needs to be correct from
   the start for registration to be automatic later rather than
   retrofitted.

This closes the dependency identified in the prior exchange: Blueprint
execution (section 13) and this registration step together are what let a
Studio Chat–built asset actually appear in a production `SceneSpec`, with
no scheme redesign required — just new code + a resolved kind mapping.

## 15. Registration step built and verified, plus a real bug found and proposed fix

Section 14 plan item 1 was executed, not just planned:
`tools/register_studio_chat_asset.py`. Given a Studio Chat `canonical_id`,
it finds the asset's current-revision build job, locates the job's `.glb`
artifact, downloads it into `assets/<kind>/`, and registers the entry in
`oeb.config.json` with the finalized kind mapping from section 14
(`location`/`set_` → `set`, `character`/`char_` → `character`, everything
else → `prop`). It does not touch git — write only, human commits, per the
Canonical Asset "artistic review" gate already established in section 12
decision 2.

Verified for real, not just by reading code: created a live Studio Chat
thread, submitted a real build job through the actual running pipeline,
waited for the real worker to complete it, then ran the script against
that real asset (`prop_wooden_stool_A`) — it correctly derived `kind`,
downloaded a real 169KB `.glb`, and wrote a correct registry entry. That
test registration was then reverted (file removed, `oeb.config.json`
restored) since it was a verification run, not a real asset the user
asked to register.

### Bug found while building it: `glb_path`/`source_blend_path` are never resolved

The script does **not** read `StudioChatAsset.glb_path` /
`source_blend_path` directly, despite section 13 item 2 proposing exactly
those columns as the dual-artifact source. Root cause, confirmed by
tracing the actual call sites: `_upsert_asset_state_from_build` (which
writes those columns) is called exactly once, at job-*creation* time,
from `create_studio_chat_build_job`
(`app/routers/studio_chat.py:2889`), using a payload built by
`app.routers.conversations._build_job_payload`. That payload's
`artifact_paths` contain a **literal, unsubstituted `"{job_id}"` path
template** — the real job ID doesn't exist to substitute in yet at
creation time, and nothing ever revisits these columns after the job
actually completes and real files exist. The columns are not usable as
stored today.

The script instead walks the reliable path: asset → current revision →
`StudioChatAssetRevision.job_id` (a real foreign key, already present in
the schema) → that job's trace → the real `Artifact.storage_path` /
`review_url`, which are correctly resolved because `Artifact` rows are
only created after a job actually finishes.

### Fix — IMPLEMENTED and verified live

`app/routers/jobs.py`'s generic `complete_job` handler (line 452) already
had a precedent for job-type-specific post-completion logic: it
special-cases `job.payload.get("job_type") == "asset.review_render"`
(line 488) to compute gallery readiness once real artifacts exist. Added a
parallel helper, `_sync_studio_chat_asset_paths_from_artifacts`, called
right after `job.status = "completed"` is set:

1. Queries `StudioChatAssetRevision` where `job_id == job.id`. A match
   means this job built/edited a Studio Chat asset; no match returns
   immediately (most jobs aren't Studio Chat builds).
2. Queries that job's real `Artifact` rows (same pattern already used for
   the review-render branch) and finds the `.glb` (and `.blend`, if
   present) by filename suffix.
3. Overwrites `revision.glb_path` / `revision.source_blend_path` with the
   artifact's real, resolved `storage_path`, replacing the stale
   `{job_id}`-template string.
4. If `revision.revision == asset.current_revision` (this build wasn't
   superseded by something else before finishing), also updates the
   parent `StudioChatAsset.glb_path` / `.source_blend_path` to match.

**Verified live, not just by test suite:** submitted a real build job
through the actual thread pipeline, waited for the real worker to
complete it, then checked both the revision and the asset's current
state. Before the fix, `glb_path` held the literal string
`"{job_id}/..."`. After: a real resolved path with the actual job UUID —
e.g. `/srv/oeb-studio-harness/artifacts/622b5cd9-.../prop_test_fix_stool_A.glb`
— on both the revision record and the parent asset (only updated because
that revision was still current, confirming the guard in step 4 works).
`source_blend_path` correctly stayed `None` for this build, since no
`.blend` artifact was produced. Full suite: 270/270, host and Docker.

**Nuance carried into the implementation, documented in the function's own
docstring:** `Artifact.storage_path` is a path inside the `artifacts`
Docker named volume (`/srv/oeb-studio-harness/artifacts/...`) — correct
from inside the container, but not directly readable from the host
(confirmed while building the registration script above; it is a named
volume, not a bind mount). Storing `storage_path` in `glb_path` fixes it
for server-side/in-container consumers; host-side tools should keep using
`Artifact.review_url` over HTTP the way
`register_studio_chat_asset.py` already does, not read `glb_path`
directly.

## 16. Blueprint job wiring, resolver symmetry, and "no tension between the two product paths"

### Blueprint interpreter wired to run as a real harness job

`tools/submit_blueprint_job.py` (new): submits a Blueprint to
`POST /api/v1/jobs`, the generic job-creation endpoint, with a payload
pointing at `tools/blueprint_interpreter.py`. No server-side changes were
needed — the endpoint already accepts an arbitrary `payload` dict, and the
worker's `BlenderCLIAdapter` already runs any `script_file`/`script_args`
generically, the same mechanism `tools/primitive_asset_builder.py` already
runs through. Verified live: submitted a real Blueprint job, the real
`render-mac-01` worker picked it up and completed it, producing genuine
`Artifact` rows — `.glb` (8.7KB), `.blend` (97KB), manifest (578B) — not
simulated.

This surfaced a real gap: `register_studio_chat_asset.py` locates a job
via `StudioChatAssetRevision.job_id`, but a job submitted directly through
`submit_blueprint_job.py` has no such row (confirmed empty via direct DB
query) — Studio Chat's tables only get populated by its own thread/
build-job flow. Blueprint jobs and the registration script don't connect
yet.

### Resolver design correction: symmetric inputs, not a bypass

Initial framing of the fix — add a `--job-id` "alternate entry point" that
bypasses the `StudioChatAssetRevision` lookup — was itself wrong, called
out directly: it implicitly treated `--asset-id` as the "real" path and
`--job-id` as a workaround bolted onto it. Corrected design: the script
fundamentally needs a `(job_id, canonical_id, kind_hint)` tuple before the
shared work (find artifact, download, register) can run. There are (at
least) two legitimate, equally-weighted ways to produce that tuple —
resolve via a Studio Chat asset's current revision, or resolve via a
directly-submitted job's own payload (`submit_blueprint_job.py` already
embeds `payload.blueprint.canonical_id` for exactly this) — and more may
exist later as other job types produce registrable builds. `--asset-id`
and `--job-id` should be implemented as two independent, first-class,
mutually exclusive resolvers that both feed the same shared downstream
pipeline, not a primary path with a special case attached.

**IMPLEMENTED and verified live.** `--asset-id`/`--job-id` are now an
argparse mutually-exclusive group (errors if neither or both are given),
each resolving to the same `BuildResolution(job_id, canonical_id,
source_revision)` tuple consumed by the identical shared pipeline. Tested
against real data: `--asset-id prop_wooden_stool_A` resolved via its
current revision (job `c88e858e...`); `--job-id 2a0f3cb1-...` resolved
`prop_job_wiring_test_A` directly from `payload.blueprint.canonical_id` —
the exact case that was broken before, a job with no
`StudioChatAssetRevision` row at all, submitted via
`submit_blueprint_job.py`. Both produced identical registry-entry output.

### "No tension between the two product paths" — framing correction

Called out directly, and correct: recent sections narrated a false
tension — treating shared infrastructure work (Blueprint interpreter, job
wiring, registration) as "drift toward the production pipeline" away from
the conversational-creation priority. That framing doesn't hold up. Both
product paths terminate in the same place, a registered Canonical Asset:
the teleplay path gets there by resolving structured intent into a
`SceneSpec` that references assets by ID; the conversational path gets
there by an LLM proposing a Blueprint the interpreter builds. Different
front doors, same building. The bridge infrastructure isn't competing
with the conversational-creation goal — it's what makes a conversationally
built asset *matter* to the studio at all; without it, Studio Chat
produces disposable geometry nobody can use in a real scene. Going
forward, shared infrastructure work should not be flagged as tension or
drift between the two paths.

### What happens when Studio Chat is used to work on a scene?

Asked directly. Honest answer: nothing, today — the capability doesn't
exist. Studio Chat's entire ontology (Primitive → Operation → Blueprint →
Canonical Asset) is scoped to building or editing one asset. A scene —
actors placed in a set, cameras, shots, timing — is a `SceneSpec`, a
different, higher-level object that *references* Canonical Assets by ID;
nothing in Studio Chat today proposes, validates, or applies changes to
one.

The consistent extension, following the exact pattern already proven for
assets rather than inventing a new mechanism: `SceneSpec` becomes a second
target for the same propose → validate → apply loop. A scene-level
operation vocabulary — `place_actor`, `move_prop`, `adjust_camera`,
`add_shot` — sits alongside the Blueprint operation vocabulary from
section 11/13. Validation reuses `tools/validate_spec.py`'s existing rules
(already built, already used by the teleplay path — no new validator
needed). "Move the hero stage left" becomes a `place_actor` operation on
the current `SceneSpec`, the same shape as "move that back" being a
`set_transform` operation on the current Blueprint. This is recorded here
as the next real architectural extension once the asset-level Blueprint
loop is fully wired (per the standing priority decision in the section 11
follow-up discussion) — not yet scoped in detail, and not a separate
system from everything built in sections 11-16.

## 17. Scene-reconstruction diagnosis, reference-frame resolution, and the live-sandbox reconciliation

### Context: the OEB title-scene reconstruction (separate session)

A different session used a frontier model to reconstruct a scene from the
original 1999 OEB teaser: reviewing the source video and stills, producing
a free-form Markdown reconstruction plan (assets, placement, camera
choreography, timing), then hand-writing a ~750-line bespoke Blender
Python builder (`scene_versions/oeb_scene_title_v*/build_scene_title.py`)
from that plan, iterated by hand through several versions (0.0.5, 0.0.6),
debugged by rendering six orientation views and eyeballing them against
reference stills. That process surfaced a concrete bug — the logo's
rotation axis was near-vertical where the reference needs it closer to
horizontal/camera-facing, which is why the six orientation renders looked
so inconsistent and why a blind 180° flip only partially fixed the
framing — recorded here for continuity, not yet corrected in that scene's
builder.

### Question: can Studio Chat get robust enough to do this end-to-end?

Asked directly: can Studio Chat go from (reference stills + a source
video + text explanation) to a finished render, instead of requiring a
frontier-model session hand-writing a bespoke script per scene? Diagnosis,
confirmed point by point:

1. **Vision/interpretation is correctly frontier-model work** — watching
   video and inferring 3D camera paths from 2D stills is a "novel design
   problem" per the architecture principle (section 12), not a local-model
   gap. The missing piece is a defined hand-off: frontier model produces a
   *structured, typed* plan, not prose, and the deterministic local loop
   takes over from there.
2. **The frontier model's output has nowhere structured to land today** —
   it becomes a one-off hand-built script instead of a reusable
   construction (the Shape Library anti-pattern in different clothes).
3. **No camera/timeline representation exists anywhere** — neither the
   Blueprint schema (v0.1: primitives + bevel/mirror/array, no time axis)
   nor Studio Chat's asset model has any concept of camera keyframes, shot
   timing, or animation, despite this being a fundamentally cinematic
   task.
4. **No asset-import capability** — the Blueprint interpreter only
   creates primitives from scratch; this reconstruction needed to append
   existing assets (the logo's geometry, the JB100, a character).
5. **No automated reference-comparison loop** — render, eyeball against
   reference, describe the mismatch in English, hand-edit the script,
   repeat. No structured render-vs-reference diff feeding back as a
   repair operation.

All five confirmed. Resolution order agreed: (1) camera/timeline
operations first — root cause of "chaotic" camera moves and a
prerequisite for expressing any shot at all; (2) asset-import as a
Blueprint/scene component, reusing the reference-by-`canonical_id`
pattern `SceneSpec`'s `ActorSpec`/`PropSpec` already use, not a new
mechanism; (3) the typed reconstruction-plan schema the frontier model
fills, meaningful only once 1-2 exist to express it in; (4) the automated
render-vs-reference comparison/repair loop, the capstone, dependent on
1-3.

### Reference-frame resolution for relative conversational edits

Raised directly: "move the engine pods 10 centimeters forward" is only
meaningful once "forward" and "centimeter" are defined relative to
something. **Resolved: object-local axes by default** — matches OEB's
already-established orientation standard (e.g. JB100 nose = local -Y),
stays consistent regardless of camera angle, and is already the
convention used throughout the Blueprint/primitive work this session.
Camera/view-relative interpretation stays available as an explicit
override for requests that are genuinely about the view ("move it toward
camera"), not the default.

**Addendum — the "centimeter" half was not resolved with the same rigor
and needed its own pass.** Direction (object-local axes) doesn't answer
the harder problem: Blender's default unit is 1 Blender unit ≈ 1 meter,
but nothing guarantees that convention holds for what Studio Chat builds.
A primitive-built object at an arbitrary designer-judgment scale and an
imported asset like the JB100 don't necessarily share a common real-world
scale, and nothing in the v0.1 Blueprint schema (section 13) carries any
real-world dimension today. So "10 centimeters" is ambiguous per-asset
until something states the conversion.

**Resolved:** every Canonical Asset/Blueprint needs an explicit scale
reference — a `units_per_meter` field (or an equivalent real-world
dimension, e.g. "overall length = 4.2m") in its metadata. Real-world unit
commands convert through that field; if a Blueprint doesn't declare one,
default to Blender's native 1 unit = 1 meter convention rather than
silently guessing.

**IMPLEMENTED.** `units_per_meter` shipped in the same commit as the
Blueprint job-wiring work (`e7e010b`, "Blueprint job wiring + units") — it
is now part of the committed v0.1 Blueprint schema/manifest, not design
only. (This correction found during a 2026-08-07 status re-verification
pass; the doc previously said "Design only — not yet added to the
schema," which was stale as of that commit.)

### The live conversational sandbox proposal, and reconciling it with sections 3-4/13

From the cousin, a new proposal to eliminate the edit → export → render →
inspect cycle: keep Blender open as a persistent, authoritative scene
editor; an MCP server receives structured commands from ChatGPT or a
local model and modifies the live scene directly, capturing viewport
images only when visual confirmation is needed — ordinary modeling stays
inside the live viewport with no intermediate renders. For mobile access,
existing remote-desktop tooling (Sunshine on the workstation, Moonlight on
iPad/iPhone) streams the live Blender viewport over low-latency hardware
H.264, decoupled from the conversational command channel. Proposed
architecture: *Blender desktop session → Official Blender MCP Server →
OEB Studio harness → ChatGPT or local language model*, with the harness
remaining responsible for Blueprint execution, `SceneSpec`/`ShotSpec`
interpretation, canonical asset management, revision history, render
orchestration, and production workflow — Blender MCP providing
"standardized scene control rather than a custom protocol."

**That characterization predates this session's own findings and needed
reconciling.** Sections 3-4 and 13 installed and read the official Blender
MCP server's actual source: it has no named tool set at all — one generic
"execute arbitrary Python" operation, a `weak_sandbox.py` module whose own
docstring says it "isn't really a sandbox" (blocks exactly 5 things), and
Blender's own site carries an explicit warning that it runs LLM-generated
code with no real guard. "Standardized scene control" doesn't describe
what's actually there.

**Resolved, not by rejecting the proposal but by correcting the trust
model within it:**

1. **Harness-mediated, LLM never gets raw exec access.** The LLM proposes
   typed Operations from the vocabulary already being built (the same
   propose → validate → apply loop used throughout sections 11-16); the
   harness is the only thing that ever generates the actual Python sent
   through Blender MCP. This preserves the zero-code-execution-exposure
   property already established as a real strength (function inventory
   criterion 4) while still getting the live-session, no-relaunch benefit
   the proposal is actually after. Blender MCP becomes a transport the
   harness drives, not a tool surface the LLM talks to directly.
2. **The sandbox coexists with the headless job pipeline, doesn't replace
   it.** Live sandbox is for fast interactive iteration; an approved
   result still commits to a Canonical Asset through the deterministic
   path already built and verified this session
   (`tools/blueprint_interpreter.py` → job queue →
   `tools/register_studio_chat_asset.py`), so revision history and the
   asset registry stay intact. The live session and the headless
   interpreter should ultimately execute the same Operation vocabulary —
   one interactive, one batch — not two divergent code paths.

This makes the live-sandbox proposal an interactive front end onto the
same harness-mediated, typed-Operation architecture already underway, not
a competing system with a different, weaker trust model. Design only, at
the time this section was written — **section 18 below records that
camera/timeline operations and asset-import have since gained a working,
uncommitted draft implementation**; the reconstruction-plan schema, the
comparison loop, and the live-sandbox wiring remain pure design, untouched
by code.

## 18. Status re-verification (2026-08-07) — uncommitted camera/timeline + asset-import work found

A follow-up pass re-checked every checkable claim in sections 10-17 and
the corresponding `PROJECT-TODO.md` items directly against the current
codebase (not against what the docs said) before making this update.
18 of 20 checked items were confirmed unchanged. Two were not:

1. **The `units_per_meter` staleness fixed in section 17 above.**
2. **Working-tree code for camera/timeline operations and asset-import
   already exists, uncommitted, undocumented until now.**
   `tools/blueprint_interpreter.py`'s committed baseline (`9ee1031`/
   `e7e010b`) had only `bevel`/`mirror`/`array`. The current working tree
   adds `set_camera_keyframe`, `orbit_around`, and `dolly_to` (lines
   369-451, registered in the `OPERATIONS` dict at line 453) plus an
   `"import"` primitive type that pulls an existing asset by
   `canonical_id` via `oeb.config.json` — i.e. real code toward both
   section 17's stated top priority (camera/timeline operations) and its
   item 2 (asset-import), still following the same `_apply_<op>` pattern
   as the committed operations.

   **Status is draft, not done — three gaps keep this from being treated
   as shipped:**
   - **Not committed.** This is uncommitted working-tree state, per
     `git log` — nothing has landed on the branch.
   - ~~Not verified live.~~ **Verified live 2026-08-07, see below.**
   - **Not adopted anywhere.** The interpreter's own docstring says the
     new camera system and the teleplay pipeline's existing camera
     grammar (`data/camera_grammar.json`, `export_blender.py`) are
     "intentionally not unified yet." No caller in
     `routers/studio_chat.py` or `services/studio_chat.py` references
     `blueprint_interpreter` at all (still `primitive_asset_builder.py`
     exclusively, confirmed at `routers/studio_chat.py:1121`) — the
     wiring gap from section 16 ("nothing calls it yet") is unchanged.

   Recorded here as in-progress, not as a completed phase. Same
   convention as the rest of this document: no code has been
   authorized to be committed, and this section doesn't authorize that
   either — it's a status correction, not a decision.

### Live-Blender verification (2026-08-07)

Ran the uncommitted draft against real headless Blender 5.1.2 (not just
the mocked test suite), matching the verification standard the rest of
this document uses elsewhere. Test Blueprint: a cube, an imported
`prop_bottle_generic_A` (via `oeb.config.json`), a `set_camera_keyframe`
at frame 1, an `orbit_around` (frames 1-49, 90° arc, radius 10), and a
`dolly_to` (frames 50-97, distance 10→3).

- **Positive path, real build.** `blender --background --python
  tools/blueprint_interpreter.py` produced a real `.glb` (12.4KB) and
  `.blend` (287KB). The `.glb` correctly contains only `body` and
  `bottle` geometry (camera excluded, per spec) — confirmed via
  `use_selection` gltf export log ("Primitives created: 1" ×2).
- **Keyframes are real, not metadata.** Re-opened the produced `.blend`
  headlessly and inspected the camera's fcurves directly (Blender 5.1's
  layered-action API: `action.layers[].strips[].channelbags[].fcurves`,
  not the old flat `action.fcurves`). All 6 expected channels
  (location/rotation_euler × xyz) exist with 9 keyframes each. Values
  match the operations' math exactly: frame 1 = `(10, 0, 3)` (the
  declared `set_camera_keyframe` position); frame 49, end of a 90° orbit
  arc at radius 10 = `(0, 10, 3)`; frame 97, end of the dolly to distance
  3 = `(0, 2.91, 1.23)`, matching the hand-computed direction-vector math.
  Stepping `scene.frame_set()` across sampled frames and reading the
  object's evaluated transform matched the raw keyframe values exactly,
  confirming the fcurves actually drive the camera, not just record
  isolated points.
- **Guard rails fire for real.** Three negative-path cases confirmed to
  raise `ValueError` and produce zero output files under real Blender:
  a `set_camera_keyframe` frame (500) outside the declared
  `frame_range`; an `orbit_around` with `end_frame < start_frame`; and a
  degenerate `set_camera_keyframe` where `position == aim`.
  Same-run manifest correctly recorded `units_per_meter`, the resolved
  `frame_range`, and the three applied camera operations.
- **Mocked suite still green:** `test_blueprint_interpreter.py` 18/18,
  matching the earlier count — the live run surfaced no behavior the
  mocks missed.
- **Byproduct, not a bug:** importing `prop_bottle_generic_A` pulls in
  every object from its source file (`bar_scene_scifi.glb`, a shared
  multi-object glTF), not just the requested node — matching
  `export_blender.py`'s existing import-and-resolve-by-name pattern
  (same mechanism this file's docstring already cites). The extra
  objects stay unparented and are excluded from the `.glb` export by
  selection, so this doesn't leak into build output, but it does leave
  inert extra objects in the intermediate `.blend` scene when a shared
  asset file is imported.

**Net result: the live-verification gap is closed for camera/timeline
ops and asset-import.** The remaining two gaps — not committed, not
wired into anything that calls it — are unchanged and still require an
explicit decision before either happens.

## 19. Blueprint interpreter wired into Studio Chat's build path — the two paths unified, not bridged

Directly requested and executed, not scoped in advance: wire
`tools/blueprint_interpreter.py` into Studio Chat's actual build path,
closing the gap sections 13/16/18 called out repeatedly ("not yet wired
up... nothing calls it yet"). The first implementation attempt kept
`tools/primitive_asset_builder.py` as a separate file that the
interpreter imported and delegated to for compiled-spec builds. Called
out directly as the wrong shape — "we don't want two paths,
primitive_asset_builder.py isn't able to do anything productive [on its
own anymore]. What can we salvage and unify into blueprint?" — and
redone as a real merge instead of a bridge.

### What was salvaged vs. cut

Every function in the old `tools/primitive_asset_builder.py` was real,
exercised, tested code — the hierarchical/recipe system this whole
review has been trying to get more out of since section 8, not the
heuristic-guessing layer that was cut in Phase 1 (that lived in
`services/studio_chat.py`, a different file, already gone). Nothing here
was dead weight; the ask was to stop running it as a second script, not
to delete its capability. Concretely:

- **Salvaged, moved verbatim into new `tools/oeb_blender/recipes.py`:**
  category dispatch (`category_for_name`, `scene_object_category` — incl.
  the seating/storage/bed → chair/cabinet/bed routing fixed in section
  10 Phase 2), every `make_*` recipe (`make_chair`, `make_table_like`,
  `make_bed`, `make_cabinet`, `make_monitor`, `make_lamp`, the
  `make_vehicle_*` family), the flat registry-primitive dispatch
  (`primitive_for_registry_instance`, `PRIMITIVE_BUILDERS`), placement
  math (`component_position`, `scene_object_position`,
  `offset_position_for_category`), and the top-level
  `make_component_layout_scene` → renamed `build_object_graph`, now
  geometry-only (camera/lighting/preview setup moved to the
  interpreter — see below). `parent_to_root` (byte-identical between
  the two files already) moved to the existing shared
  `tools/oeb_blender/primitives.py` instead of staying duplicated a
  second place.
- **Cut, not moved:** `add_preview_setup` (the old script's own
  camera+light+render-settings function) was retired outright, not
  ported — the interpreter already owns a reserved "camera" object and
  the camera/timeline operation vocabulary (section 17/18); duplicating
  a second camera-creation path inside the recipe module would have
  recreated exactly the "two paths" problem this whole pass was fixing,
  just one level deeper.
- **`tools/primitive_asset_builder.py` deleted.** Not deprecated, not
  kept as a fallback — removed from the tree, matching
  `PROJECT-TODO.md`'s own alpha-development rule ("prefer deleting...
  over preserving legacy behavior. Do not keep duplicate data flows").

### The unified build

`blueprint_interpreter.py`'s `build_blueprint()` now has exactly one
branch point: a Blueprint carrying a `compiled_spec` key (the full
compiled `PrimitiveBuildSpec` — scene_plan/components/registry
primitives) builds geometry via `oeb_blender.recipes.build_object_graph`;
one without it builds from the native `primitives`/`operations`
vocabulary (cube/cylinder/.../bevel/mirror/array/camera-ops/import).
Both branches converge immediately after: the interpreter always creates
its own reserved "camera" object and preview light, and — new in this
pass — gives the camera a sane default framing
(`canonical_camera_views()["action"]`, the same named view the old
script's preview always used) whenever a Blueprint's operations don't
target the camera at all, rather than only for compiled-spec builds.
Pure-Blueprint builds that don't choreograph a camera now also get a
sensible preview instead of a blank shot at the origin — a capability
gain from unifying, not just a refactor.

### `app.routers.conversations._build_job_payload` now targets the interpreter

Every Studio Chat build job — `create_studio_chat_build_job`,
`create_conversation_job`, and edit/revert rebuilds via
`_edit_build_job_from_state`, since all three funnel through this one
function — now submits `tools/blueprint_interpreter.py` with
`--blueprint-json` wrapping the compiled spec as `compiled_spec`, plus
`--glb-output`/`--blend-output`/`--preview-output`/`--manifest-output`.
`artifact_paths` grew a fourth entry for the `.blend`. This closes the
still-open `PROJECT-TODO.md` item "Have Blueprint execution write dual
artifacts... nothing general-purpose populates them today" for every
future build, for free — `blueprint_interpreter.py` always wrote both
halves already, it just wasn't Studio Chat's build script yet.
`_state_paths_from_payload`'s existing by-suffix `.blend`/`.glb`
detection (section 15) picks up the new path automatically; no server
code needed to change beyond the payload builder itself.

### Verified

- **Mocked suite:** 286/286 passing on host (two pre-existing failures
  in `test_asset_review_streamlining.py`/`test_studio_chat_milestone_17.py`
  are unrelated — they require Docker-stack env vars not set on host,
  same as before this change). The old `test_primitive_builder_routing.py`
  was replaced by `test_oeb_blender_recipes.py`, same test bodies,
  retargeted at the new module — not weakened, not dropped.
- **Live, headless Blender, hierarchical/recipe path:** submitted a
  `compiled_spec` for `category: "seating"` (the same category-routing
  fix from section 10 Phase 2) through the full interpreter CLI. Real
  output: a 3-part chair (`seat`/`back`/`post`, matching `make_chair`
  exactly), a valid `.glb` (11.5KB) and `.blend` (100KB), and a real
  preview PNG showing a recognizable chair, correctly framed by the new
  default-camera logic — visually confirmed, not just file-existence
  checked.
- **Live, headless Blender, native camera-choreography path
  re-confirmed after the refactor:** re-ran section 18's exact
  camera/orbit/dolly/import test blueprint. Identical keyframe values
  (`frame 1 = (10,0,3)`, `frame 49 = (0,10,3)`, `frame 97 =
  (0,2.91,1.23)`) and identical guard-rail behavior (out-of-range frame
  still raises, zero output files) — the unification did not disturb
  the already-verified camera path.

### Status

Committed to nothing — same convention as the rest of this document,
these are working-tree changes pending the user's own commit. But this
closes the "not wired up" gap that persisted across sections 13, 16, and
18: Studio Chat's build path and the Blueprint interpreter are now one
system, not two, and the interpreter's camera/timeline/asset-import
work from section 18 is reachable from real chat-driven builds for the
first time.

## Not yet decided

This document records discussion and opinions reached along the way, not
final decisions. Nothing here should be read as authorization to delete
code, change the heuristic layer, rebuild the API on MCP, or execute
Phase 3 as scoped in section 10, the section 11 design plan (as amended by
sections 12-14) beyond what's already built, the scene-level operation
vocabulary in section 16, or any of the reconstruction-plan schema,
comparison loop, or live-sandbox/Blender-MCP wiring proposed in section
17 — those would be separate, explicit asks. Camera/timeline operations
and asset-import (also proposed in section 17) are now live-verified and
wired into Studio Chat's real build path per section 19 — explicitly
requested and executed, not an inference from this document. Phases 0,
1, 2, and 4 were executed and verified (section 10); their working-tree
diffs are the actual deliverable. Section 14 plan item 1 was executed
and verified (`tools/register_studio_chat_asset.py`, now committed), the
`complete_job` path-resolution fix was implemented and verified live
(section 15), the Blueprint interpreter and its job wiring were
implemented and verified live (sections 13 and 16,
`tools/blueprint_interpreter.py`, `tools/submit_blueprint_job.py`), the
resolver-symmetry fix (section 16) was implemented and verified live
(`--asset-id`/`--job-id` as first-class mutually-exclusive resolvers, now
committed), and Studio Chat's build path now runs entirely through the
Blueprint interpreter with `tools/primitive_asset_builder.py` deleted
(section 19) — all real, working, tested code, not proposals. Section 19
is uncommitted working-tree state, same as every other change this
session; it does not authorize itself to be committed. Section 11 (the
still-narrow operation vocabulary — no boolean/bisect/extrude/loft/sweep
yet), section 12's Canonical Asset / Production Variant lifecycle, the
scene-level operation vocabulary (section 16), and section 17's
reconstruction-plan schema/comparison-loop/live-sandbox items remain
design proposals only — no code has been written against any of them.
The logo rotation-axis bug identified in section 17 (a separate session's
`scene_versions/oeb_scene_title_v0.0.6/build_scene_title.py`) is also not
yet fixed — diagnosis only, per that session's explicit instruction.
