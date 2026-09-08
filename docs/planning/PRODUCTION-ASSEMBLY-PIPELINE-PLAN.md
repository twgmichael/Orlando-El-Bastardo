---
title: Production Assembly Pipeline Plan
created: 2026-08-16T00:00:00-04:00
updated: 2026-08-16T00:00:00-04:00
doc_type: plan
production_area: layout
department: layout
status: draft
canonical: true
canonical_for: production_assembly_pipeline
wiki: true
wiki_group: Planning
wiki_page: Production-Assembly-Pipeline-Plan
wiki_order: 202
---
# Production Assembly Pipeline Plan

Recorded 2026-08-16. Status: **deep-dive planning starting; the four local/
cloud/budget/provider questions below are answered as of 2026-08-16, but
implementation is explicitly sequenced behind
`docs/planning/PRODUCER-HARNESS-RENDER-DISPATCH-PLAN.md`'s staging proof
run — see "Sequencing decision" below. Nothing scoped into an
implementation plan or built from this document yet.**

## Predecessor

This document is the direct successor to
`docs/archive/LOCATION-BASED-SCENE-GROUPING-INSIGHT.md` (archived
2026-08-16, superseded by this doc), which recorded the original insight
and the first role-by-role discussion (Producer, Production Designer,
Casting Director, Director) that this plan now carries forward. Read that
document first for the worked example (the teaser's outer-space/asteroid
scenes) and the five open questions raised there — they are restated and
extended below, not replaced.

## Named concept: Production Assembly Pipeline

The reframe from the predecessor document, now given a name:

```text
Screenplay → organize production → build reusable world → stage scenes → shoot cameras
```

replacing today's architecture:

```text
Scene → solve everything → render
```

Concretely: the Producer should perform a screenplay-wide pass before any
Director work begins. It identifies shared locations, chronological
relationships, asset dependencies, continuity chains, and efficient
production groups. The Production Designer and Casting Director then
prepare each shared production package once. The Director subsequently
stages every associated screenplay scene inside that package.

## Producer role definition (confirmed 2026-08-16)

The Production Assembly Pipeline concept above, made concrete as a role
specification for Producer:

- Reads the complete screenplay and production context.
- Breaks down scenes into production requirements.
- Groups scenes by shared locations, sets, characters, vehicles, props, and
  effects.
- Determines dependencies and sensible production order.
- Identifies what already exists versus what must be created.
- Produces the executable production plan.
- Assigns work to Production Designer, Casting Director, and Director.
- Tracks whether everything required for a scene is ready.
- Owns production-planning cost and time responsibility — see "Budget and
  time-estimate responsibility" below.

### Worked handoff example

```text
Producer: "Scenes 2, 5, 8, and 11 share Space Environment A. They require
  Orlando, JB5K, mining probe, asteroid field, and these effects."

Production Designer: "I will make sure that environment and its required
  physical/digital assets exist."

Casting Director: "I will make sure the required characters and performers
  exist."

Director: "I will stage the actions, trajectories, performances, cameras,
  and shots within that prepared environment."
```

### Producer vs. Director — the load-bearing distinction

**Producer decides what must be produced and organizes how the production
gets there. Director decides how prepared material becomes the actual
screen performance and images.** Producer is the planning/organization
layer; Director is the creative-staging/execution layer working inside
what Producer has already assembled. This is the concrete answer to this
document's own open question 5 (does Production Group become a
Producer-owned tracked artifact) — yes, tracking readiness is explicitly
listed as a Producer responsibility above.

### Real-world scoping: what carries over from Line Producer / UPM, and what doesn't

Traditional Line Producer and Unit Production Manager duties concerning
money, human crews, permits, catering, transportation, payroll, union
rules, and physical logistics mostly do not apply to this studio — there
are no physical sets, crews, or locations to manage. Their *useful
computational functions* — breakdown, scheduling, dependencies, resource
planning, and production readiness — fit naturally inside this Producer
role and are exactly what the role definition above captures. One
partial exception worth naming explicitly: budget is a real, applicable
concept here too, just not in its physical-production form (payroll,
catering) — see the zero-budget-default rule below, which is the
computational-resource-planning analog of a Line Producer's budget
authority, not a callback to physical production costs.

