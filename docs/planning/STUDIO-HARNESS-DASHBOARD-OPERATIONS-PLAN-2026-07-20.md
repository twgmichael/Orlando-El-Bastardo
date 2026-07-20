---
title: Studio Harness Dashboard Operations Plan
created: 2026-07-20T00:00:00-04:00
updated: 2026-07-20T00:00:00-04:00
doc_type: plan
production_area: operations
department: pipeline
status: draft
canonical: true
canonical_for: studio_harness_dashboard_operations
wiki: true
wiki_group: Planning
wiki_page: Studio-Harness-Dashboard-Operations-Plan
wiki_order: 160
---
# Studio Harness Dashboard Operations Plan

Date: 2026-07-20

Status: **PLANNED**

This plan covers the two current Studio Harness dashboard priorities from
`PROJECT-TODO.md`:

1. Add a failed jobs section to the dashboard for the last 24 hours.
2. Show worker IP address on the harness index as `worker-id (ip-address)`.

The near-term goal is operator visibility. Render failures and worker identity
should be visible from the main harness index without opening debug endpoints,
SSH sessions, or database clients.

## Context Reviewed

Current dashboard behavior lives in:

- `oeb-studio-harness/server/app/routers/dashboard.py`
- `oeb-studio-harness/server/app/templates/dashboard.html`

The dashboard already computes a `recent_cutoff` for the last 24 hours and uses
it for the latest completed jobs list. It also already shows status counts for
`pending`, `running`, `completed`, and `failed`.

Current worker state lives in:

- `oeb-studio-harness/server/app/models/worker.py`
- `oeb-studio-harness/server/app/schemas/worker.py`
- `oeb-studio-harness/server/app/routers/workers.py`
- `oeb-studio-harness/worker/agent/main.py`
- `oeb-studio-harness/worker/agent/client.py`
- `oeb-studio-harness/worker/agent/heartbeat.py`

Workers currently have a flexible `resources` JSON field, but no first-class
IP address column. Registration sends `resources` from the worker config.
Heartbeat does not currently update resource metadata.

## Item 1: Failed Jobs Section, Last 24 Hours

### Goal

Add a dedicated dashboard section for jobs with `status == "failed"` and
`updated_at >= now - 24 hours`.

Failed jobs should remain visible even when there are no active jobs and when
the failed count chip is the only status signal.

### Recommended UX

Place the section between **Active Jobs** and **Completed Jobs**.

Heading:

```text
Failed Jobs (last 24 hours)
```

Columns should mirror the completed jobs table where possible:

- Title
- Status
- Policy
- Worker
- Priority
- Updated

Add one failure-focused column if the data is cheap to retrieve:

- Reason or latest attempt error/log excerpt

First pass can skip the reason column if it requires awkward joins. The link to
the review page is the essential operator path because the review/debug pages
already surface more context for failed jobs.

### Server Plan

1. In `dashboard.py`, add:

   ```python
   failed_result = await db.execute(
       select(Job)
       .where(Job.status == "failed", Job.updated_at >= recent_cutoff)
       .order_by(Job.updated_at.desc())
   )
   failed_jobs = failed_result.scalars().all()
   ```

2. Pass `failed_jobs` into the template context.

3. Keep this list unpaginated for the first pass. The scope is explicitly last
   24 hours, so pagination should only be added if real operations produce too
   many rows.

4. If adding a failure reason, prefer a small helper that reads from the latest
   `JobAttempt.output_summary`, `JobAttempt.log_output`, or job payload fields
   without making the main query complicated. Do not block the visibility
   improvement on this.

### Template Plan

1. Add a new `<section>` after Active Jobs.
2. Use `job_review_url(j)` for each failed job title.
3. Render the status badge with the existing `status-failed` class.
4. Empty state:

   ```text
   No failed jobs in the last 24 hours.
   ```

### Tests

Add focused dashboard tests if the test harness already supports template
rendering. If not, add a unit-level helper test for the dashboard query logic
when extracting it is reasonable.

Minimum acceptance checks:

- A failed job updated inside the last 24 hours appears in the dashboard HTML.
- A failed job updated before the cutoff does not appear.
- Completed jobs still render independently.
- A failed asset review job links through the existing review URL helper.

### Acceptance Criteria

- The main harness index has a dedicated failed jobs section.
- Only failures from the last 24 hours appear.
- Each failed job links to its review/debug path.
- Existing active, completed, worker, and audit sections keep working.

## Item 2: Worker IP Address On Harness Index

### Goal

Display workers on the dashboard as:

```text
render-pc-01 (203.0.113.42)
```

This should make render machines quickly identifiable during troubleshooting,
especially when multiple workers are online or a worker needs physical-machine
attention.

### First-Pass Data Model

Use the existing `Worker.resources` JSON field for the first pass.

Recommended keys, in priority order:

```json
{
  "ip_address": "203.0.113.42",
  "hostname": "render-pc-01"
}
```

Dashboard display should look for:

1. `worker.resources.ip_address`
2. `worker.resources.primary_ip`
3. `worker.resources.host_ip`

