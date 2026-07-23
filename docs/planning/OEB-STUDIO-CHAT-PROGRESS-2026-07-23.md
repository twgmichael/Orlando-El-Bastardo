# OEB Studio Chat Progress

Date: 2026-07-23

## Related Documents

- [OEB Studio Chat Lightweight Plan](../plans/OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md)
  is the main plan and has been updated with the current implemented state and
  next primitive-registry direction.

## Summary

We advanced `oeb-studio-chat` from a transparent local Ollama chat into the
first working version of a local chat-to-harness production loop.

The main direction is now clear:

- The frontier model designs and evolves the contracts, schemas, validation,
  registry, and review policy.
- The local LLM handles constrained translation work.
- The deterministic harness and workers execute validated build/render jobs.

The local LLM should not be treated as the tool executor. It should convert
creative prompts into strict, small, buildable JSON specs that the harness can
validate, repair, and submit to workers.

## Implemented Progress

Studio chat now supports:

- Direct local Ollama chat through the harness.
- Model selector.
- Role presets.
- Editable system prompt.
- Temperature and max-token controls.
- Raw/debug view.
- Transcript export.
- Review-view shortcut:
  `["top", "bottom", "left", "right", "front", "rear", "action"]`.
- Automatic build-job creation after local LLM responses.
- Inline build/render progress cards inside the chat transcript.
- Inline render thumbnails when review artifacts are ready.
- Inline render lightbox for stepping through review images without navigating
  away from the chat.
- Hidden-by-default assistant JSON output using a per-message disclosure.
- Hidden-by-default primitive resolver output attached to the build progress
  card.
- Database-backed chat threads with a left-sidebar thread list and `New Thread`
  control.
- Append-only trace events for saved prompts, Ollama requests/responses,
  assistant JSON, resolver attempts, normalized specs, harness job payloads,
  job creation, status polling, review artifacts, failures, and inline card
  snapshots.

The build flow now:

1. Sends user prompt and recent transcript to the local LLM.
2. Receives assistant JSON.
3. Parses or repairs the JSON.
4. Falls back to deterministic intent extraction for simple primitive requests
   when the assistant JSON is malformed.
5. Creates a deterministic harness build job.
6. Requests post-build review renders.
7. Polls job/review status.
8. Shows progress and render artifacts inline in the chat turn.

## Important Fixes

### Root Dashboard

The harness root route `/` was returning `500` because app code expected the
`workers.git_sha` column, while the local Postgres database was still at
Alembic revision `0005`.

Applied:

```bash
docker exec oeb_studio_harness_local_api alembic upgrade head
```

The local DB is now at `0006_worker_update_state`, and both `/` and
`/studio-chat` resolve.

### Worker Identity Cleanup

The stale `mac-mini` local worker identity was removed from the local worker
roster, and its old worker tokens were revoked.

The active local worker identity is:

```text
render-mac-01
```

### Artifact Storage Permissions

Review render uploads failed because the API container ran as user `harness`,
but `/srv/oeb-studio-harness/artifacts` was owned by `root:root`.

Live container ownership was corrected to `harness:harness`, and Ansible was
updated so the artifact directory remains writable by the harness user.

### Failure Diagnostics

Failed job attempts already persisted diagnostic data in:

- `job_attempts.output_summary.reason`
- `job_attempts.log_output`

The review job page displays this under:

```text
Attempts -> Failure Diagnostics
```

Worker failure handling was improved so artifact upload/registration failures
persist the underlying exception and rendered artifact paths, rather than only a
generic upload failure.

### Missing Artifact Guard

Primitive build jobs were able to appear completed even when Blender emitted a
Python traceback and produced no expected artifacts. The worker adapter now
fails script jobs when declared `artifact_paths` are missing after script
execution.

This prevents post-build review jobs from being created against missing GLB
files.

### Cone Primitive Bug

A failed two-primitive request exposed that `primitive_asset_builder.py` routed
scene objects with category `cone` to `cone(...)`, but no low-level `cone`
helper existed.

Added a basic Blender cone primitive helper and tests for cone routing.

## Current Architectural Lesson

Adding one-off semantic branches for every shape or object will not scale.

The right next layer is a generic primitive registry/spec executor:

```text
user prompt
  -> local LLM translator
  -> local LLM primitive resolver/compiler
  -> harness schema validation
  -> deterministic primitive executor
  -> GLB/preview/review renders
  -> inline chat progress and artifacts
```

The local LLM can help interpret natural language into the registry, but it
must not invent new tool abilities or Blender APIs.

## Chat Memory And Trace Progress

`oeb-studio-chat` is now thread-native. The goal remains durable local/staging
chat memory that preserves both conversation context and production trace, so
progress and renders survive refreshes and can be reviewed later.

Implemented database-backed tables:

```text
studio_chat_threads
  id
  title
  environment
  default_model
  default_preset_id
  system_prompt
  review_views
  created_at
  updated_at
  archived_at

studio_chat_messages
  id
  thread_id
  role
  content
  raw
  created_at

studio_chat_build_events
  id
  thread_id
  message_id
  job_id
  asset_id
  event_type
  payload
  created_at

studio_chat_trace_events
  id
  thread_id
  message_id
  job_id
  event_type
  source
  label
  payload
  text_snapshot
  created_at
```

Implemented thread and trace API surface:

