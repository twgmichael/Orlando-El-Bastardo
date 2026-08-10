---
title: Scene Render Job Type Plan
created: 2026-07-19T16:50:26-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: plan
production_area: rendering
department: pipeline
status: draft
canonical: false
wiki: true
wiki_group: Planning
---
# Scene Render Job Type Plan

Date: 2026-07-19

Status: **PLANNED**

Updated: 2026-07-19. Added render quality tiers, ETA/progress tracking,
intermittent progress-frame artifacts for long scene renders, per-job Blender
timeout control for long final renders, and an active-job-safe worker update
process.

## Context

During the first JB100 / Ellipso Flyer / Ventradi Cruiser chase scene render,
the desired user experience was simple:

> Save this version as `JB100-pirate-escape` and send it to `render-pc-01` for
> a final render.

In practice, that request required too many hidden operator steps: locating the
right harness environment, retrieving the deployed admin token, checking worker
registration, copying the scene script to the render PC checkout, hand-building
a raw job payload, checking worker logs over SSH, and manually confirming frame
output.

The target experience is that scene renders behave like asset review renders:
a creative command submits a first-class harness job, routes to the right
Blender worker, produces stable review links immediately, and registers the
final video artifact without manual SSH or ad hoc JSON.

## Desired Flow

1. User asks:

   ```text
   Fantastic! Save this version as "JB100-pirate-escape" and send it to the
   render-pc-01 for a final render!
   ```

2. Codex saves the current scene script under the requested scene name.

3. Codex submits:

   ```http
   POST /api/v1/scene-renders
   ```

4. The harness resolves the scene script, creates the job, selects a worker,
   returns a review URL, tracks progress, and registers the final MP4.

5. Codex reports the job URL and render state without manually probing the
   render worker.

## First-Class Route

Add:

```text
POST /api/v1/scene-renders
```

Initial request shape:

```json
{
  "scene_name": "JB100-pirate-escape",
  "script_path": "tools/JB100-pirate-escape.py",
  "quality": "final",
  "width": 1920,
  "height": 1080,
  "preferred_worker_id": "render-pc-01",
  "blender_timeout_seconds": 86400
}
```

`preferred_worker_id` is optional. When omitted, the harness should route the
job to any eligible worker.

`blender_timeout_seconds` is optional. When omitted, the route should choose a
quality-aware default and include it in the worker payload. This prevents final
animation renders from inheriting a short worker-wide safety timeout.

Quality should support three operational tiers:

```text
draft   -> fastest blocking animatic, low resolution, frame count only
preview -> pretty creative review render, used to seed timing estimates
final   -> production render, seeded from preview timing and updated live
```

Default Blender timeout by quality:

```text
draft   -> 1800 seconds
preview -> 7200 seconds
final   -> 86400 seconds
```

Callers may override these defaults per job. Worker adapter config remains the
fallback safety cap when the payload does not include a timeout.

Initial response shape:

```json
{
  "job_id": "b58d2ece-b341-4d38-813c-4030a5ca03d8",
  "status": "pending",
  "review_url": "/review/scene-renders/b58d2ece-b341-4d38-813c-4030a5ca03d8",
  "trace_url": "/api/v1/debug/jobs/b58d2ece-b341-4d38-813c-4030a5ca03d8/trace"
}
```

## Harness Responsibilities

### Resolve Scene Script

The server should accept only repo-relative scene paths.

Rules:

- Reject absolute paths.
- Reject path traversal.
- Normalize separators.
- Store the requested `scene_name` and original `script_path` in the job
  payload.
- Pass the worker a resolved runtime path using `{workspace_root}`.

Example worker payload value:

```json
{
  "script_file": "{workspace_root}/tools/JB100-pirate-escape.py"
}
```

### Package Or Sync Required Files And Assets

Phase 1 should preserve the current worker model:

- Workers are expected to have a current repo checkout.
- Workers are expected to have the referenced assets available at repo-relative
  paths.
- The worker validates `script_file` before running Blender.
- Missing files fail clearly and surface on the review page.

Phase 2 should add an explicit scene bundle:

- Server builds a manifest for the scene job.
- Manifest includes the scene script and referenced assets.
- For script-driven scenes, detect obvious asset references such as
  `assets/ships/*.glb`.
