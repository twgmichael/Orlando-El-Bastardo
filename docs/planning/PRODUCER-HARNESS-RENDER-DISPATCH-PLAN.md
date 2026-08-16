---
title: Producer Harness Render Dispatch Plan
created: 2026-08-15T00:00:00-04:00
updated: 2026-08-15T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: draft
canonical: true
canonical_for: producer_harness_render_dispatch
wiki: true
wiki_group: Planning
wiki_page: Producer-Harness-Render-Dispatch-Plan
wiki_order: 200
---
# Producer Harness Render Dispatch Plan

Recorded 2026-08-15. Status: **design doc, scoping only — nothing built from
this document.**

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

## Open questions

- Should `scene.pipeline_render` be a genuinely new job type, or should
  `scene.render` grow an alternate `intent_payload` input mode alongside its
  existing `script_path` mode? A new job type keeps the two contracts
  (hand-authored script vs. generated intent) from tangling; a shared job
  type avoids duplicating dashboard/status/artifact plumbing. Not decided
  here.
- Local Docker harness routing (the other half of the original ask — "local
  dev harness sends to local dev render") needs the same env-driven dispatch
  but pointed at `127.0.0.1:8088` and a local worker instead of staging. The
  proposed design already covers this for free (it is just which
  `OEB_HARNESS_URL`/worker is configured), but it has not been exercised or
  verified against the local Docker stack specifically.
- Whether Producer should download the rendered artifact locally for
  `episode_cut()`, or whether episode-cut stitching itself should become
  harness-aware and operate on remote artifact URLs, is undecided.

## Not built

Nothing in this document has been implemented. `tools/producer.py`'s render
step is unchanged as of this writing.