### Budget and time-estimate responsibility (folded in 2026-08-16)

Producer's production-planning role now explicitly includes cost and time
estimation, not just grouping and dependency tracking:

- **A budget of zero dollars is always assumed unless explicitly stated
  otherwise — in the script, or provided by a human.** No agent or
  software may ever assume, or be allowed, a budget greater than zero on
  its own. This is a hard rule, not a soft default; see
  `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md`'s "Resolved: the
  zero-budget default" for the mechanism (nonzero-cost resources are
  filtered out of the harness scheduler's candidate set entirely unless a
  job carries explicit authorization, rather than being deprioritized).
- **Time estimates matter alongside budget**, not as an afterthought: if a
  job is marked urgent, the system should be able to produce cost
  estimates for different turnaround times, not just a single number.
- **Named as a "big win" feature**: producing upfront cost/time estimates
  for render, LLM, audio, and other resource requests *before* a job
  starts, not just tracking actual spend after the fact.
- The actual estimate computation and the budget-gating mechanism live at
  the harness/resource-model level (they need real per-resource data —
  pricing, `job_limit`, typical durations) — see
  `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md`. Producer is the
  consumer: it requests estimates as part of building the executable
  production plan, and respects the zero-budget default when deciding what
  it can actually assign.

### Per-script budget model (command decision, 2026-08-16)

Makes concrete what "explicitly stated otherwise — in the script" means
above:

- **Budget lives on the script itself**, as a line item a human adds — not
  a global setting, not a per-job flag chosen by any agent. No line item
  means the script's budget is zero. This is not a fallback to be fixed —
  it's the correct, intended behavior, and it's what all three current
  test scripts already do (none of them carries a budget line item, so
  every job against them today correctly runs at $0).
- **When a script does carry a budget, Producer allocates it** across the
  resource needs of that script's production. Worked example: an
  81-scene script gets a $10 line item. Producer might spend ~$5 of it on
  one cloud call for the initial full-script breakdown/rundown that
  everything else in that production consumes, and allocate the remaining
  $5 across whatever else in the run turns out to need paid resources —
  the split isn't fixed in advance; Producer determines it using the
  pre-job cost/time estimates described above.
- Not yet designed: where the budget line item actually lives (screenplay
  frontmatter, a sibling config file, a `producer.py` flag) or the exact
  allocation algorithm. See "New open questions" below.

### Open concern (2026-08-16): is a paid call a hard default for the full-script grouping pass?

Raised directly against Decision 1 below: always requiring a frontier
cloud call for Producer's screenplay-wide grouping pass risks becoming a
hard dependency on paid resources for a step that runs once per script but
gates everything after it — in tension with the zero-budget-by-default
rule, which should make paid resources the exception, not the assumed
path. Per-scene work has already had real success on the local model at a
useful confidence level (the local-vs-Haiku benchmarking discussed
earlier). Worth investigating before accepting Decision 1 as final: can
the screenplay-wide grouping pass itself be done as local-only, chunked
work — batching scenes into windows the local model can actually handle
well, then merging/reconciling the per-chunk results — accepting somewhat
diminished grouping quality as the zero-budget default, with a paid
full-script pass as an opt-in upgrade only when a script's budget actually
authorizes it? Not designed or benchmarked. See "New open questions"
below.

## New context since the predecessor document

Two things changed between the predecessor insight and this plan starting:

