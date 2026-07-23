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
- Hidden-by-default assistant JSON output using a per-message disclosure.

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
