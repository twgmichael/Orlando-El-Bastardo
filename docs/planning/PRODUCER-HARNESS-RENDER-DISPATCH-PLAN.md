---
title: Producer Harness Render Dispatch Plan
created: 2026-08-15T00:00:00-04:00
updated: 2026-08-16T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: active
canonical: true
canonical_for: producer_harness_render_dispatch
wiki: true
wiki_group: Planning
wiki_page: Producer-Harness-Render-Dispatch-Plan
wiki_order: 200
---
# Producer Harness Render Dispatch Plan

Recorded 2026-08-15. Status: **active — as of 2026-08-16, this is the
sequenced prerequisite for `docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`.**
Decision (2026-08-16): prove the full 81-scene script rendering end-to-end
through the staging harness, distributed across real workers, before any
Producer reorganization work begins — see that plan's "Decisions" section
for the full rationale. Still nothing built as of this writing; this update
adds the build plan, not code.

## Why this exists

Raised during 2026-08-15 end-to-end test planning (bringing render-mac-01 and
render-pc-01 online and current): the request was that `tools/producer.py`
"shouldn't care" where a scene actually renders — local dev should farm to a
local Docker harness, staging runs should farm to the staging harness
(`oeb-studio.docker-pi`) and its workers, driven by settings, not hardcoded.

That's not currently true, and not for a shallow reason.

## Current state

`tools/producer.py`'s render step (`main()`, the branch that runs when
`--no-render` is not passed) unconditionally does:

```python
cmd = [VENV_PY, "tools/run_pipeline.py", "--intent", intent_path,
       "--episode", episode, "--targets", args.targets,
       "--render-out", render_out]
run = subprocess.run(cmd, ...)
```

This always runs locally, synchronously, one scene at a time, on whichever
machine invoked `producer.py`. It never consults `OEB_HARNESS_URL` /
`API_ADMIN_TOKEN`, unlike Producer's own `enqueue_casting_director_job()` and
`enqueue_set_designer_job()`, which already do exactly the env-driven
harness-or-local pattern this plan wants for rendering too.

This is not a hardcoded setting that can just be swapped for an env read.
There is currently **no harness job type that can carry this render step at
all**:

- The harness's existing `scene.render` job type
  (`POST /api/v1/scene-renders`, `docs/planning/SCENE-RENDER-JOB-TYPE-PLAN.md`,
  `BlenderCLIAdapter._execute_script` in
  `oeb-studio-harness/worker/agent/adapters/blender.py`) runs
  `blender --background --python <repo-relative script path>` — built for
  hand-authored scene scripts already checked into the repo (e.g.
  `tools/JB100-pirate-escape.py`).
- `tools/run_pipeline.py --intent intent.json --render-out ...` is a
  different shape entirely. It needs the worker's plain venv Python, not
  Blender's embedded interpreter — `run_pipeline.py` itself shells out to
  Blender as one step among several (resolve → validate → export → render).
  Its `intent.json` input is generated fresh per scene per producer run; it
  is not a file already sitting in git that a remote worker could reference
  by repo-relative path the way `scene.render` expects.

So today, nothing lets a worker run Producer's actual render pipeline at
all — local-only is not a missing `if` branch, it's a missing capability.

## Proposed job type: `scene.pipeline_render`