1. **Cloud LLM access added.** OpenAI API and Claude API keys were added to
   a new `.env.local` at the repo root (gitignored, not read into this
   document — see `docs/local/COMMANDS.md`-style handling for secrets).
   This is the first cloud-LLM credential present in the project; every
   LLM-touching component built so far (Producer, Director, Casting
   Director, Set Designer, Studio Chat's asset-matching tiers) has run
   against the local Qwen2.5-3B model only.
2. **New branch opened for this work:** `feature/production-assembly-pipeline`.

The Production Assembly Pipeline is the first piece of architecture being
planned with cloud-model access assumed available, not retrofitted onto it
later — which is why the open questions below focus on the local/cloud
split rather than only on the grouping mechanics themselves.

## What carries forward unchanged from the predecessor

- Per-scene validation and construction discipline remains valuable at the
  camera-pass level (and for genuine single-scene cases) — this pipeline
  changes the *unit* those steps operate on, not whether they happen.
- The existing `location_standins` reuse (exact `location_tag` match) is
  the floor this pipeline builds on, not a replacement for it.
- The project's standing pattern for LLM use — constrained candidate-set
  selection, grounded evidence, deterministic code owns resolution — is the
  default assumption for how the Producer's grouping pass should work,
  local or cloud.

### Leveraging the cloud call as a dual-purpose investment (2026-08-16)

Direction on the "Open concern" above: proceed with one real cloud
(Opus-tier) call for the full-script breakdown now, treated as serving two
purposes at once, not just one:

1. **Immediate deliverable** — the actual production plan for the current
   script, usable today regardless of how the local-chunking question
   resolves.
2. **Calibration fixture for the local-chunked alternative** — per
   decision 3's dev-cost-control note (persist the raw response, develop
   against the cached fixture), the same saved response becomes ground
   truth to design and test local-chunked grouping against, rather than an
   independent one-off cost.

