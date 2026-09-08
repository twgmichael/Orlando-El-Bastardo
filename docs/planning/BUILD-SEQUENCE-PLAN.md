---
title: Build Sequence Plan
created: 2026-08-16T00:00:00-04:00
updated: 2026-08-16T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: draft
canonical: true
canonical_for: build_sequence
wiki: true
wiki_group: Planning
wiki_order: 199
---
# Build Sequence Plan

Recorded 2026-08-16. Coordinates the order in which the currently active
planning docs get built, so each phase's real output accelerates the
next one instead of the phases being built in parallel on unproven
foundations. This document doesn't introduce new decisions of its own —
it sequences decisions already recorded elsewhere.

## The active planning docs this coordinates

- `docs/planning/PRODUCER-HARNESS-RENDER-DISPATCH-PLAN.md` — proves the
  harness can dispatch and distribute real render work across workers.
- `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md` — `job_limit`, the
  uniform confidence-level job envelope, zero-budget gating, pre-job
  cost/time estimates, the benchmark-grading system.
- `docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md` — the Producer
  reorganization itself (screenplay-wide grouping into production groups)
  and the master/resolved script mechanism.

## Phases

### Phase 0 — Harness render dispatch (active now, gates everything below)

`PRODUCER-HARNESS-RENDER-DISPATCH-PLAN.md`'s build plan: new
`scene.pipeline_render` job type, worker adapter, Producer dispatch
branch, local-Docker-harness proof, then the staging proof run
(81-scene episode distributed across `render-mac-01`/`render-pc-01`).
Already the recorded sequencing gate — see that plan's "Decisions"
section — for the reason already given: *"Better to spend our effort
proving what we know works than try to do that later with something
that we're not sure of altogether."*

Nothing in Phase 2 below should be built until this lands, because it
extends the exact same worker-registration/job-claim mechanism this
phase proves out — building `job_limit`/confidence-level routing on top
of an unproven dispatch foundation repeats the mistake this phase exists
to avoid.

### Phase 1 — Master/resolved script mechanism (can start now, in parallel with Phase 0)

`PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s "Master/resolved script concept"
and "Director joins the master-script process" sections: extend
`data/standins.json` with alias/description matching, give
`tools/director.py` a write path into `data/resolver_map.json` matching
Casting Director's and Production Designer's existing pattern, persist
`screenplay_entity_resolution.py`'s resolutions instead of discarding
them.

**No harness dependency** — this is local/deterministic file work, not a
render-dispatch or job-routing change, so there's no reason to wait on
Phase 0. **Coordination risk with Phase 0's `intent.json` payload —
resolved 2026-08-17**: every Phase 1 decision made so far (alias
resolution in `data/standins.json`, resolver extensions in
`data/resolver_map.json`, Director's continuity handoff in its own
`director_state.json`) lands outside `intent.json`, so there's no
collision with Phase 0's `scene.pipeline_render` payload today. Any
future Phase 1 work that does need a real `intent.json` field uses
versioning, not a freeze — see
`PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s resolved note on this
(`schema_version` already exists on `SceneIntent`, just needs to
actually be checked by the worker adapter once it's built).

**Why doing this now accelerates Phase 3**: per the naming-convention/
alias discussion, most of the guessing burden in a full-script grouping
pass comes from unresolved ambiguity ("the 5000" vs. "small red ship").
Landing alias resolution before Phase 3's grouping pass gets built means
that pass groups against already-resolved entities instead of raw
ambiguous text — directly shrinking how much any LLM, local or cloud, has
to guess.

### Phase 2 — Harness resource model (gated behind Phase 0)

`HARNESS-RESOURCE-MODEL-PLAN.md`: `job_limit` field, the uniform
confidence-level job envelope, the zero-budget-by-default gate, pre-job
cost/time estimates. Extends Phase 0's now-proven worker/job-dispatch
mechanism rather than building on an unproven one.

**Benchmark-system data collection can start earlier, informally** —
grading local-vs-cloud competence per task doesn't require the scheduler
to exist first, only a place to log results. Now owned by
`docs/planning/LLM-COMPETENCE-BENCHMARK-PLAN.md` (2026-08-17, closes the
doc gap below), logging to
`docs/planning/benchmarks/llm_competence_results.jsonl` — a separate file
from the existing `docs/planning/benchmarks/results.jsonl`, which turned
out to already be owned by the unrelated Studio Chat visual-variety
benchmark. Building the *scheduler logic* that consumes those grades
should still wait for Phase 0, per the gating reason above.

### Phase 3 — Production Assembly Pipeline reorganization (gated behind Phase 0; benefits from Phases 1 and 2)

`PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s Producer role reorganization
itself: the screenplay-wide grouping pass, 4–5 production groups,
Casting Director/Production Designer prepare-once, Director stages-many.
Already gated behind Phase 0 (recorded sequencing decision). Now also
benefits concretely from:

- **Phase 1**: clean, already-resolved entity data to group against
  instead of raw ambiguous script text.
- **Phase 2**: the confidence-level envelope and per-script budget
  allocation Producer's own role definition already commits to using
  (the "$10 budget → $5 to the full-script breakdown, $5 to everything
  else" example needs Phase 2's mechanism to actually function, not just
  be a worked example).

## Doc gap — closed 2026-08-17

`docs/planning/LLM-COMPETENCE-BENCHMARK-PLAN.md` now owns the
benchmark-grading system referenced from `HARNESS-RESOURCE-MODEL-PLAN.md`
(open question 2) and this document's Phase 2 above.

## Not built

This document coordinates sequencing only. No phase above has started
implementation as of this writing.