Mirrors the env-detection pattern already proven in
`enqueue_casting_director_job()` / `enqueue_set_designer_job()`: check
`OEB_HARNESS_URL` / `API_ADMIN_TOKEN`, harness-route if both are set, local
subprocess fallback (today's exact behavior, unchanged) if not — so a bare
local-dev run with no harness configured is completely unaffected.

1. **Server**: new job type `scene.pipeline_render`. Payload carries the
   actual `intent.json` *content* (not a path — workers do not share a
   filesystem with the machine running Producer), plus `episode`, `targets`,
   and render-quality fields matching the existing `scene.render` contract
   where they overlap (see `docs/planning/HARNESS-RENDER-QUALITY-LANGUAGE.md`).
   New Pydantic schema + router endpoint + service function, following the
   shape of `create_scene_render_job()` in
   `oeb-studio-harness/server/app/services/scene_render.py`.
2. **Worker**: new adapter path (new method on `BlenderCLIAdapter`, or a new
   adapter) that writes the payload's intent content to a job-scoped temp
   file, then runs
   `VENV_PY tools/run_pipeline.py --intent <tmp-path> --episode ... --targets ... --render-out ...`
   — the same subprocess-and-capture pattern `_execute_script` already uses,
   just invoking the venv interpreter instead of Blender's bpy interpreter.
   Rendered artifact uploads the same way every other job type's artifacts
   do today.
3. **Producer**: the unconditional local `subprocess.run([VENV_PY,
   "tools/run_pipeline.py", ...])` call becomes: submit-and-poll
   `scene.pipeline_render` when `OEB_HARNESS_URL`/`API_ADMIN_TOKEN` are set
   (mirroring `tools/submit_scene_render.py`'s request/poll pattern), else
   today's exact local call. On harness completion, record/download the
   returned artifact for `episode_cut()` the same way a local `render_out`
   path is used today.

## Scope note

This is not a one-line settings read. It touches a new server schema, route,
and service function; a new worker adapter path; and `producer.py`'s
dispatch branch — each needing its own tests — plus a deploy to
`docker-pi-01` (same flow used earlier 2026-08-15 for the worker-update
comparison fix) before it is usable against staging at all.

## Build plan (proposed 2026-08-16)

Phased so each step is independently verifiable before the next depends on
it. No step requires an LLM call — this whole plan is deterministic-pipeline
plumbing, orthogonal to the local/cloud model-routing work in
`docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`.

1. **Settle the open job-type question below** (new type vs. extending
   `scene.render`) before writing schema code — it changes the shape of
   every later step.
2. **Server**: `scene.pipeline_render` schema + route + service function
   (or the equivalent extension to `scene.render`), per the "Proposed job
   type" section above. Docker-backed tests, matching this project's
   existing convention (`docker exec oeb_studio_harness_local_api pytest
   ...`).
3. **Worker adapter**: the new `run_pipeline.py --intent <tmp-path> ...`
   dispatch path. Include the same worker-assignment fields
   `scene.render`/`tools/submit_scene_render.py` already have
   (`preferred_worker_id`, `require_gpu_cycles`, `priority`,
   `blender_timeout_seconds`) so this job type behaves consistently with the
   existing one rather than inventing a second dispatch contract. Tests.
4. **Producer dispatch branch**: env-driven harness-or-local, per the
   "Proposed job type" section's item 3. First target: **local Docker
   harness** (`127.0.0.1:8088`), not staging — smaller blast radius, and
   directly closes the local-routing half of open question 2 below before
   attempting staging.
5. **Staging proof run**: the actual milestone this whole plan exists to
   reach. Submit the full 81-scene episode
   (`scripts/pilot/Orlando-El-Bastardo-Episode-01-The-Pilot.md`) through
   `oeb-studio.docker-pi` with jobs distributed across `render-mac-01` and
   `render-pc-01`, and confirm it completes to an equivalent episode cut —
   the harness-dispatched counterpart to the local 81-scene run completed
   2026-08-15/16 (74/81 delivered that run; see `PROJECT-DONE.md` once
   logged). This is the "prove what we know works" checkpoint the
   Production Assembly Pipeline decision is gated on.

### A real architecture decision inside step 4: serial or fan-out dispatch?

Today's `main()` loop is **synchronous per scene** — submit, block, move to
the next scene. That's exactly why the local 81-scene run took ~12 hours on
one machine. Naively harness-routing that same loop (submit one
`scene.pipeline_render` job, poll to completion, then submit the next) would
still only ever have one job in flight — it would not use `render-pc-01` and
`render-mac-01` at the same time, and the actual payoff of "integrate the
staging harness" (real parallel throughput across two-plus workers) would be
left on the table. Getting real speedup requires restructuring the loop to
submit a batch of jobs and poll the batch — a bigger change to
`tools/producer.py`'s control flow than the dispatch branch alone, and worth
scoping explicitly in step 4 rather than discovering it mid-implementation.

## Render task assignment across workers

Directly relevant now that staging-harness distribution is the near-term
goal, not a someday capability:

- `scene.render`'s existing `preferred_worker_id` / `require_gpu_cycles`
  fields (`tools/submit_scene_render.py`) are the model to reuse for
  `scene.pipeline_render` — don't invent a second worker-assignment
  contract.
- **2026-08-16:** `docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md` proposes a
  new `job_limit` field on worker registration (local render workers = 1,
  cloud render/LLM resources = higher) as the general mechanism for
  per-resource capacity awareness across both render and LLM dispatch. Once
  that lands, `scene.pipeline_render` worker assignment should respect it
  rather than assuming every worker is single-job like today's two local
  machines.
- **Known blocker, found and never resolved earlier this session:**
  `render-pc-01`'s `gpu.cycles_render` capability is degraded — Blender
  reports "No CUDA/OptiX GPU devices discovered" despite `nvidia-smi`
  seeing the GPU fine. If any full-script proof run requests
  `require_gpu_cycles` for final-quality passes, those jobs will not route
  to `render-pc-01` until that's diagnosed — worth a pre-flight check
  before the staging proof run in step 5, not a surprise discovered during
  it.
- Whether the proof run needs `require_gpu_cycles` at all is itself an open
  call — the local 81-scene run used plain local Blender rendering with no
  GPU requirement, so a first staging proof run could reasonably do the
  same and treat GPU-required final passes as a follow-up.

## Open questions

- Should `scene.pipeline_render` be a genuinely new job type, or should
  `scene.render` grow an alternate `intent_payload` input mode alongside its
  existing `script_path` mode? A new job type keeps the two contracts
  (hand-authored script vs. generated intent) from tangling; a shared job
  type avoids duplicating dashboard/status/artifact plumbing. Not decided
  here.
- Local Docker harness routing (the other half of the original ask — "local
  dev harness sends to local dev render") needs the same env-driven dispatch
  but pointed at `127.0.0.1:8088` and a local worker instead of staging. Per
  the build plan above, this is now the deliberate first target rather than
  staging, specifically so it gets exercised before the staging proof run.
- Whether Producer should download the rendered artifact locally for
  `episode_cut()`, or whether episode-cut stitching itself should become
  harness-aware and operate on remote artifact URLs, is undecided.
- Serial-submit-and-poll vs. batch fan-out (see build plan step 4) — not
  decided; fan-out is where the actual throughput win lives, but it's a
  larger change to `producer.py`'s control flow than the dispatch branch
  alone.

## Not built

Nothing in this document has been implemented. `tools/producer.py`'s render
step is unchanged as of this writing. This update records a build plan and
sequencing decision only.