- Worker downloads or receives the bundle into a job-local workspace.
- Future support should cover `.py`, `.blend`, and archived scene packages.

### Select Render Workers

Map quality to required capabilities:

```text
draft   -> ["blender.preview_render"]
preview -> ["blender.preview_render"]
final   -> ["blender.final_render"]
```

For GPU final renders, support:

```text
["blender.final_render", "gpu.cycles_render"]
```

If `preferred_worker_id` is supplied:

```text
policy = wait_for_preferred_worker
preferred_worker_id = render-pc-01
```

If no worker is supplied:

```text
policy = run_anywhere
```

### Create Stable Output And Artifact Paths

The server should create output paths, not the caller.

Proposed path pattern:

```text
{output_root}/oeb-studio-harness/scene-renders/{job_id}/JB100-pirate-escape_final.mp4
{output_root}/oeb-studio-harness/scene-renders/{job_id}/frames/
```

The scene name should be slugged before use in filenames.

### Return Review URL Immediately

The route should return a review URL as soon as the job is created.

The caller should not need to inspect raw job JSON, poll workers directly, or
construct review URLs by hand.

### Expose Progress Without SSH

The harness should expose render progress through normal API and review UI
paths.

Initial progress options:

- Worker counts rendered frames in the output frames directory.
- Worker reports latest frame count during lease renewal or via a new progress
  endpoint.
- Server stores latest progress on the active job attempt.

Review page display:

```text
Rendering frame 82 / 360
23%
worker: render-pc-01
```

The goal is that Codex can answer "is it rendering?" without SSHing into the
worker or tailing system logs.

#### Progress Enhancement

Scene renders usually move through three creative passes:

1. `draft` for fast blocking, timing, camera, and composition.
2. `preview` for a pretty-enough creative review pass.
3. `final` for the production-quality render.

The draft pass is intentionally fast, so it only needs basic frame-count
progress. The preview pass should record useful timing data. The final pass
should use the preview timing as its first ETA guess, then replace that
estimate with live final-frame timing as soon as frames begin landing.

Worker progress payload:

```json
{
  "phase": "rendering_frames",
  "quality": "final",
  "frames_rendered": 62,
  "total_frames": 360,
  "percent": 17.2,
  "seconds_per_frame": 68.5,
  "eta_seconds": 20413,
  "last_frame_at": "2026-07-19T21:24:00Z",
  "estimate_source": "current_render"
}
```

Before enough final frames exist, use prior preview timing when available:

```json
{
  "phase": "queued",
  "eta_seconds": 5400,
  "estimate_source": "previous_preview"
}
```

Useful phases:

- `queued`
- `starting`
- `rendering_frames`
- `encoding_video`
- `uploading_artifact`
- `complete`

The review page should show:

```text
Rendering frame 62 / 360 - 17% - ETA 5h 40m
```

If frame count has not changed for a threshold but the worker is still
heartbeating, show a stale-progress warning such as:

```text
Rendering, no new frame for 4m
```

### Upload Intermittent Progress Frames

For long scene renders, the worker should upload periodic still frames while
the job is running. This makes the review page useful before the final MP4 is
complete and gives the operator confidence that the render still looks right.

Trigger options:

- Every N frames, for example every 24 frames.
- Every N minutes, for example every 5 minutes.
- Always replace or highlight the latest completed frame.

Artifact type:

```text
scene.progress_frame
```

Progress-frame metadata:

```json
{
  "job_type": "scene.render",
  "scene_name": "JB100-pirate-escape",
  "quality": "final",
  "frame": 96,
  "total_frames": 360,
  "percent": 26.7
}
```

Review page behavior:

- Show the latest progress frame prominently.
- Keep only the latest few progress frames to avoid clutter.
- Link to the final MP4 once complete.
- Keep progress-frame upload failures non-fatal; they should not kill the
  render unless the final artifact upload fails.

### Store Render Timing History

Start simple by writing timing stats to completed job `output_summary`:

```json
{
  "scene_name": "JB100-pirate-escape",
  "script_path": "tools/JB100-pirate-escape.py",
  "quality": "preview",
  "width": 1280,
  "height": 720,
  "frames": 360,
  "elapsed_seconds": 840,
  "seconds_per_frame": 2.33
}
```

Later, add a dedicated `render_timings` table keyed by scene name, script path,
quality, resolution, and render engine. Final renders can use the most recent
matching preview timing as their initial estimate.

