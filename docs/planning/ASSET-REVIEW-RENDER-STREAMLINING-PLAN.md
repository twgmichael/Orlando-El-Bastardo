# Asset Review Render Streamlining Plan

Date: 2026-07-18

Updated: 2026-07-19. Status: **IMPLEMENTED for the main operator flow**.
Ventradi Cruiser, JB5k, Ellipso Flyer, and JB100 all resolve through the review
asset path. JB100 final-quality GPU review renders completed on `render-pc-01`,
and the live gallery supports action-plus-angle lightbox navigation.

Updated: 2026-07-20. Asset review renders now use the same user-facing render
quality language as scene renders: `draft`, `preview`, and `final`. See
`HARNESS-RENDER-QUALITY-LANGUAGE.md`.

## Context

During the first existing-model review render runs for Ventradi Cruiser, JB5k,
and Ellipso Flyer, the desired user experience was simple:

> Render all views for this existing model and show them on the network review
> page.

In practice, those requests required too many manual steps: locating asset
paths, choosing the correct harness target, checking whether the Mac worker was
really running, repairing artifact storage, backfilling PNG bytes, and verifying
gallery URLs by hand.

The target experience is that a request like "Render all views for Ellipso
Flyer" submits the correct `asset.review_render` job, routes to a healthy
Blender worker, uploads artifacts directly to docker-pi, and returns a ready
gallery URL with no follow-up repair.

## What Caused the Extra Prompts

1. Asset names were not first-class.

   We had to manually discover that:

   - Ventradi Cruiser maps to `assets/ships/ventradi_cruiser.glb`
   - JB5k maps to `assets/ships/jb5k.glb`
   - Ellipso Flyer maps to `assets/ships/ellipso_flyer_mk1.glb`

   The harness did not provide a user-facing asset picker, alias table, or
   registry lookup that could resolve friendly names.

2. Job submission still exposed operator details.

   The submit helper required explicit harness URLs and tokens. That made a
   normal creative request feel like an administrative action.

3. Worker liveness and worker correctness were separate.

   The menu icon could be running while the actual worker path was stale,
   stopped, or using old in-memory code. The harness showed heartbeat state, but
   did not prove the worker could complete the full render/upload contract.

4. Review render completion allowed broken artifact state.

   The first successful render runs registered PNG metadata with Mac-local
   `/Volumes/...` paths. The docker-pi review page had database rows, but could
   not read the files.

5. Artifact upload failures fell back too quietly.

   Worker byte upload failed for two code reasons:

   - `upload_artifact_file()` did not accept the `size_bytes` field passed by
     artifact metadata.
   - `httpx.AsyncClient` was passed a synchronous file object as request
     content instead of raw bytes.

   The worker then fell back to metadata-only registration, causing "completed"
   jobs with broken galleries.

6. docker-pi artifact storage was not initially durable.

   The live compose deployment was missing an artifact bind mount and
   `ARTIFACTS_ROOT`, so the API tried to write under
   `/srv/oeb-studio-harness/artifacts` inside the container and hit permission
   errors. This has since been fixed, but the deployment plan should treat it as
   a required preflight.

## Desired Flow

1. User asks:

   ```text
   Render all views for Ellipso Flyer.
   ```

2. The harness or helper resolves the friendly asset name:

   ```json
   {
     "asset_id": "ellipso_flyer_mk1",
     "asset_path": "assets/ships/ellipso_flyer_mk1.glb"
   }
   ```

3. The request creates one `asset.review_render` job:

   ```json
   {
     "asset_id": "ellipso_flyer_mk1",
     "asset_path": "assets/ships/ellipso_flyer_mk1.glb",
     "views": ["top", "bottom", "left", "right", "front", "back", "action"],
     "quality": "preview"
   }
   ```

   The `quality` field may be `draft`, `preview`, or `final`.

4. The harness routes the job only to a Blender worker that passes review-render
   preflight checks.

5. The worker renders locally, then uploads PNG bytes to:

   ```text
   POST /api/v1/jobs/{job_id}/artifact-files
   ```

6. The server writes PNGs under its configured artifact root and creates
   artifact records with:

   - `provenance: uploaded`
   - `storage_path` under `/srv/oeb-studio-harness/artifacts/...`
   - `public_url` for `/review/artifacts/{artifact_id}`
   - `review_metadata.view`
   - `review_metadata.asset_id`

7. The job completes only after all requested views have uploaded and are
   readable by the review page.

8. The response gives one URL:

   ```text
   http://oeb-studio.docker-pi/review/assets/{asset_id}
   ```

## Implementation Plan

### 1. Asset Name Resolution

Add a harness-level asset lookup for existing assets. It should support:

- Canonical id, such as `ellipso_flyer_mk1`
- Friendly names, such as `Ellipso Flyer`
- Common aliases, such as `JB5k`
- Preferred source format, usually `.glb` for review renders

The lookup can start as a lightweight registry seeded from known asset files and
grow into the broader asset registry later.

Acceptance criteria:

- "Ventradi Cruiser" resolves to `ventradi_cruiser`.
- "JB5k" resolves to `jb5k`.
- "Ellipso Flyer" resolves to `ellipso_flyer_mk1`.
- Ambiguous matches return a clear list of candidates.

### 2. Single Review Render Command Path

Make `asset.review_render` the normal route for all existing-model review
requests. The submit helper should be a convenience wrapper around this route,
not a separate workflow.