**Concrete way to mine it**, so the comparison is evidence-based rather
than an overall similarity eyeball: pull out (a) which groupings are
non-contiguous and which fall inside simple contiguous windows — this
tells whether any windowing scheme can work at all, or whether grouping
fundamentally needs whole-script visibility; and (b) which groupings are
simple shared-tag matches (same `location_tag`, same cast) versus which
required real judgment (e.g. deciding two differently-tagged scenes are
"the same set"). If most groupings turn out to be deterministic tag
matches, the real local-vs-cloud question shrinks to a small set of
genuinely ambiguous decisions — cheap enough to resolve individually
rather than needing one whole-script reasoning pass. This also feeds the
master/resolved script concept below: the judgment calls the cloud call
resolves are exactly the kind of ambiguity (like "the 5000" vs. "small red
ship") the alias/description matching there needs to capture.

## Master/resolved script concept (raised 2026-08-16)

### Long-term goal, stated explicitly

The main goal of this system is to take **any** industry-standard
screenplay or teleplay — not one authored or reformatted for this
pipeline — and produce a 3D-animated version of it at 90–99% correctness
with no real human intervention. This matters directly here: it means the
system cannot rely on scripts being written in a deterministic,
pipeline-friendly style. Real scripts are ambiguous (this project's own
test script refers to the same ship as both "the 5000" and "small red
ship" in different places), and the system has to absorb that ambiguity,
not assume it away.

### The problem

Script formatting/naming discipline directly drives how much an LLM has to
guess. Right now that guessing happens **every time** an agent processes
the raw script — Producer's grouping pass, Casting Director's resolution,
Production Designer's asset resolution, etc. each independently re-derive
"the 5000" and "small red ship" mean the same asset, from the same raw
ambiguous text, on every run.

### Proposed middle ground: a progressively-enriched master script

Instead of re-guessing from raw text every time, convert the script once
into an exhaustively detailed, deterministic reference — filling in every
resolvable ambiguity explicitly — and have each role **write its resolved
findings back into that shared reference** as it does its own part, rather
than only producing isolated per-role artifacts derived independently from
raw text each time. Later stages (and later re-runs) read already-resolved
answers instead of re-guessing them. Open whether this is a markdown file
or a database entry — not decided; see open questions below.

This also implies asset management (`oeb.config.json` today) needs to
carry alias/description matching, not just exact tag/name matching — "the
5000" and "small red ship" both need to resolve to the same registered
asset entry.

### Decisions accepted (2026-08-16) — how to build the master script

Resolving several of the open questions above by reusing existing
mechanisms rather than inventing new storage:

- **Format: no new monolithic store.** Reuse and extend what already
  exists — `data/resolver_map.json` and `data/standins.json` (the shared,
  persistent, cross-role resolved-entity/vocabulary layer Casting
  Director's `resolve_role()` and Production Designer's
  `resolve_location()` already read and write today), per-scene
  `out/production/<episode>/scenes/<scene_id>/intent.json` (the per-scene
  fully-resolved detail layer Producer's `build_intent()` already
  produces), and `out/production/<episode>/report.json` (the live
  per-episode status/ticket index `tools/tickets.py` already maintains).
  Together these three are the master script; a generated markdown/JSON
  rollup view can be produced *from* them for human readability, but is
  not itself a new source of truth.
- **Alias/description matching (shape decided 2026-08-16): two-tier,
  cheapest path first.** Tier 1 — a separate alias-redirect table
  alongside `data/standins.json`'s existing flat maps (e.g. `"aliases":
  {"small red ship": "ship 5000", "the 5000": "ship 5000"}`), tried
  first: free, instant, exact, and additive — it doesn't touch the
  existing `cast`/`location_standins` dicts or their call sites, only
  adds one redirect hop on a miss. Tier 2 — description/embedding-based
  matching, tried only when Tier 1 misses: covers phrasings nobody
  enumerated, which Tier 1 alone can never generalize to, at the cost of
  a real (if cheap/local) match step instead of a free dict lookup. Tier
  1 alone doesn't scale to an unseen script; Tier 2 alone would pay a
  matching cost on every mention even when a one-line alias would have
  resolved it for free — the two-tier order is what keeps this
  level-0-first.
- **Ownership**: each role already writes disjoint entries via its own
  `resolve_*()` function (Casting Director → role/cast entries,
  Production Designer → location entries) — natural per-role namespacing
  by entity kind, matching how it already works today. No new
  conflict-resolution mechanism needed as long as each role's writes stay
  scoped to its own entity kind.
- **Storage location**: a hybrid, not a pure choice between "harness
  artifact" and "local file." The underlying files stay local/
  git-tracked derived state, same as today, but resolution increasingly
  routes through the harness's existing registry-resolve HTTP endpoint
  (`tools/screenplay_entity_resolution.py` already calls
  `GET /api/v1/registry/resolve` for entity-mention resolution) — the
  harness mediates resolution; the files persist the result.

Still genuinely open, not resolved by reuse: **staleness/invalidation**
(no existing mechanism tracks whether a resolved entry is still valid
after the raw script changes) and **the human-curation-vs-full-automation
tension** (a human-curated alias table solves this script's ambiguity but
doesn't generalize to an unseen script, which is the stated long-term
goal) — both carried forward, unresolved.

### Director joins the master-script process (2026-08-16)

Director is added to the master-script write pattern on equal footing with
Producer, Casting Director, and Production Designer — closing the gap
flagged in prior discussion (Director's staging output currently doesn't
persist anywhere durable outside the render pipeline). Mechanically, this
means `tools/director.py` needs a write path into the shared
resolved-entity layer analogous to `resolve_role()`/`resolve_location()` —
not yet built.

What Director writes back is very likely the same "Scene State" continuity
handoff already named in predecessor open question 3 below
(staging/camera/performance decisions that carry forward into the next
connected scene in a production group) — this decision confirms Director
*gets* a durable write path; the exact data shape of what it writes is
still open (question 3 below, now sharpened rather than replaced by this
decision).

**Write path decided (2026-08-17): per-scene file, mirroring `intent.json`.**
`out/production/<episode>/scenes/<scene_id>/director_state.json` — one
file per scene, not a shared mutable structure, consistent with how
`intent.json` already works. A scene later in a continuity chain reads
the *specific prior scene's* file (Producer's dependency chain says
which one), rather than everyone reading/overwriting one global record.
Chosen over a shared-file or database-record approach for now — revisit
once other collaborative features (real-time multi-role editing, the
harness-hosted registry direction) are further along; nothing here
blocks moving to a shared store later, since each per-scene file can be
absorbed into one once it exists. Doesn't depend on Phase 3 (the
grouping pass) existing first, unlike a continuity-chain-keyed shared
record would — Director can start writing these now; chain-reading wires
up once Phase 3 assigns chain ids. Still open: whether the file holds
the full `DirectorPlan` (shots/framing included) or just the end-state
subset (`blocking` + final `move` marks) continuity actually needs —
shots are per-scene creative choices, not facts the next scene needs to
read.

### New open questions (2026-08-16, master script / asset alias matching)

- **Director's write path — storage location decided** (per-scene
  `director_state.json`, see above). Still open: full `DirectorPlan` vs.
  end-state-only fields in that file — this is predecessor question 3
  (Scene State's data shape), narrowed to a field-content choice now
  that storage location is settled.
- **Coordination risk with the in-flight render-dispatch build — largely
  mitigated, "version it" adopted for the residual (2026-08-17).** None
  of the Phase 1 decisions made so far touch `intent.json`'s shape: alias
  resolution lives in `data/standins.json`, resolver extensions in
  `data/resolver_map.json`, Director's continuity handoff in its own
  `director_state.json` — all resolve into `intent.json`'s existing
  fields with better values, not new ones. Residual risk (a future
  Phase 1 addition someday needing a real `intent.json` field) is covered
  by versioning rather than freezing: `schemas/sceneintent.schema.json`
  already requires a `schema_version` field (semver-patterned, currently
  unused for this purpose) — any future shape change bumps it, and
  `scene.pipeline_render`'s worker adapter checks it rather than assuming
  a fixed shape. No freeze needed.

## Open questions carried from the predecessor (not yet resolved)

1. How does the system decide two location tags are "the same set"
   (human-curated location-family mapping vs. LLM-inferred)?
2. Contiguous vs. non-contiguous grouping — confirmed non-contiguous by the
   predecessor's worked example (scenes 1, 3, 7, 11), but the mechanism for
   persisting and re-entering a built set across the whole episode is not
   designed.
3. What carries continuity across a group, and who authors it — the
   predecessor proposed a "Scene State" handoff between connected scenes,
   authored by Director from a Producer-identified dependency chain, but
   the data shape of "Scene State" is undefined.
4. What's the new unit of production tracking — does "Production Group"
   become a first-class tracked artifact alongside the screenplay scene, or
   purely an internal grouping the existing per-scene tracking absorbs?
5. Incremental rollout vs. one redesign?

### New open questions (2026-08-16, budget model and grouping-pass default)

6. Where does a script's budget line item actually live — screenplay
   frontmatter, a sibling config file, a `producer.py` CLI flag, something
   else? Not specified yet.
7. What's the actual algorithm Producer uses to split a script's total
   budget across resource needs (the "$5 to the full-script breakdown, $5
   to everything else" example is illustrative, not a rule)? Presumably
   consumes the pre-job cost/time estimate feature once that exists — not
   designed.
8. Can the full-script grouping pass be done local-only via chunked/
   windowed batches instead of one large cloud call, and if so, how much
   quality is actually lost? Unbenchmarked — see "Open concern" above and
   `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md` open question 2 (ranked
   competence / benchmark-driven grading).
9. If a local-chunked grouping pass runs at diminished competence (because
   budget is zero), does Producer surface that as a flagged/lower-
   confidence result for human review, or is diminished quality accepted
   silently whenever no budget authorizes better? Not decided.

## Decisions (2026-08-16)

Answers to the five questions raised when this plan started, recorded from
discussion — not yet implemented.

1. **Producer's grouping pass routes to cloud.** Confirmed: the
   screenplay-wide grouping pass needs more capability than the local
   Qwen2.5-3B can reliably provide. Cost discipline is a hard constraint,
   not a nice-to-have: **call the real cloud API once per meaningful
   prompt/schema iteration, persist the raw response as a fixture, and
   develop against that cached fixture** rather than re-calling the live
   API on every harness/pipeline test. A separate, scaled-down test path
   exercises the deterministic plumbing against the local LLM and/or cached
   fixtures. This is explicitly **not** a local-vs-cloud comparison
   exercise — prompts are tuned per model, so output can't be diffed
   directly across them. **Flagged for reconciliation 2026-08-16:**
   `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md` records that the harness
   scheduler, not the caller, should pick local-vs-cloud per job — which
   sits in tension with "Producer explicitly routes to cloud" as stated
   here. Not resolved; see that document's "Needs reconciliation" section.
2. **Both cloud providers must be interchangeable.** Anthropic and OpenAI
   both get tested, and the pipeline must be able to swap between them via
   a config setting or flag, not a code change. Needs a provider-abstraction
   layer — either an existing vendor package (evaluate one, e.g. a
   LiteLLM-shaped abstraction, rather than assuming) or a small
   project-owned adapter. Not yet evaluated or chosen; this is real
   scoping work for whenever cloud-routed implementation begins, not
   decided here. **Superseded/extended 2026-08-16:** this is now scoped at
   the harness level, not just for Producer — see
   `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md`, which treats local and
   cloud LLM (and render) resources as interchangeable, harness-coordinated
   resources with a `job_limit` field, not a Producer-local provider swap.
   **Further flagged 2026-08-16:** whether cloud routing should even be the
   *default* for this pass is now itself an open concern, not just how the
   routing is chosen — see "Open concern: is a paid call a hard default for
   the full-script grouping pass?" above. **Reconciliation mechanism
   settled 2026-08-16:** `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md`'s
   "Uniform job envelope and confidence levels" resolves this — Producer
   requests a confidence level, not a specific backend; hardwiring to a
   frontier model was a symptom of not yet having that envelope, not a
   real decision to keep.
3. **Budget model.** Roughly $5 is acceptable for one full-script,
   Opus-tier test pass (matches the earlier per-request cost estimate for
   this exact job). Development-time cost control has three parts: (a)
   cache/reuse real cloud responses aggressively rather than re-calling
   live per test, per decision 1; (b) evaluate Haiku's reliability for
   "basic needs" tasks as a cheaper production tier, the same
   evidence-over-guessing approach as the local-vs-Haiku discussion; (c)
   default to the local LLM (or cached fixtures) for repetitive
   harness-plumbing tests that don't need real model output at all. All
   models — local and cloud — have a nonzero failure rate; saved
   known-good responses are treated as first-class test fixtures, not an
   afterthought.
4. **The reorganization target is confirmed, not just the mechanism.**
   Producer moves from 81 independent per-scene tasks to roughly four or
   five production groups (by scene/location); Casting Director and
   Production Designer prepare each group's assets once; Director stages
   scenes inside the group using those prepared assets. This restates the
   named concept above as a confirmed target shape, not a new open
   question.
5. **Sequencing decision — see below.** This is the biggest decision from
   this round: it doesn't just answer the open question, it gates
   everything else in this document.

## Sequencing decision (2026-08-16): harness render integration comes first

See `docs/planning/BUILD-SEQUENCE-PLAN.md` for the full phase-by-phase
build order this decision anchors, including which work (the master
script mechanism below) does *not* need to wait for this gate.


Before any Producer reorganization work begins, the staging harness must be
proven end-to-end for full-script rendering, distributed across real
workers — closing the gap documented in
`docs/planning/PRODUCER-HARNESS-RENDER-DISPATCH-PLAN.md` (no harness job
type currently exists for Producer's render step at all; it always runs
locally). Rationale, in the words the decision was made in: *"Better to
spend our effort proving what we know works than try to do that later with
something that we're not sure of altogether."*

Concretely: `docs/planning/PRODUCER-HARNESS-RENDER-DISPATCH-PLAN.md`'s
build plan (new `scene.pipeline_render` job type, worker adapter path,
Producer dispatch branch, then a real staging proof run submitting the full
81-scene episode through `oeb-studio.docker-pi` with jobs distributed
across `render-mac-01`/`render-pc-01`) is now the **active, sequenced
prerequisite** for this document. This plan (Production Assembly Pipeline)
stays in the "deep-dive planning, not yet scoped into implementation"
state until that render-dispatch proof run lands.

This also resolves part of question 5 as originally posed: the
Production Assembly Pipeline does not need to change what the
render-dispatch plan carries (grouping is a pre-Director planning
concern, separate from render dispatch) — it depends on that plan being
*proven*, not on it being *redesigned*.

## Not built

Nothing in this document has been implemented or scoped into an
implementation plan. `tools/producer.py`'s scene-by-scene loop is unchanged
as of this writing. No cloud-model call exists anywhere in the codebase.
No script carries a budget line item today (field doesn't exist yet); no
local-chunked grouping alternative has been built or benchmarked. No
alias/description-matching field exists in `data/standins.json` today,
only exact vocabulary matching; `tools/director.py` has no write path
into `data/resolver_map.json` yet.
