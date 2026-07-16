# Local Worker Operations Fix Plan

Recorded 2026-07-15 after the first successful local prompt-to-Blender run.

## Problem

The local studio chat pipeline can now create jobs, and the Mac worker can
process them, but the last-mile developer operations are still too manual.
The immediate blockers and risks are:

- Worker startup depends on a hand-built environment command.
- Local docs still imply `localhost`, while the working worker URL is
  `http://127.0.0.1:8088`.
- Detached worker startup through `nohup` is unreliable from the Codex command
  wrapper; a named `screen` session worked.
- Worker logs and status checks are not standardized.
- Repeated prompts can reuse the same `canonical_id`, causing worker output
  files under `{output_root}` to overwrite one another before they are copied
  into the job-scoped artifact store.
- The successful local runtime recipe is not captured in tracked planning docs.

## Goals

1. Make local worker start/stop/status repeatable.
2. Document the known-good local harness URL, token defaults, screen session,
   output roots, and artifact roots.
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

Defaults target the local Docker stack:

```text
OEB_HARNESS_URL=http://127.0.0.1:8088
OEB_ENROLLMENT_TOKEN=local-worker-enrollment-token
OEB_OUTPUT_ROOT=/tmp/oeb-harness-worker-output
OEB_ARTIFACT_STORE_ROOT=/tmp/oeb-harness-worker-artifacts
```

Real deployments should override these values from shell env or a gitignored
`.env.local`.

### 3. Documentation

Update local command notes and worker planning notes with:

- The `127.0.0.1` local harness URL.
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

Optional live verification after the local Docker stack is up:

```bash
curl -sS -H "Authorization: Bearer local-admin-token" \
  http://localhost:8088/api/v1/debug/studio-state
```

## Follow-Up

A later pass should promote the `screen` helper into a `launchd` service for
the Mac worker, with structured logs and restart-on-failure behavior.