### Upload And Register Final MP4

After Blender completes, the worker should upload the final MP4 through the
existing artifact upload path.

Artifact metadata:

```json
{
  "artifact_type": "scene.final_render",
  "filename": "JB100-pirate-escape_final.mp4",
  "mime_type": "video/mp4"
}
```

The review page should expose the MP4 directly when complete.

## Worker Payload Contract

The server should translate a `scene.render` request into a Blender script job:

```json
{
  "job_type": "scene.render",
  "scene_name": "JB100-pirate-escape",
  "script_file": "{workspace_root}/tools/JB100-pirate-escape.py",
  "cwd": "{workspace_root}",
  "factory_startup": true,
  "script_args": [
    "--mode",
    "preview",
    "--width",
    "1920",
    "--height",
    "1080",
    "--output",
    "{output_root}/oeb-studio-harness/scene-renders/{job_id}/JB100-pirate-escape_final.mp4"
  ],
  "artifact_paths": [
    "{output_root}/oeb-studio-harness/scene-renders/{job_id}/JB100-pirate-escape_final.mp4"
  ],
  "artifact_type": "scene.final_render",
  "blender_timeout_seconds": 86400
}
```

The existing Blender adapter can mostly run this as script mode. It should add
special handling only where `scene.render` needs progress, bundle resolution,
or clearer scene-specific output summaries.

### Per-Job Blender Timeout

The worker should honor `payload.blender_timeout_seconds` when present:

```text
effective_timeout = payload.blender_timeout_seconds || adapter.timeout_seconds
```

This is especially important for `scene.render` final jobs. A final animation
can be healthy while taking far longer than a two-hour asset-render timeout.
Timeout should protect against runaway processes, not terminate an active final
render just because wall-clock time crossed the worker default.

Validation rules:

- Accept positive integer seconds.
- Reject zero, negative, or non-integer values at the route/schema boundary.
- Allow the server to set defaults by `quality`.
- Preserve an explicit caller override when provided.
- Include timeout metadata in job payload and completed output summary.

Operational rule:

- If frames continue landing, the progress system should be the primary health
  signal.
- If no frames land for the stale-progress threshold, surface a warning before
  timeout becomes the only failure signal.

## Worker Update Process

Scene renders expose a deployment problem: final renders can run for hours, and
the worker code may need progress or timeout fixes while a render is already
active. Updating by SSH or Ansible without job awareness can accidentally kill
the render. Worker updates should become a first-class harness operation.

### Worker Version Reporting

Each worker heartbeat/registration should include:

```json
{
  "agent_version": "0.1.0",
  "git_sha": "abc1234",
  "update_state": "idle"
}
```

The dashboard should show:

- Worker code version.
- Latest available/deployed version when known.
- Whether an update is available.
- Whether an update is queued, draining, applying, failed, or complete.

### Drain Before Update

Add a worker state or command equivalent to:

```text
draining
```

Drain behavior:

- A draining worker continues its current job.
- A draining worker does not claim new jobs.
- The dashboard shows the active job and "update pending."
- Once idle, the queued update can run automatically.

This is the default for render workers. A forced update while busy should
require an explicit destructive confirmation because it will terminate the
active Blender process.

### Harness-Triggered Worker Update

Add a harness route or worker command such as:

```http
POST /api/v1/workers/{worker_id}/update
```

Request shape:

```json
{
  "target_git_sha": "abc1234",
  "mode": "drain_then_update"
}
```

Modes:

```text
drain_then_update -> default; wait for current job to finish
update_if_idle    -> update only if no active job
force_update      -> explicit destructive update for emergency use
```

The worker should perform the update itself when safe:

1. Stop claiming jobs.
2. Sync or pull the requested code version.
3. Install/update worker dependencies when needed.
4. Restart the worker service.
5. Re-register with the new version and capabilities.

Ansible remains the fallback for machine provisioning, OS packages, GPU driver
work, and emergency repair. Normal worker app-code deploys should use the
harness update path.

### Post-Update Health Verification

After restart, the harness should verify:

- Worker heartbeat returns.
- Worker reports the expected `git_sha`.
- Required capabilities are present.
- Blender executable is available.
- GPU visibility is healthy for `gpu.cycles_render` workers.