```text
GET    /api/v1/studio-chat/threads
POST   /api/v1/studio-chat/threads
GET    /api/v1/studio-chat/threads/{thread_id}
PATCH  /api/v1/studio-chat/threads/{thread_id}
POST   /api/v1/studio-chat/threads/{thread_id}/messages
POST   /api/v1/studio-chat/threads/{thread_id}/build-jobs
GET    /api/v1/studio-chat/threads/{thread_id}/events
GET    /api/v1/studio-chat/threads/{thread_id}/trace
GET    /api/v1/studio-chat/messages/{message_id}/trace
GET    /api/v1/studio-chat/jobs/{job_id}/trace
```

Current behavior:

- On page load, open the latest active thread or create one.
- Save each user message before calling Ollama.
- Save each assistant response after Ollama returns.
- Save resolver output, build-job creation, render status, artifacts, and
  failures as build events tied to the assistant message.
- Reconstruct the transcript from persisted messages plus events.
- Add a `New Thread` control.
- Auto-title threads from the first user prompt.
- Send only compact recent-thread context to the local LLM.
- Keep full production provenance in the database.

Production trace should be stored alongside chat text:

```json
{
  "assistant_json": {},
  "resolver_output": {},
  "primitive_spec": {},
  "job_payload": {},
  "review_artifacts": []
}
```

This gives us memory for creative continuity while keeping the harness audit
trail useful for debugging and staging comparison.

## Material And Quantity Fix

The prompt `Build 2 blue balls.` exposed two deterministic-side problems:

- The local LLM and resolver preserved `blue`, but Blender preview/review
  renders appeared white because the primitive builder set only
  `diffuse_color`, not the render/export material node base color.
- `quantity: 2` was collapsed to one primitive in the direct primitive path.

Fixes landed:

- `primitive_asset_builder.py` now sets Principled BSDF `Base Color` and
  `Alpha` for named primitive materials.
- The chat primitive normalization now preserves `quantity` / `count` from
  assistant JSON or prompt text.
- The primitive executor also expands raw registry primitive `quantity` /
  `count`, so direct executor specs remain robust.
- Blender smoke verification produced two blue spheres, and a review render
  from the exported GLB preserved the blue material.

## Next Chat Interface TODO

Update `oeb-studio-chat` layout and worker gating:

- Make the center chat/thread cards the only scrolling column.
- Keep the left thread/settings card fixed.
- Keep the right raw-debug card fixed.
- Keep the `Message the local OEB model` composer fixed at the bottom of the
  center column.
- Remove the standalone `Review renders ready` status box.
- Add an explicit render-worker availability indicator:
  `online` / `offline`.
- Disable the chat `Send` button whenever no render-capable worker is
  available.
- Have render workers mark themselves `busy` while running chat build/review
  render jobs, and treat busy workers as unavailable for new chat sends unless
  another render-capable worker is idle.

## Proposed Primitive Registry Direction

Add `PrimitiveRegistry v0.1` with a small, explicit supported set:

- `box`
- `sphere`
- `cylinder`
- `cone`
- `torus`
- `plane`
- `wedge`

Each primitive should have:

- canonical type
- aliases
- allowed params
- default dimensions
- material binding
- transform contract

Example target spec:

```json
{
  "action": "primitive_spec",
  "confidence": 0.88,
  "clarification_question": null,
  "unsupported_terms": [],
  "primitives": [
    {
      "id": "yellow_cone",
      "type": "cone",
      "label": "yellow cone",
      "material": "yellow",
      "transform": {
        "location": [-0.5, 0, 0.41],
        "rotation": [0, 0, 0],
        "scale": [1, 1, 1]
      },
      "params": {
        "radius1": 0.34,
        "radius2": 0,
        "depth": 0.82,
        "vertices": 32
      }
    }
  ]
}
```

## Local LLM Role

The local LLM should handle constrained compiler-like tasks:

- Detect intent: `build`, `edit`, `render`, `clarify`, `escalate`.
- Map natural language to registry primitives.
- Normalize aliases, colors, review views, and simple relationships.
- Emit small JSON jobs.
- Ask clarification when target, shape, quantity, placement, or art direction is
  too vague.
- Escalate ambiguous visual/art-direction decisions.

It should not:

- Write Blender code.
- Submit jobs directly.
- Invent primitive types outside the registry.
- Invent unavailable assets.
- Decide success after worker execution.

## Harness Role

The harness should:

- Validate local LLM JSON.
- Repair minor malformed JSON.
- Run one bounded resolver retry when a primitive type is unsupported.
- Fill deterministic defaults.
- Reject unsupported primitive types with structured errors.
- Submit worker jobs.
- Require expected artifacts before marking builds complete.
- Register assets.
- Trigger review renders.
- Show progress and diagnostics inline in chat.

## Worker Role

The worker should remain boring and deterministic:

- Read validated primitive specs.
- Dispatch each primitive through a registry-backed builder.
- Export GLB.
- Render preview.
- Upload artifacts.
- Report progress.
- Fail with useful diagnostics if required artifacts are missing.

The worker should not reason about user intent.

## Next Best Slice

1. Add `PrimitiveRegistry v0.1`.
2. Add a `primitive_shape_resolver` local LLM preset.
3. Add a backend resolver service that calls local Ollama with the registry and
   strict schema.
4. Add validation for primitive instances:
   type, id, transform, params, material, numeric bounds.
5. Compile legacy `components` and `scene_plan` into `primitives` for backward
   compatibility.
6. Update `primitive_asset_builder.py` to execute `spec.primitives` first.
7. Keep old semantic scene-object routing only as a temporary fallback.
8. Show resolver output in debug, hidden by default.

## Verification Already Run

Focused test suites passed during this work, including:

- studio chat lightweight tests
- primitive builder routing tests
- worker path expansion tests
- asset review streamlining tests

The latest focused suite reported:

```text
44 passed
```
