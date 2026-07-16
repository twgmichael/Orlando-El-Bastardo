---
title: Studio Chat Endpoint Plan
created: 2026-07-15T15:04:43-04:00
updated: 2026-07-16T17:46:50-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: active
canonical: true
canonical_for: studio_chat_endpoint
wiki: true
wiki_group: Planning
wiki_page: Studio-Chat-Endpoint-Plan
wiki_order: 150
---
# Studio Chat Endpoint Plan

Recorded 2026-07-15. Status: **FIRST PASS BUILT**.

## Context

`tools/studio_chat.py` proved the first conversation-to-build workflow. It is
environment-neutral: the caller chooses the target harness through
`OEB_HARNESS_URL` or `--harness-url`.

The studio needs a chat intake surface that works the same way in each
environment:

```text
local:             http://127.0.0.1:8088/api/v1/studio-chat
staging-docker-pi: http://oeb-studio.docker-pi/api/v1/studio-chat
```

The endpoint should let a creative prompt become a structured harness job
without the human repeatedly managing CLI syntax.

## Discovery

We clarified that the endpoint should be hosted by an environment, but should
not be hardcoded to that environment.

For example:

- Local Docker can host `/api/v1/studio-chat` and submit jobs to the local
  harness when `OEB_HARNESS_URL=http://127.0.0.1:8088`.
- docker-pi can host `/api/v1/studio-chat` and submit jobs to the deployed
  harness when `OEB_HARNESS_URL=http://oeb-studio.docker-pi`.
- Either environment can be configured to target another harness if needed.
- Worker selection is a harness/runtime concern: local workers claim local jobs;
  staging workers claim staging jobs.

This separates:

1. Where the chat endpoint is running.
2. Which harness receives the created job.
3. Which local or remote LLM performs intake.

## Recommendation

Build a harness-hosted, interface-agnostic endpoint:

```text
POST /api/v1/studio-chat
```

It should accept a creative prompt and return the same useful result shape as
the current CLI:

```json
{
  "job_id": "...",
  "status": "pending",
  "canonical_id": "asset_example_A",
  "review_url": "/review/jobs/...",
  "trace_url": "/api/v1/debug/jobs/.../trace",
  "saved_llm_response": true
}
```

The endpoint should use environment/config settings rather than hardcoded
targets:

```text
OEB_HARNESS_URL
API_ADMIN_TOKEN
OEB_LLM_ENDPOINT
OEB_LLM_MODEL
OEB_STUDIO_CHAT_TARGET
```

The exact names can evolve, but the principle is fixed: endpoint routing must
be configurable per environment.

## Decisions

- Do not keep studio chat as only a Mac-local CLI.
- Do not hardcode local or docker-pi targets into the endpoint.
- Keep the endpoint interface-agnostic so Open WebUI, CLI tools, dashboards,
  and future custom UIs can all use it.
- Preserve object detail and prompt modifiers as structured scene-plan fields,
  not only as label text. The builder-side schema home for this is
  `docs/planning/SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md`; the broader canonical
  schema overview is `docs/SCHEMA.md`.
- Preserve the full prompt loop in job trace data:
  - original prompt
  - LLM prompt
  - raw LLM response
  - scene plan prompt/response
  - repair prompt/response
  - final primitive spec
  - job payload
- Return both a human review URL and a chatbot/debug trace URL.
- Keep environment targeting flexible enough to test local-to-local,
  local-to-pi, pi-to-pi, and pi-to-local workflows. The code must not prefer
  one environment; the selected environment provides the URLs and tokens.

## Acceptance Workflow

Local harness test:

```bash
OEB_HARNESS_URL=http://127.0.0.1:8088 \
API_ADMIN_TOKEN=local-admin-token \
python3 tools/studio_chat.py "build a small rectangular table with rounded corners"
```

Staging docker-pi harness test:

```bash
OEB_HARNESS_URL=http://oeb-studio.docker-pi \
API_ADMIN_TOKEN=<deployed harness admin token> \
python3 tools/studio_chat.py "build a small rectangular table with rounded corners"
```

Expected path in either environment:

1. `tools/studio_chat.py` calls `$OEB_HARNESS_URL/api/v1/studio-chat`.
2. The selected harness records the prompt loop and creates a render job.
3. An eligible worker claims the job.
4. Blender renders the primitive asset.
5. The response returns `job_id`, `review_url`, `trace_url`, and
   `canonical_id`.

The acceptance prompt should preserve detail-sensitive fields such as
`rounded_corners`, source phrases, structured shape details, orientation
metadata, and prop classification.

## Open Design Notes

The endpoint can either:

1. Run the intake process directly inside the harness API container.
2. Delegate the intake process to a configured worker or sidecar.
3. Call a configured LLM HTTP service and then submit back to the configured
   harness URL.

The safest first implementation is to reuse the proven logic from
`tools/studio_chat.py`, but move the durable behavior behind the API endpoint.
The CLI can then become a thin client of `/api/v1/studio-chat`.

## Detail Preservation Contract

The chat endpoint should prompt and repair the local LLM so meaningful creative
details pass through into structured fields. For example, "build a dining room
table with rounded corners" should produce an object with fields such as:

```json
{
  "label": "dining room table",
  "category": "surface",
  "shape": {
    "primary_form": "rectangular_table",
    "corner_style": "rounded"
  },
  "required_features": ["rounded_corners"],
  "source_phrases": ["dining room table", "rounded corners"]
}
```

Endpoint repair should compare the original prompt against the scene plan. If a
prompt modifier only appears in a label, or disappears entirely, the repair pass
should move it into `shape`, `required_features`, `materials`,
`style_details`, or `source_phrases`.

## Next Build Step

Implemented a first version of:

```text
POST /api/v1/studio-chat
```

Built behavior:

- Accept `{ "prompt": "..." }`.
- Run the same scene-plan, repair, and primitive-spec process currently used by
  `tools/studio_chat.py`.
- Submit the resulting job to the configured target harness.
- Store all prompt-loop data.
- Return `job_id`, `canonical_id`, `review_url`, and `trace_url`.
- Update `tools/studio_chat.py` so it calls this endpoint by default.

The old CLI-owned intake path remains available with:

```bash
python3 tools/studio_chat.py --legacy-local-intake "Build ..."
```