Recommended default:

```text
views = top,bottom,left,right,front,back,action
quality = preview
policy = run_anywhere or wait_for_preferred_worker when explicitly targeted
```

Acceptance criteria:

- The helper can submit by asset id or friendly name.
- The helper defaults to the configured production/staging harness target.
- The user does not need to provide a harness URL for routine local-network
  operation.

### 3. Worker Review-Render Preflight

Before a worker claims `asset.review_render`, it should prove it can satisfy the
contract:

- Blender command is available.
- `tools/render_asset_review.py` exists under `workspace_root`.
- The requested asset path exists.
- The harness `/artifact-files` endpoint is reachable.
- The server-side artifact root is writable.

Workers that fail preflight should advertise themselves as unhealthy for
`blender.preview_render` until the issue is fixed.

Acceptance criteria:

- A worker with missing Blender does not claim render jobs.
- A worker with a stale code checkout does not claim render jobs.
- A worker that cannot upload bytes does not claim render jobs.

### 4. Make Byte Upload Required for Review Renders

For `asset.review_render`, metadata-only artifact registration should not be a
successful fallback. If byte upload fails, the job should fail with a clear
reason.

For other job types, path-only registration can remain as a compatibility mode
if needed.

Acceptance criteria:

- Review render artifacts always use `provenance: uploaded`.
- Review render `storage_path` is server-local.
- A completed review render job always has readable image URLs.
- Failed uploads produce a failed job, not a broken gallery.

### 5. Gallery Readiness Checks

Add a job completion check that confirms every requested view has a readable
artifact before marking the result "gallery ready."

The asset review page should distinguish:

- Pending
- Running
- Completed but missing artifacts
- Gallery ready
- Failed

Acceptance criteria:

- The dashboard does not imply a broken gallery is ready.
- The asset page shows exactly which views are missing if any upload fails.
- Job `output_summary` includes `gallery_url`, `artifact_urls`, and
  `missing_views`.

### 6. Managed Worker Runtime

Run the Mac worker through a durable launch path, not only an interactive menu
process.

Current practical path:

```text
oeb-studio-harness/worker/scripts/start-local-worker.sh
```

This starts the worker in a detached `screen` session using the worker
virtualenv and shared project output root.

Future polish:

- Add a LaunchAgent for automatic startup.
- Make the menu icon reflect actual server heartbeat and current job state.
- Add "Restart Worker" and "Open Logs" actions.

Acceptance criteria:

- The worker survives shell/app restarts.
- The dashboard heartbeat reflects actual worker process health.
- Restarting the menu icon cannot leave a stale hidden worker behind.

### 7. Review Render UI

Add a simple web UI affordance:

- Asset page or asset index button: "Render all views"
- Optional quality selector: preview/final
- Job status panel while rendering
- Automatic link to the latest gallery when complete

Acceptance criteria:

- A non-technical operator can request renders from the browser.
- No token, curl, SSH, or shell command is needed for routine render requests.

## Non-Goals

- Do not remove the backfill tools; keep them for historical repair and disaster
  recovery.
- Do not require the Mac external drive to be shared over the network.
- Do not make docker-pi read worker-local paths.
- Do not treat path mapping as the primary artifact delivery mechanism.

## Milestones

### Milestone 1: Reliable Headless Path

- Keep docker-pi artifact bind mount and `ARTIFACTS_ROOT` in the managed
  deployment.
- Keep worker byte upload fixed.
- Disable metadata fallback for `asset.review_render`.
- Add tests proving upload failures fail the job.

### Milestone 2: Name-Based Submission

- Add known-asset registry entries for Ventradi Cruiser, JB5k, JB100, and
  Ellipso Flyer.
- Allow submit helper and API to accept friendly names.
- Return one gallery URL immediately after submission.

### Milestone 3: Operator UI

- Add asset index/review page "Render all views" button.
- Show live job status and gallery readiness.
- Add missing-view diagnostics.

### Milestone 4: Managed Worker UX

- Promote the screen launcher or LaunchAgent to the standard Mac worker runtime.
- Add worker preflight status to the dashboard.
- Update the menu icon to reflect actual harness worker health.

## Success Criteria

The streamlined flow is complete when all four requests below work without
manual repair:

```text
Render all views for Ventradi Cruiser.
Render all views for JB5k.
Render all views for JB100.
Render all views for Ellipso Flyer.
```

Each request should end with:

- One completed `asset.review_render` job.
- Seven PNG artifact rows.
- All artifact rows using `provenance: uploaded`.
- All artifact rows stored under docker-pi artifact storage.
- A gallery page that immediately shows the action render and six-angle grid.

2026-07-18 GPU proof: JB100 completed a seven-view final-quality
`asset.review_render` on `render-pc-01` using Blender Cycles CUDA, 1280x960,
96 samples. Follow-on scheduler work should request `gpu.cycles_render` for
GPU-targeted final review renders so CPU-only final workers do not claim them.

2026-07-19 gallery/retention update:

- The review lightbox now includes the action render and the six angle renders,
  with Back/Forward buttons and left/right keyboard navigation.
- The inline action preview is reduced to half-size while preserving full-size
  inspection in the lightbox.
- Review render image artifacts older than 7 days are pruned by the harness
  maintenance loop.
- The latest completed render set for each active review asset is protected, so
  active galleries keep their action and angle images.