If none is available, show only the worker id.

This avoids a database migration for an operator-facing label. A first-class
`Worker.ip_address` column can be added later if IP becomes query/filter state
or part of the worker API contract.

### Worker Reporting Plan

1. Add a small worker-side helper that discovers a useful LAN IP address.
2. Merge it into `cfg.resources` before registration.
3. Prefer the outbound route IP, because it usually reflects the interface that
   reaches the harness:

   - Open a UDP socket to the harness host or a non-routed test address.
   - Read the local socket address.
   - Fall back to hostname resolution.
   - Fall back to no value.

4. Do not fail worker startup if IP detection fails.

Registration is enough for the first pass because dashboard troubleshooting is
mostly about current known worker identity. Later, heartbeat can refresh the IP
if DHCP changes are common.

### Server Plan

No migration required for the first pass.

Optional helper in `dashboard.py`:

```python
def _worker_display_id(worker: Worker) -> str:
    resources = worker.resources or {}
    ip = (
        resources.get("ip_address")
        or resources.get("primary_ip")
        or resources.get("host_ip")
    )
    return f"{worker.id} ({ip})" if ip else worker.id
```

Register it as a Jinja global, or compute a `worker_display_names` mapping in
the dashboard route.

### Template Plan

Replace the worker ID cell content with the computed display string:

```text
worker-id (ip-address)
```

Keep the cell monospace. Do not add a separate IP column unless the label gets
too wide in real use.

### Tests

Minimum acceptance checks:

- Worker with `resources={"ip_address": "203.0.113.42"}` renders as
  `render-pc-01 (203.0.113.42)`.
- Worker with no IP still renders as `render-pc-01`.
- Existing worker list ordering and capability rendering are unchanged.

### Acceptance Criteria

- Dashboard worker rows show `worker-id (ip-address)` when IP is available.
- Missing IP does not break dashboard rendering.
- Worker registration includes best-effort IP metadata for new registrations.

## Relationship To Current Planning Tracks

### Scene Render Job Type Plan

The dashboard failed-jobs section directly supports first-class scene renders.
Long scene renders need visible failure states, especially when missing scripts,
timeouts, worker update transitions, or artifact upload failures occur.

Recommended tie-ins after the first dashboard pass:

- Ensure `scene.render` failures have clear review pages.
- Include latest progress and stale-frame state on scene render review pages.
- Keep worker update states visible next to worker identity.
- Do not hide failed `scene.render` jobs behind aggregate counts.

Note: `SCENE-RENDER-JOB-TYPE-PLAN.md` currently exists at the workspace-level
`docs/planning` path while most planning docs live under
`Orlando-El-Bastardo.src/docs/planning`. Consolidate or copy it into the source
repo planning folder before future doc-sync work so planning references resolve
from one canonical docs tree.

### Canonical ID Slug Plan

The dashboard work should not change slugging behavior. The only relevant
connection is review/debug scan value:

- Failed job titles and review links should continue to use the improved
  `canonical_id` values.
- Failed jobs from prompts such as letter-shaped ships should be recognizable
  by title, not only by UUID.

### Asset Location Orientation Standard

The dashboard work does not touch orientation rules. The connection is
operational review:

- Failed primitive builds caused by orientation, placement, or multi-view render
  issues should remain visible in the failed jobs section.
- Future failure summaries can include validation warnings for orientation
  metadata or canonical camera views.

### Schema Consolidation Track

The failed-jobs and worker-IP changes are operational UI improvements, not
schema consolidation work. Keep them separate from the larger consolidation of:

- `docs/SCHEMA.md`
- `docs/planning/SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md`
- `docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md`

Recommended schema follow-up after dashboard work:

1. Create one schema map section in `docs/SCHEMA.md` with three layers:
   conversational scene plan, primitive builder contract, canonical production
   `SceneSpec`.
2. Move shared field definitions for `shape`, `required_features`,
   `source_phrases`, `materials`, `style_details`, orientation metadata, and
   relationships into that map.
3. Keep implementation-facing rollout details in the planning docs.

### Agent Bus Plan

Dashboard failures are a future bus signal.

Do not build bus integration as part of these two dashboard items, but leave the
path clean:

- Failed job visibility is human/operator-facing now.
- Later, repeated failed jobs can file or update `stream:tooling` bus issues.
- Worker IP and update state can help the orchestrator route machine-specific
  repair tasks.

## Implementation Order

1. Add failed jobs query and dashboard section.
2. Add worker display helper and template update for IP-aware labels.
3. Add worker-side best-effort IP detection into registration resources.
4. Add focused tests for dashboard rendering and worker IP fallback behavior.
5. Smoke-test the dashboard locally with workers and synthetic failed jobs.
6. Deploy to staging and confirm recent failures remain visible on the harness
   index.

## Non-Goals

- Do not build the worker self-update executor in this pass.
- Do not change scene render routing, progress, or timeout behavior in this
  pass.
- Do not change canonical slug generation in this pass.
- Do not refactor schema docs in this pass.
- Do not build agent bus integration in this pass.
