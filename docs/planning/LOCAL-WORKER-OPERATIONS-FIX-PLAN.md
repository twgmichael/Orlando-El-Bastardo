---
title: Local Worker Operations Fix Plan
created: 2026-07-15T21:13:15-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: plan
production_area: operations
department: pipeline
status: active
canonical: true
canonical_for: local_worker_operations
wiki: true
wiki_group: Planning
wiki_page: Local-Worker-Operations-Fix-Plan
wiki_order: 170
---
# Local Worker Operations Fix Plan

Recorded 2026-07-15 after the first successful local prompt-to-Blender run.

## Problem

The local studio chat pipeline can now create jobs, and the Mac worker can
process them, but the last-mile developer operations are still too manual.
The immediate blockers and risks are:

- Worker startup depends on a hand-built environment command.
- Local docs still mix generic workflow notes with machine-specific runtime
  values.
- Detached worker startup through `nohup` is unreliable from the Codex command
  wrapper; a named `screen` session worked.
- Worker logs and status checks are not standardized.
- Repeated prompts can reuse the same `canonical_id`, causing worker output
  files under `{output_root}` to overwrite one another before they are copied
  into the job-scoped artifact store.
- The successful local runtime recipe is not captured in tracked planning docs.

## Goals

1. Make local worker start/stop/status repeatable.
2. Document the local worker control flow without committing machine-specific
   paths or private runtime values.
3. Prevent shared output path collisions when canonical ids repeat.
4. Keep fake local defaults convenient while keeping real secrets in
   environment variables or gitignored `.env.local` files.
5. Verify the touched Python modules still compile.

## Non-Goals

- Replacing `screen` with a permanent macOS `launchd` service in this pass.
- Changing canonical id semantics or asset registry uniqueness rules.
- Moving the Docker stack or worker into one process manager.
- Adding database migrations.

## Implementation Plan

### 1. Job-scoped worker output paths

Add worker support for a `{job_id}` placeholder in Blender payload paths and
script args. Update generated primitive build job payloads to write to:

```text
{output_root}/jobs/{job_id}/assets/<kind>s/<canonical_id>.glb
{output_root}/jobs/{job_id}/renders/asset_previews/<canonical_id>.png
{output_root}/jobs/{job_id}/out/asset_builds/<canonical_id>.json
```

The artifact store already copies into directories keyed by job id; this
change protects the source output tree too.

### 2. Local worker scripts

Add tracked helper scripts under `oeb-studio-harness/worker/scripts/`:

- `start-local-worker.sh` starts a named detached `screen` session.
- `stop-local-worker.sh` stops that session.
- `status-local-worker.sh` reports the screen session and, when possible,
  the local harness worker state.

Runtime values are supplied by shell environment or a gitignored worker
`.env.local` file:

```text
OEB_HARNESS_URL=<local harness URL>
OEB_ENROLLMENT_TOKEN=<worker enrollment token>
OEB_OUTPUT_ROOT=<durable project output root>
OEB_ARTIFACT_STORE_ROOT=$OEB_OUTPUT_ROOT/oeb-studio-harness/artifacts
```

The worker helper must fail instead of falling back to temporary storage when
the durable project output root is unavailable. Temporary storage makes renders
easy to lose and hard to find.

Committed docs and scripts must use placeholders for host-specific paths.
Exact machine paths belong in `docs/local/`, shell history, or gitignored
`.env.local` files.

### 3. Documentation

Update local command notes and worker planning notes with:

- Local harness URL guidance without committing machine-specific assumptions.
- Start/stop/status commands.
- Screen session name and log file.
- Output and artifact directories.
- `{job_id}` placeholder behavior.

### 4. Verification

Run focused syntax checks:

```bash
python3 -m py_compile \
  oeb-studio-harness/worker/agent/adapters/blender.py \
  oeb-studio-harness/server/app/routers/conversations.py
```

Optional live verification after the local stack is up:

```bash
curl -sS -H "Authorization: Bearer $API_ADMIN_TOKEN" \
  "$OEB_HARNESS_URL/api/v1/debug/studio-state"
```

## Follow-Up

A later pass should promote the `screen` helper into a `launchd` service for
the Mac worker, with structured logs and restart-on-failure behavior.
