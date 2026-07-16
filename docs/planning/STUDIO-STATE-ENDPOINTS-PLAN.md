# Studio State Endpoints Plan

Recorded 2026-07-15. Status: **FIRST PASS BUILT**.

## Context

The studio harness is becoming a conversational production system. A human
creative prompt now flows through local LLM planning, scene repair, primitive
builder job creation, worker execution, Blender output, artifacts, and review
pages.

As the loop grows, debugging by copy/paste is becoming too slow. The chatbot
needs a small number of read-only harness endpoints that expose the current
studio state and the full prompt-to-render trail.

## Discovery

We identified two different visibility needs:

1. A single-job trace endpoint for deep debugging of one build.
2. A broader studio-state endpoint for situational awareness across projects,
   jobs, workers, failures, and active production tasks.

The first endpoint has been implemented:

```text
GET /api/v1/debug/jobs/{job_id}/trace
```

It is admin-token protected and returns the full prompt loop for one job:

- Job record.
- Original creative request.
- Local LLM prompt and raw response.
- Scene-plan prompt and raw response.
- Parsed scene plan.
- Repair prompt and raw response.
- Repaired scene plan.
- Final primitive spec.
- Worker attempts, including logs and output summaries.
- Registered artifacts and review URLs.

This is enough for targeted debugging when the human provides one job ID.

The second endpoint has also been implemented:

```text
GET /api/v1/debug/studio-state
```

It is admin-token protected and returns a compact studio overview:

- Active projects.
- Workers with capabilities and inferred current job IDs.
- Queued jobs.
- Running jobs.
- Recently completed jobs.
- Recently failed jobs.
- Recent attempts, including failure reasons.
- Recent artifacts with review links.
- Review links and trace links for listed jobs.

## Remaining Gap

The trace endpoint alone does not answer broader questions like:

- What projects are active?
- What jobs are queued, running, failed, or recently completed?
- Which worker is online or busy?
- What prompt/build loops are currently producing suspicious output?
- What failures are repeating?
- What review links are ready for creative inspection?

Existing endpoints already expose pieces of this:

```text
GET /api/v1/projects
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}/attempts
GET /api/v1/jobs/{job_id}/artifacts
GET /api/v1/debug/jobs/{job_id}/trace
```

The studio-state endpoint now provides the first single-response answer to
“what is happening in the studio right now?” Further work can make it richer.

## Recommendation

Maintain and extend the read-only, admin-token protected studio-state endpoint:

```text
GET /api/v1/debug/studio-state
```

This should return a compact operational summary, not every full log. It should
be designed for chatbot consumption first: enough context to decide what to
inspect next, with links or IDs for deeper trace calls.

Implemented response shape:

```json
{
  "generated_at": "2026-07-15T00:00:00Z",
  "projects": [],
  "workers": [],
  "jobs": {
    "queued": [],
    "running": [],
    "recent_completed": [],
    "recent_failed": []
  },
  "recent_attempts": [],
  "recent_artifacts": [],
  "review_links": [],
  "debug_links": []
}
```

Each job item should include:

- `job_id`
- `title`
- `status`
- `created_at`
- `updated_at`
- `assigned_worker_id`
- `canonical_id` when available from payload/spec
- `creative_request` when available
- `review_url`
- `trace_url`
- short failure reason when available

Each worker item should include:

- `worker_id`
- `status`
- `last_heartbeat_at`
- `current_job_id`
- `capabilities`

## Decisions

- Keep these endpoints interface-agnostic. Open WebUI, CLI tools, dashboards,
  and chatbot escalation flows should all be able to consume the same API.
- Keep the debug endpoints read-only.
- Protect debug endpoints with the admin token.
- Prefer compact summaries for studio-state and full detail for per-job trace.
- Do not expose direct database access as the primary workflow. Purpose-built
  read-only endpoints are safer, easier to paste into a chat, and easier to
  stabilize as the schema evolves.
- Do not include rendered image bytes in the first studio-state response.
  Include review and artifact URLs first; image embedding can be added after
  the trace/state API proves useful.

## Open Questions

- Should studio-state include planned tasks from `PROJECT-TODO.md`, or only
  database-backed runtime state?
- Should failed jobs be grouped by repeated failure reason?
- Should the endpoint include only recent records by default, with query params
  like `?limit=20`, `?project_id=...`, and `?include_completed=true`?
- Should chatbot-facing debug URLs be absolute URLs using `OEB_HARNESS_URL`, or
  relative URLs that the client expands?

## Implemented First Pass

Implemented:

- Active projects.
- Workers and capabilities.
- Inferred worker `current_job_id` from running job assignment.
- Queued jobs.
- Running jobs.
- Recent failed jobs.
- Recent completed jobs.
- Recent attempts with failure reason.
- Recent artifacts with review URLs.
- Trace URL for every listed job.

This will let the chatbot inspect the studio without asking the human to copy
database rows or manually stitch together project/job/attempt/artifact state.

## Next Build Step

After this endpoint is exercised against real production data:

- Add repeated-failure grouping.
- Add optional filters like `project_id`, `status`, and `include_completed`.
- Decide whether URLs should be absolute or relative.
- Add image-preview retrieval or embedding once artifact access is settled.