If verification fails, surface the failure on the dashboard and keep the worker
out of the eligible pool until repaired.

### Update Safety For Scene Renders

For scene renders specifically:

- Never auto-update a worker running `scene.render` unless the job is complete
  or the update is explicitly forced.
- If a worker is missing progress-reporting code during an active render, show
  "worker update pending after current job" instead of restarting it.
- Prefer sidecar/backfill progress for active long renders when possible.
- Apply worker progress, timeout, and artifact-upload fixes before submitting
  the next final render.

## Review UI

Add a scene render review page or extend the existing job review page to show:

- Scene name.
- Script path.
- Quality.
- Resolution.
- Worker assignment.
- Job status.
- Progress.
- ETA.
- Current phase.
- Latest intermittent progress frame.
- Final MP4 link when available.
- Blender log excerpt and failure reason when failed.

Suggested route:

```text
/review/scene-renders/{job_id}
```

It may redirect internally to the generic job page at first, as long as the
response from `POST /api/v1/scene-renders` gives a stable review URL.

## CLI Helper

Add:

```text
tools/submit_scene_render.py
```

Usage:

```bash
python3 tools/submit_scene_render.py \
  --scene-name JB100-pirate-escape \
  --script tools/JB100-pirate-escape.py \
  --quality final \
  --worker render-pc-01 \
  --width 1920 \
  --height 1080
```

The helper should use `OEB_HARNESS_URL` and `API_ADMIN_TOKEN`, matching the
existing harness helpers. Long term, Codex should call this helper rather than
hand-building raw JSON.

## Tests

Add focused tests for:

- Rejecting absolute scene script paths.
- Rejecting path traversal in scene script paths.
- Creating correct required capabilities for preview and final quality.
- Setting `wait_for_preferred_worker` when a worker is specified.
- Setting `run_anywhere` when no worker is specified.
- Creating stable output paths.
- Setting per-job Blender timeout defaults by quality.
- Preserving caller-provided `blender_timeout_seconds`.
- Returning review and trace URLs immediately.
- Worker adapter handling `scene.render`.
- Worker adapter honoring payload timeout over adapter config timeout.
- Completed jobs registering an MP4 artifact.
- Failed missing-script jobs surfacing a clear error.
- Draft, preview, and final quality capability mapping.
- Progress payloads storing phase, ETA, frame counts, and estimate source.
- Progress-frame artifacts registering as `scene.progress_frame`.
- Progress-frame upload failures remaining non-fatal.
- Worker update route respects active jobs and drain mode.
- Busy scene-render workers are not restarted by default.
- Worker version/gitag SHA appears in dashboard/worker status.

## Implementation Order

1. Add server schema, service, and route for `POST /api/v1/scene-renders`.
2. Add worker adapter support for `job_type = "scene.render"` where needed.
3. Add `tools/submit_scene_render.py`.
4. Add review/debug UI fields for scene renders.
5. Add progress reporting without SSH.
6. Add worker version reporting and active-job-safe update/drain flow.
7. Add scene bundle packaging and worker download support.

## Progress Enhancement Implementation Order

1. Add `draft` quality to scene render schema and submit helper.
2. Automatically set or infer `expected_frames` for scene scripts when possible.
3. Add progress phase, seconds-per-frame, ETA, last-frame timestamp, and
   estimate-source fields.
4. Store preview timing stats in completed job `output_summary`.
5. Seed final ETA from the latest matching preview timing.
6. Upload periodic `scene.progress_frame` artifacts from the worker.
7. Show latest progress frame, phase, percent, ETA, and stale-progress warning
   on the review page.
8. Add artifact retention/pruning for progress frames.
9. Add `blender_timeout_seconds` to scene render schema, route defaults,
   submit helper, worker payload, and Blender adapter execution.
10. Add worker update/drain support so progress and timeout fixes can be
    deployed safely before final scene renders.

## Open Risks

- Script-driven scenes can reference arbitrary repo files, so dependency
  detection will be imperfect until scenes declare manifests explicitly.
- Workers can only render scripts that match their checked-out repo version
  until packaging is implemented.
- Final video upload may be large enough to need timeout and size-limit review.
- Blender script conventions are not yet standardized across scenes. The first
  route can support the current `--mode`, `--width`, `--height`, and `--output`
  contract, then generalize once more scene scripts exist.
