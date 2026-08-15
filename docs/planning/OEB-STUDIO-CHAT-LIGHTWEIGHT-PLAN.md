---
title: OEB Studio Chat Lightweight Plan
created: 2026-08-05T21:30:07-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: active
canonical: false
wiki: true
wiki_group: Planning
---
# OEB Studio Chat Lightweight Plan

Date: 2026-07-23

Status: **IMPLEMENTED FIRST SLICE; EVOLVING INTO CHAT-TO-HARNESS PRODUCTION LOOP; MILESTONE SAVE STATE, REVIEW READINESS, AND ASSET REVISION STATE IMPLEMENTED**

## Related Documents

- [Studio Chat Local LLM Output Resilience Plan](../archive/STUDIO-CHAT-LOCAL-LLM-OUTPUT-RESILIENCE-PLAN.md)
  defines tolerant ingestion, semantic-preserving normalization, deterministic
  compilation gates, bounded repair, structured diagnostics, and the
  failure-class regression strategy.
- [Scene Graph Primitive Builder Plan](SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md)
  defines the OEB Semantic Asset Graph + Operation Contract milestone. It
  records what OEB already planned independently and what later similar-editor
  research clarified as architectural reference, not source dependency.
- [OEB Studio Chat Progress - 2026-07-23](../archive/OEB-STUDIO-CHAT-PROGRESS-2026-07-23.md)
  records the implementation progress, fixes, and next architectural direction
  discovered while building and testing the local chat flow.
- [Local Asset Builder Support Notes](../archive/LOCAL-ASSET-BUILDER-SUPPORT-NOTES.md)
  captures the local asset-builder role and worker boundary decisions.
- [Conversation To Build Loop](CONVERSATION-TO-BUILD-LOOP.md)
  defines local LLM versus deterministic worker responsibilities.
- [Scene Graph Primitive Builder Plan](SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md)
  describes the request-to-render primitive pipeline.
- [Asset Location Orientation Standard](ASSET-LOCATION-ORIENTATION-STANDARD.md)
  defines OEB axis and direction semantics.
- [Studio Chat vs. Blender MCP Review Criteria](STUDIO-CHAT-VS-BLENDER-MCP-REVIEW-CRITERIA.md)
  defines the per-function review criteria and holds the draft
  function-by-function inventory produced against them; see the "Blender MCP
  Integration Direction" section below for the resulting findings.

## Purpose

`oeb-studio-chat` began as a lightweight local chat interface for talking
directly to the local LLM without routing the conversation through a frontier
model.

In this plan, **lightweight** describes the chat product surface: the UI should
stay focused, inspectable, and OEB-specific. It does not mean the development
process should avoid rigorous schema design, persistent state, revision
history, deterministic builders, or production-grade review diagnostics.

The first version should be deliberately small: a local browser UI, a minimal
backend proxy, and direct calls to Ollama. It should make local model behavior
visible, preserve raw prompts and responses, and provide a foundation for later
OEB-specific production workflows such as asset-builder requests, scene-plan
extraction, job submission, artifact links, and review-page handoff.

The first slice is now working and has grown into the first local
chat-to-harness loop: the local LLM translates a prompt into constrained JSON,
the harness validates and submits a deterministic primitive build job, the
worker exports artifacts, and review renders are shown inline in the chat.

This is not intended to replace OpenWebUI. OpenWebUI remains a good future
option for a fuller local-model cockpit. `oeb-studio-chat` should start as the
thin OEB-native layer that teaches us what controls and workflow affordances
actually matter.

## Name

The working name is:

```text
oeb-studio-chat
```

Do not use `oeb-local-chat` for this project. The chat surface should be framed
as part of the OEB studio harness/toolchain rather than a generic local model
toy.

## Goals

- Let a human chat directly with the local LLM.
- Avoid frontier-model filtering, rewriting, arbitration, or hidden mediation.
- Talk to Ollama directly through the local Ollama API.
- Keep the first version easy to run on the Mac mini.
- Show raw model behavior clearly enough for debugging and trust-building.
- Support OEB role presets without forcing structured output immediately.
- Prepare for later structured production flows.
- Keep the interface lightweight enough that it can grow inside or beside
  `oeb-studio-harness`.
- Submit validated deterministic build jobs to the harness.
- Show build, review-render, and artifact progress inline with the chat turn
  that created the work.
- Keep standalone asset review renders asset-only by default: no floor, wall,
  room, base plane, backdrop geometry, or scene shell unless the user explicitly
  asks for a location, set, room, ground, wall, or environment.
- Preserve assistant JSON and resolver/debug output without making it dominate
  the normal chat transcript.
- Persist thread history, build events, resolver output, and render artifacts
  so local and staging chat progress survives refreshes.
- Save complete append-only trace events for every local LLM, resolver,
  validation, job, review, and UI boundary crossing so the full chat-to-build
  paper trail is auditable later.
- Move from one-shot prompt-to-build behavior toward stateful conversational
  asset production: a thread should know which asset is being edited, what the
  current revision is, which named parts exist, and what changed in each edit.
- Support deterministic asset-edit deltas against named parts instead of
  asking the local LLM to regenerate assets from conversational memory.
- Preserve editable source state, especially `.blend`, alongside exported GLB
  and review renders.
- Move Studio Chat edits onto one canonical semantic asset graph and shared
  operation contract so chat, future WebGL editing, agents, tests, Blender
  render, review, and undo/redo all use the same editable state.
- Provide a recognized `save milestone` command that snapshots the current
  thread, asset state, working files, and review renders into an immutable
  reference bundle before working renders are overwritten by later iterations.
- Escalate ambiguous visual judgment and reference-image interpretation to a
  frontier vision/model path, while keeping routine proportional edits local.

## Non-Goals

- Do not build a full OpenWebUI replacement in the first slice.
- Do not add multi-user accounts, permissions, sharing, or remote access.
- Do not let the local LLM directly execute Blender or mutate files.
- Do not let malformed or unsupported local LLM output become an implicit
  worker action.
- Do not require vector databases, RAG, document ingestion, or long-term memory.
- Do not hide raw prompts or responses behind an opaque assistant abstraction.
- Do not make the local LLM responsible for final art direction.
- Do not rely on a frontier model for any part of the chat loop.
- Do not add complex multi-user chat semantics before the single-user
  thread/provenance model is reliable.
- Do not treat every follow-up request as a fresh build from prose.
- Do not let the local LLM be the source of truth for prior asset state or
  named-part geometry.
- Do not embed a full WebGL sandbox or Pascal-style editor before OEB's graph,
  operation vocabulary, revision model, and validation rules are stable.
- Do not mark visible review renders as simply failed without preserving the
  distinction between rendered files, uploaded artifacts, missing views, and
  gallery readiness.
- Do not require manual copying of working render files to preserve meaningful
  progress states.

## First Slice

The first slice provides:

- A browser-based chat page.
- A minimal local backend endpoint.
- Direct Ollama `/api/chat` integration.
- Model selection from locally available Ollama models.
- Editable system prompt.
- Temperature control.
- Maximum token control.
- A non-streaming chat path.
- Clear display of request status and errors.
- Transcript export as JSON or Markdown.
- A raw/debug panel showing request and response metadata.
- Role presets for local OEB tasks.
- Preferred review-view shortcut:
  `["top", "bottom", "left", "right", "front", "rear", "action"]`.
- Manual and automatic build-job creation.
- Inline build/review progress cards.
- Inline review render thumbnails.
- Inline render lightbox for stepping through review images.
- Hidden-by-default assistant JSON disclosures.
- Hidden-by-default normalizer/compiler JSON disclosures.

The implemented first-slice chat flow is:

```text
browser UI
  -> oeb-studio-chat backend
  -> Ollama http://localhost:11434/api/chat
  -> local model response
  -> browser UI
```

No frontier model participates in this flow.

The implemented production loop is:

```text
browser UI
  -> local LLM JSON translator
  -> harness JSON parse/repair/fallback
  -> deterministic build job
  -> primitive worker GLB/preview export
  -> post-build asset review render job
  -> inline chat progress and thumbnails
```

## Next Architectural Milestone

Studio Chat Milestone 16 is the OEB Semantic Asset Graph + Operation Contract.
It implements the next step of the Scene Graph Primitive Builder Plan.

This milestone separates what OEB already needed from what similar projects
helped clarify:

- Original OEB direction: preserve creative intent as structured named parts,
  relationships, materials, placement, modifiers, and source phrases before
  generating primitive build artifacts.
- Reference-project lesson: keep the semantic graph as the editable product,
  and make every chat, UI, agent, test, render, and undo action cross the same
  operation API.

Milestone 16 should define the canonical graph schema, shared operations,
headless compiler, validation outcomes, reviewable graph diffs, and revision
commit rules. It should defer WebGL sandbox embedding until those contracts are
stable enough to remain the single source of truth.

## Proposed Architecture

`oeb-studio-chat` should be a small web app with two layers:

```text
frontend chat UI
backend Ollama proxy
```

The backend exists for practical reasons:

- Avoid browser CORS issues with Ollama.
- Centralize local model discovery.
- Store reusable OEB role presets.
- Keep future harness integration in one place.
- Normalize errors from Ollama into friendly UI messages.
- Provide a stable local API if the frontend changes later.

The backend should not reinterpret model responses in the first slice. It
should pass user messages, system prompts, model settings, and chat history
through to Ollama as transparently as possible.

## Backend

Preferred backend shape:

```text
FastAPI service inside or adjacent to oeb-studio-harness
```

FastAPI is a good fit because the harness already uses Python/FastAPI patterns.
The first implementation can either live inside the existing harness app or as
a small sibling service. If there is no strong reason to separate it, prefer
adding it to the harness as a development-only local route group.

Suggested endpoints:

```text
GET  /api/v1/studio-chat/models
GET  /api/v1/studio-chat/presets
POST /api/v1/studio-chat/chat
POST /api/v1/studio-chat/chat/stream
POST /api/v1/studio-chat/build-jobs
GET  /api/v1/studio-chat/build-jobs/{job_id}/status
GET  /api/v1/studio-chat/threads
POST /api/v1/studio-chat/threads
GET  /api/v1/studio-chat/threads/{thread_id}
PATCH /api/v1/studio-chat/threads/{thread_id}
POST /api/v1/studio-chat/threads/{thread_id}/messages
POST /api/v1/studio-chat/threads/{thread_id}/build-jobs
POST /api/v1/studio-chat/assets
GET  /api/v1/studio-chat/assets/{asset_id}/state
GET  /api/v1/studio-chat/assets/{asset_id}/revisions
POST /api/v1/studio-chat/assets/{asset_id}/edits
POST /api/v1/studio-chat/assets/{asset_id}/milestones
GET  /api/v1/studio-chat/assets/{asset_id}/milestones
GET  /api/v1/studio-chat/milestones/{milestone_id}
GET  /api/v1/studio-chat/threads/{thread_id}/events
GET  /api/v1/studio-chat/threads/{thread_id}/trace
GET  /api/v1/studio-chat/messages/{message_id}/trace
GET  /api/v1/studio-chat/jobs/{job_id}/trace
```

Initial endpoint responsibilities:

- `GET /models`: call Ollama `/api/tags` and return available model names.
- `GET /presets`: return local role/system prompt presets.
- `POST /chat`: send non-streaming chat requests to Ollama `/api/chat`.
- `POST /chat/stream`: stream Ollama responses to the browser when practical.
- `POST /build-jobs`: validate assistant JSON and create a deterministic
  primitive build job with post-build review render configuration.
- `GET /build-jobs/{job_id}/status`: return build status, review job status,
  missing views, and uploaded render artifacts for inline chat cards.
- Asset state endpoints: create and retrieve the current editable state for a
  chat-managed asset, including base builder, revision, named parts,
  orientation, source artifacts, and review artifacts.
- Asset edit endpoint: validate a conversational edit delta against the current
  revision, submit a deterministic edit job, and create the next revision only
  when worker outputs pass review artifact checks.
- Milestone endpoints: create and retrieve immutable progress snapshots that
  copy the current working files, source state, renders, job payloads, and trace
  data into a non-overwritten reference bundle.
- Thread endpoints: persist conversation messages, settings, resolver output,
  build events, review artifacts, and failure diagnostics.
- Trace endpoints: return complete append-only audit events for threads,
  messages, and jobs.

Initial request shape:

```json
{
  "model": "oeb-qwen2.5-3b",
  "system_prompt": "You are the OEB local studio assistant...",
  "messages": [
    {"role": "user", "content": "Sketch a primitive ship builder spec."}
  ],
  "temperature": 0.2,
  "max_tokens": 2048,
  "stream": false
}
```

Initial response shape:

```json
{
  "model": "oeb-qwen2.5-3b",
  "message": {
    "role": "assistant",
    "content": "..."
  },
  "done": true,
  "raw": {
    "total_duration": 123456,
    "load_duration": 12345,
    "prompt_eval_count": 120,
    "eval_count": 340
  }
}
```

## Ollama Integration

Default Ollama base URL:

```text
http://localhost:11434
```

Configuration should allow overriding this with an environment variable:

```text
OEB_OLLAMA_BASE_URL=http://localhost:11434
```

The service should use:

```text
GET  /api/tags
POST /api/chat
```

The backend should support both streaming and non-streaming modes. The first
working version may ship with non-streaming only if that makes the slice much
faster, but the API should leave room for streaming.

Current implementation uses non-streaming chat. Streaming remains a later
ergonomics improvement.

## Frontend

The frontend should open directly into the usable chat experience. It should
not start with a marketing page or explanatory hero.

Core layout:

- Left or top control area for model, preset, temperature, and max tokens.
- Main transcript area.
- Message composer fixed near the bottom.
- Optional collapsible debug/raw panel.
- Small transcript actions such as clear, export, and copy.

Required controls:

- Model selector.
- Role preset selector.
- Editable system prompt.
- Temperature input or slider.
- Max token input.
- Streaming toggle if implemented.
- Debug/raw response toggle.
- Auto-build toggle.
- Review-view selector.
- Clear conversation.
- Export transcript.

Suggested first presets:

- General local chat.
- OEB asset-builder translator.
- OEB asset-edit translator.
- OEB scene-plan extractor.
- OEB harness-debug helper.

The first presets change system prompts and defaults. Job creation is controlled
by the UI build flow and must pass harness validation before any worker action.

## Role Presets

Role presets should be plain local configuration. A preset should define:

```json
{
  "id": "asset_builder_translator",
  "label": "Asset Builder",
  "description": "Translate creative asset requests into constrained primitive-builder specs.",
  "system_prompt": "...",
  "temperature": 0.2,
  "max_tokens": 2048
}
```

Preset IDs should be stable and machine-readable. Labels may be human-friendly.

The first version should store presets in source-controlled configuration so
they can be reviewed and improved. Later, user-local preset overrides can be
added if needed.

## Debugging And Transparency

The interface should make local model behavior inspectable.

The debug panel should show:

- Selected model.
- Active preset ID.
- System prompt.
- Temperature.
- Max tokens.
- Raw request payload.
- Raw Ollama response metadata.
- Error details when Ollama is unavailable or returns malformed data.

Transcript export should include:

- Timestamp.
- Model.
- Preset ID.
- Settings.
- Messages.
- Raw metadata when debug export is enabled.

## Relationship To OEB Studio Harness

`oeb-studio-chat` began as direct local-model chat and is now becoming the
OEB-native production surface for small local build requests.

Implemented harness-aware actions:

- Validate structured JSON from the local model.
- Convert approved chat output into normalized asset intent and deterministic
  build specs.
- Repair minor malformed JSON and recover simple primitive intent from prompt
  context.
- Convert follow-up requests into constrained asset-edit requests.
- Submit named primitive builder jobs.
- Submit asset-review render jobs after export.
- Link to `/review/jobs/{job_id}`.
- Link to `/review/assets/{asset_id}`.
- Show artifact summaries returned by the harness.
- Display build and review-render progress inline with the originating
  user/assistant exchange.
- Carry an explicit `scene_shell` decision into the deterministic build spec so
  grouped assets and semantic forms are rendered without default floor/wall
  geometry, while true locations or explicit sets can still request shells.
- Preserve the asset identity and current revision across follow-up turns so
  edits apply to a known state rather than a local-model reconstruction of
  prior chat text.
- Store before/after state for each accepted edit so changes are auditable and
  reversible.
- Keep review render status specific: a render may have produced images while
  still failing gallery-readiness because uploads, view metadata, or required
  view aliases did not satisfy the strict contract.

These actions are controlled by the chat UI. Manual `Create Build Job` remains
available, and `Auto build` can create jobs immediately after assistant output.
The harness remains responsible for validation before submission.

## Stateful Asset Edit Direction

The next production step is to turn Studio Chat from a one-shot asset builder
into a stateful asset-edit surface. Each thread can still contain ordinary
messages, but production turns should attach to a durable editable asset state.

Target flow:

```text
user request + optional reference image
  -> Studio Chat thread
  -> local LLM extracts constrained asset intent or edit delta
  -> validator resolves named parts, views, and OEB directions
  -> deterministic builder applies the delta to current asset state
  -> .blend + GLB + canonical review renders
  -> inline review thumbnails
  -> user approval or another delta
```

The current asset state should be explicit JSON, not inferred from the chat
transcript:

```json
{
  "asset_id": "bugblatter_interceptor",
  "base_builder": "primitive_ship",
  "current_revision": 42,
  "source_blend_path": "out/assets/bugblatter_interceptor/rev_042/source.blend",
  "glb_path": "out/assets/bugblatter_interceptor/rev_042/bugblatter_interceptor.glb",
  "parts": {
    "cockpit": {},
    "shoulder_pods": {},
    "spine": {},
    "large_wings": {},
    "small_wings": {},
    "engine_pods": {}
  },
  "orientation": {
    "front": "+X",
    "rear": "-X",
    "left": "-Y",
    "right": "+Y",
    "up": "+Z",
    "down": "-Z"
  }
}
```

Each follow-up request should become an edit delta:

```json
{
  "asset_id": "bugblatter_interceptor",
  "base_revision": 42,
  "target": "spine",
  "operation": "adjust_profile",
  "view": "right",
  "endpoint_direction": "down",
  "amount": 0.3,
  "preserve": ["cockpit_connection", "taper", "material"],
  "review_views": ["top", "front", "right", "action"]
}
```

The local LLM may propose the delta, but the harness owns validation:

- `asset_id` must identify a known editable asset.
- `base_revision` must match the current revision or require explicit conflict
  handling.
- `target` must resolve to a named part in the asset state.
- `operation` must be supported by the asset's base builder.
- `view`, `semantic_direction`, and axis language must resolve through the OEB
  orientation standard.
- `amount` must satisfy operation-specific bounds.
- `preserve` constraints must be recorded and passed to the deterministic
  builder.
- Ambiguous target, view, proportion, or visual judgment should ask one
  clarification or escalate.

Proposed persistence:

```text
studio_chat_assets
  id
  thread_id
  asset_id
  base_builder
  current_revision
  state_json
  source_blend_path
  glb_path
  created_at
  updated_at

studio_chat_asset_revisions
  id
  chat_asset_id
  revision
  parent_revision
  message_id
  job_id
  state_before
  edit_delta
  state_after
  source_blend_path
  glb_path
  review_artifacts
  status
  created_at
```

The first concrete builder target should be `primitive_ship`, because the
Bugblatter workflow exposed the necessary named-part contract:

- `cockpit`
- `shoulder_pods`
- `spine`
- `large_wings`
- `small_wings`
- `engine_pods`

`primitive_ship` should not be a library of ship variants. It should be a
deterministic editable builder with named parts and supported operations. The
asset state is the source of truth; the local LLM only translates the user's
requested change into a candidate delta.

## Save Milestone Direction

Working review renders may continue to be overwritten during normal iteration.
That is acceptable for active work, but Studio Chat needs a recognized command
that preserves important progress states without manual file copying.

Recognized command examples:

- `save milestone`
- `save this milestone`
- `snapshot progress`
- `save milestone as first readable wing profile`

When a user issues a milestone command, Studio Chat should create an immutable
bundle for the current thread and active asset revision. The command should not
ask the local LLM to invent a summary of filesystem state. The harness should
resolve the active thread, asset, revision, build job, review job, current
working artifacts, and current render artifacts.

Milestone command flow:

```text
chat command
  -> command recognizer identifies save_milestone intent
  -> backend validates active thread and asset/revision context
  -> harness copies current source/artifact/render files
  -> harness writes milestone manifest
  -> harness records trace event
  -> inline chat card links to the saved bundle and render images
```

The saved bundle should copy files, never move them, so normal working-output
overwrite behavior remains unchanged.

Suggested bundle layout:

```text
oeb-worker-output/milestones/
  2026-07-26_153012_bugblatter_interceptor_rev_042/
    milestone.json
    README.md
    state/
      asset_state.json
      revision_before.json
      revision_after.json
    artifacts/
      source.blend
      asset.glb
      manifest.json
      build_job.json
      review_job.json
    renders/
      top.png
      bottom.png
      left.png
      right.png
      front.png
      rear.png
      action.png
    traces/
      studio_chat_trace.json
```

`milestone.json` should be the canonical index:

```json
{
  "milestone_id": "uuid",
  "label": "first readable wing profile",
  "created_at": "2026-07-26T19:30:12Z",
  "thread_id": "uuid",
  "message_id": "uuid",
  "asset_id": "bugblatter_interceptor",
  "revision": 42,
  "build_job_id": "uuid",
  "review_job_id": "uuid",
  "source_blend_path": "artifacts/source.blend",
  "glb_path": "artifacts/asset.glb",
  "renders": {
    "top": "renders/top.png",
    "bottom": "renders/bottom.png",
    "left": "renders/left.png",
    "right": "renders/right.png",
    "front": "renders/front.png",
    "rear": "renders/rear.png",
    "action": "renders/action.png"
  },
  "trace_path": "traces/studio_chat_trace.json"
}
```

Proposed persistence:

```text
studio_chat_milestones
  id
  thread_id
  message_id
  asset_id
  revision
  label
  bundle_path
  manifest_json
  created_at
```

Milestone creation rules:

- Require an active thread.
- Prefer an active asset revision; if none exists, allow a thread-only
  milestone that saves chat messages and trace data but no render bundle.
- Copy every available current review image for the active revision.
- Preserve partial render sets and record missing views in `milestone.json`.
- Copy `.blend`, GLB, manifest/spec JSON, job payloads, and trace data when
  present.
- Store paths relative to the milestone bundle where possible.
- Never overwrite an existing milestone directory.
- Show an inline milestone card with the label, asset/revision, saved views,
  missing views, and links to bundle files.

## Reference Image Direction

Studio Chat should support references as message attachments, not as invisible
context. A reference image should be stored as an artifact and tied to the
message, thread, and asset revision that used it.

Each reference should produce recorded observations:

```json
{
  "reference_artifact_id": "uuid",
  "asset_id": "bugblatter_interceptor",
  "message_id": "uuid",
  "observations": [
    {
      "target": "spine",
      "view": "right",
      "observation": "rear endpoint should drop lower",
      "confidence": 0.72,
      "requires_frontier_review": false
    }
  ]
}
```

Routine observations can be local-model assisted if they map cleanly to named
parts and OEB directions. Ambiguous art direction, proportional judgment,
unknown parts, and reference interpretation should escalate to a frontier
vision/model path and record the escalation reason.

## Render Readiness Correction

Current review renders can visibly exist while the review job is still marked
failed. The likely failure boundary is the strict gallery-readiness contract:
requested views must match uploaded image artifacts with valid review metadata.
If a render produced files but upload provenance, view names, or aliases do not
match, the job becomes failed even though thumbnails may be visible.

Required correction:

- Centralize review-view normalization across Studio Chat, review job payloads,
  render scripts, worker upload metadata, and gallery-readiness checks.
- Normalize `rear` / `back` at one boundary and store both display label and
  canonical render view deliberately.
- Track separate states for `rendered`, `uploaded`, `registered`,
  `gallery_ready`, and `failed`.
- Keep strict failure for real upload/registration errors.
- In Studio Chat, show available thumbnails even when gallery readiness fails,
  but display the exact missing view or upload/metadata problem.
- Add trace events for review artifact state transitions so a future asset
  revision can be audited without reading worker logs first.

## Construction Graph Compiler Direction

The next architectural layer should be a generic construction graph compiler.
Primitive geometry must be an internal executable substrate, not the
conversational input contract. Studio Chat should not grow a helper for each
shape, letter, object, or scene. The local LLM should describe asset intent,
parts, materials, relationships, orientation, and semantic construction. The
harness should normalize that intent into deterministic build operations.

Target flow:

```text
user prompt
  -> local LLM asset intent
  -> harness normalizer
  -> optional one-pass local LLM normalization feedback
  -> construction graph
  -> deterministic executable build ops
  -> GLB/.blend/preview/review renders
  -> inline chat progress and artifacts
```

The local LLM output should stay strict only at the container boundary:

- valid JSON
- stable top-level fields
- no Blender code
- no shell commands
- no direct filesystem mutation

The flexible content should include:

- `asset_intent`
- `parts`
- `materials`
- `relationships`
- `orientation`
- `semantic_geometry`
- `construction_notes`
- `clarification_question`
- `escalation_reason`

Example asset intent shape:

```json
{
  "action": "build",
  "confidence": 0.86,
  "clarification_question": null,
  "escalation_reason": null,
  "asset_intent": {
    "name": "two blue tubes with a yellow ball and red cube",
    "kind": "prop",
    "parts": [
      {
        "id": "left_tube",
        "role": "left vertical tube",
        "material": "blue",
        "semantic_geometry": {"type": "tube", "orientation": "vertical"}
      },
      {
        "id": "right_tube",
        "role": "right vertical tube",
        "material": "blue",
        "semantic_geometry": {"type": "tube", "orientation": "vertical"}
      },
      {
        "id": "center_ball",
        "role": "yellow ball between tubes",
        "material": "yellow",
        "semantic_geometry": {"type": "sphere"},
        "relationships": [{"between": ["left_tube", "right_tube"]}]
      },
      {
        "id": "right_cube",
        "role": "red cube on the right",
        "material": "red",
        "semantic_geometry": {"type": "cube"},
        "relationships": [{"right_of": "center_ball"}]
      }
    ],
    "construction_notes": "Keep the tubes vertical and place the ball between them."
  }
}
```

The normalizer should then produce a construction graph:

```json
{
  "version": "0.1",
  "asset_id": "asset_two_blue_tubes_yellow_ball_red_cube_A",
  "nodes": [
    {
      "id": "left_tube",
      "semantic_geometry": {"type": "tube", "orientation": "vertical"},
      "material": "blue"
    }
  ],
  "constraints": [
    {"type": "between", "target": "center_ball", "anchors": ["left_tube", "right_tube"]},
    {"type": "right_of", "target": "right_cube", "anchor": "center_ball"}
  ],
  "review_views": ["top", "bottom", "left", "right", "front", "rear", "action"]
}
```

The construction graph compiler owns the conversion from semantic geometry and
relationships into executable builder operations. It may use primitives such as
boxes, cylinders, spheres, bevels, curves, strokes, or mesh operations, but
those are implementation details.

If the local LLM returns useful intent in a compiler-unfriendly shape, the
harness should run a normalizer feedback pass:

```text
I preserved this asset_intent, but I cannot compile semantic_geometry because
it is not in compiler-friendly construction graph form. Normalize it without
inventing new assets. Preserve the user intent, parts, materials, and
relationships. Return JSON only.
```

Use one retry by default, two at most. If normalization still fails, preserve
the full intent, show a diagnostic or clarification question, and do not submit
a render job that pretends the asset compiled.

Primitive validation still matters, but only after normalization:

- allowed executable op types
- material names and material parameters
- transform shapes and numeric bounds
- relationship constraints that can be solved deterministically
- artifact paths and review-view metadata

This keeps the local LLM useful without letting it invent Blender APIs, and it
keeps deterministic workers responsible for actual geometry creation.

## Threaded Chat Memory Direction

The next major UX/backend slice should make `oeb-studio-chat` thread-enabled.
The purpose is not broad RAG or autonomous memory; it is durable project memory
for the chat-to-harness loop.

The database should store:

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
```

The UI should:

- Open the latest active thread on load, or create one if none exists.
- Provide `New Thread` and `Archive Thread`.
- Auto-title a thread from the first user prompt.
- Save the user message before the Ollama call.
- Save the assistant response after the Ollama call.
- Rebuild the visible transcript from stored messages plus build events.
- Keep progress cards, render thumbnails, resolver JSON, and failure
  diagnostics attached to the message that caused them.

Build events should capture production provenance, not just chat text:

```json
{
  "assistant_json": {},
  "resolver_output": {},
  "primitive_spec": {},
  "job_payload": {},
  "review_artifacts": []
}
```

The local LLM should receive only a compact recent-thread context. The full
thread and production trace should remain in the harness database for audit,
debugging, staging comparison, and future structured OEB production actions.

## Complete Trace Ledger Enhancement

Threaded chat memory should stay UI-friendly, but we also need a complete
audit trail for later review. Add one append-only trace table:

```text
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

Keep `studio_chat_threads`, `studio_chat_messages`, and
`studio_chat_build_events` as the fast reconstruction path for the normal chat
UI. Use `studio_chat_trace_events` as the full reference ledger.

Simple rule:

```text
Every boundary crossing writes a trace event.
```

Trace event types should include:

- `chat.request.created`
- `chat.user_message.saved`
- `ollama.request.sent`
- `ollama.response.received`
- `assistant.message.saved`
- `assistant.json.parse_attempted`
- `assistant.json.parse_failed`
- `assistant.json.parsed`
- `resolver.request.sent`
- `resolver.response.received`
- `resolver.validation_failed`
- `resolver.retry_requested`
- `resolver.output.accepted`
- `spec.normalized`
- `build.job_payload.created`
- `build.job_created`
- `build.status_polled`
- `review.job_detected`
- `review.rendered`
- `review.artifact_uploaded`
- `review.artifact_registered`
- `review.artifacts_detected`
- `review.ready`
- `review.failed`
- `asset.state.created`
- `asset.edit.requested`
- `asset.edit.validated`
- `asset.revision.created`
- `asset.revision.failed`
- `milestone.requested`
- `milestone.created`
- `milestone.failed`
- `ui.card_snapshot`
- `export.created`

The trace ledger should save:

- Exact user prompts.
- Full Ollama request payloads.
- Full Ollama raw responses.
- Assistant text exactly as returned.
- JSON parse attempts, parsed output, and parse errors.
- Resolver prompts, raw responses, retries, and validation errors.
- Accepted normalized asset intent, construction graphs, and executable build
  specs.
- Generated harness job payloads.
- Created job responses.
- Meaningful build/review status transitions.
- Asset state snapshots and revision deltas.
- Milestone manifests, copied artifact paths, copied render paths, and missing
  view diagnostics.
- Reference artifact observations and escalation decisions.
- Final inline card state.
- Artifact URLs and metadata.

Use one helper so the implementation stays small:

```python
record_studio_chat_trace(
    db,
    thread_id,
    event_type,
    source,
    label,
    payload,
    message_id=None,
    job_id=None,
    text_snapshot=None,
)
```

The debug panel can remain session-focused in the short term. Add separate
trace endpoints for deep review:

```text
GET /api/v1/studio-chat/threads/{thread_id}/trace
GET /api/v1/studio-chat/messages/{message_id}/trace
GET /api/v1/studio-chat/jobs/{job_id}/trace
```

This gives the chat two memory layers:

- Normal chat memory: small, readable, optimized for UI rehydration.
- Trace ledger: complete, append-only, optimized for review and audit.

## Relationship To OpenWebUI

OpenWebUI should remain a candidate for robust general-purpose local model use.

Recommended division:

- `oeb-studio-chat`: small, OEB-specific, transparent, workflow-aware.
- OpenWebUI: broader local chat, model management, heavier UI features,
  multi-chat ergonomics, and possible long-term local model operations.

The project should not try to outgrow OpenWebUI in generic chat features. It
should specialize in OEB production workflows.

## Security And Boundaries

The first version should bind locally only.

Recommended default:

```text
127.0.0.1
```

The UI should not expose filesystem write actions, shell execution, Blender
jobs, or harness job submission until those actions have explicit validation
and approval flows.

The backend should treat Ollama output as untrusted text. Structured output
should be parsed and validated before any future production action.

Current build submission follows this boundary: the local LLM emits JSON, the
harness validates/normalizes it, and deterministic workers execute only the
validated job payload.

## First Implementation Milestone

Milestone 1 is complete:

- A local browser page can open the chat UI.
- The UI can list local Ollama models.
- The user can select `oeb-qwen2.5-3b` or another available local model.
- The user can edit the system prompt.
- The user can send a message.
- The assistant response comes directly from Ollama.
- Errors are displayed clearly when Ollama is unavailable.
- The user can clear and export the transcript.
- No frontier model is in the runtime path.

## Later Milestones

Docker-based test containers are the expected verification path for server
tests, migrations, and chat-to-harness integration checks.

Milestone 2 is substantially complete:

- Add OEB role presets.
- Add transcript import/export.
- Add better raw request/response inspection.
- Add preferred review-view shortcut.
- Add hidden-by-default assistant JSON.

Remaining Milestone 2 work:

- Add streaming responses.
- Add transcript import.

Milestone 3 is partially complete:

- Add structured JSON mode.
- Add schema validation for asset-builder and asset-edit outputs.
- Add repair prompts for malformed local output.
- Add explicit escalation markers for ambiguous requests.
- Add deterministic fallback for simple malformed asset-intent requests.

Remaining Milestone 3 work:

- Replace primitive-job front-door validation with broad asset-intent
  validation.
- Add construction graph normalization for semantic geometry, parts,
  materials, and relationships.
- Add a local LLM normalizer feedback pass for useful but compiler-unfriendly
  intent.
- Add bounded retry for unsupported or uncompileable semantic output.

Milestone 4 is partially complete:

- Add harness job preview creation.
- Add explicit user approval before job submission.
- Add review URL display.
- Add artifact links.
- Add auto-build mode for validated local chat output.
- Add inline progress and render artifact cards.
- Add asset-only review enforcement for chat-originated standalone assets:
  `scene_shell: false` by default, `scene_shell: true` only for explicit
  location/set/environment requests.

Remaining Milestone 4 work:

- Add richer job preview before submission.
- Add clearer manual approval modes for higher-risk actions.
- Add normalizer/compiler output visibility in debug.

Milestone 5:

- Add OpenWebUI companion documentation.
- Decide whether OpenWebUI becomes the preferred general local chat surface
  while `oeb-studio-chat` remains the OEB production surface.

Milestone 6:

- Add database-backed studio chat threads.
- Persist user and assistant messages.
- Persist resolver/build/review/failure events tied to messages.
- Rehydrate transcript and inline render cards after refresh.
- Add `New Thread` and `Archive Thread`.
- Keep local and staging storage schemas aligned.

Milestone 7:

- Add append-only `studio_chat_trace_events`.
- Record every local LLM request/response, resolver attempt, parse/validation
  event, normalized spec, job payload, job creation result, status transition,
  render artifact update, and final UI card snapshot.
- Add trace endpoints for thread, message, and job audit views.
- Keep trace loading separate from normal chat transcript loading so the UI
  remains fast.

Milestone 8:

- Add persistent editable asset state for chat-managed assets.
- Add `studio_chat_assets` and `studio_chat_asset_revisions`.
- Add `asset_edit_request` schema for named-part deltas.
- Add `POST /api/v1/studio-chat/assets/{asset_id}/edits`.
- Add deterministic `primitive_ship` builder support for named parts and
  bounded edit operations.
- Save `.blend` source artifacts, GLB exports, review renders, and before/after
  state for every accepted revision.
- Add optimistic revision checking so edits target the expected current state.
- Add rollback/revert support by selecting a prior revision as the active state.

Milestone 9:

- Add reference image attachments to Studio Chat messages.
- Store reference images as artifacts tied to message, thread, asset, and
  revision.
- Record structured visual observations.
- Route ambiguous visual judgments to a frontier vision/model escalation path.
- Keep routine named-part proportional edits local when validation is
  deterministic.

Milestone 10:

- Correct review readiness semantics for chat and asset revision workflows.
- Centralize canonical review-view normalization.
- Separate rendered/uploaded/registered/gallery-ready/failure status.
- Show partial thumbnails with exact diagnostics when gallery readiness fails.

Milestone 11 is implemented:

- Add recognized `save milestone` / `snapshot progress` chat commands.
- Add `studio_chat_milestones`.
- Add milestone create/list/detail endpoints.
- Copy current `.blend`, GLB, manifests, job payloads, trace data, and all
  current review renders into an immutable milestone bundle.
- Preserve partial render sets with explicit missing-view diagnostics.
- Add inline milestone cards with links to saved bundle files and render images.
- Keep working render overwrite behavior unchanged outside saved milestones.

Remaining Milestone 11 verification:

- Apply migration `0009_studio_chat_milestones` in the Docker-backed local
  database.
- Run the server test suite in the Docker test container.
- Exercise `save milestone`, `save milestone as ...`, and `snapshot progress`
  against a completed chat render.
- Confirm saved bundle links return files through
  `/api/v1/studio-chat/milestones/{milestone_id}/files/{relative_path}`.
- Confirm disk fallback captures review renders when artifact registration or
  gallery readiness is incomplete.

Milestone 12 is implemented:

- Correct review readiness semantics before deeper asset-edit work.
- Centralize review-view normalization across Studio Chat, review job payloads,
  renderer output, worker upload metadata, artifact registration, and gallery
  readiness.
- Make `rear` / `back` normalization explicit at one boundary and preserve
  display labels separately from canonical renderer names.
- Track separate statuses for rendered, uploaded, registered, gallery-ready,
  and failed.
- Update inline chat cards to show available thumbnails even when gallery
  readiness fails.
- Add exact diagnostics for missing view, missing file, upload failure,
  registration failure, and metadata mismatch.
- Add Docker tests that reproduce the current failure mode where renders exist
  but the chat/render process is marked failed.

Milestone 13 is implemented:

- Add persistent editable asset state for chat-managed assets.
- Add `studio_chat_assets` and `studio_chat_asset_revisions`.
- Add asset state, revision list, and `asset_edit_request` endpoints.
- Create or update the active asset state when Studio Chat submits a
  deterministic build job.
- Record each accepted edit delta as a reversible before/after revision.
- Add optimistic revision checks so stale edits return a conflict instead of
  mutating the active asset state.
- Preserve `.blend` and GLB source paths when the build payload exposes them.
- Keep the local LLM responsible for intent/delta translation only; keep
  deterministic workers responsible for compile, build, export, and review.

Milestone 14 is implemented:

- Add the asset-edit compiler path that turns recorded edit deltas into
  deterministic worker jobs.
- Add active-asset selection in the chat UI so follow-up prompts attach to the
  correct asset and base revision.
- Add rollback/revert by selecting a prior revision as the active state.
- Add before/after review cards for edit revisions.

Milestone 15 is implemented:

- Add first-class UI controls for browsing revision history and invoking
  rollback/revert without raw API calls.
- Add explicit before/after thumbnail pairing for edit revisions after the
  compiled rebuild review job completes.
- Add local LLM prompt examples and tests for producing
  `asset_edit_request` against active asset context.
- Expand deterministic edit operations only at the generic construction-graph
  level: named targets, transforms, material changes, relationship-preserving
  proportional changes, and compile diagnostics.

Milestone 16 is implemented:

- Add the canonical OEB Semantic Asset Graph for stable parts, mathematical
  geometry definitions, transforms, materials, relationships, attachments,
  constraints, groups, construction notes, and revision identity.
- Add one headless operation compiler for `add`, `remove`, `replace`, `move`,
  `rotate`, `attach`, `detach`, `recolor`, `resize`, `group`, `ungroup`, and
  `undo`.
- Validate revision identity, intent/operation agreement, graph references,
  positive scales, preserved constraints, and attachment cycles before
  mutation.
- Return explicit `compiled`, `needs_repair`, `needs_clarification`,
  `unsupported`, or `invalid` results with selected targets, structured
  diagnostics, proposed graph state, and reviewable path-level diffs.
- Make Studio Chat edits and rollback use the graph compiler; rejected
  proposals create neither a revision nor a render job.
- Expose graph summary, part catalog, constraints, inspect, propose, validate,
  apply, undo, and existing render-job behavior through agent-friendly HTTP
  resources and tools.
- Keep primitive specs as a derived Blender-worker projection while the graph
  is authoritative.
- Defer the WebGL sandbox, Pascal-style embedding, and the earlier browser UX
  verification items until the graph contract survives real workflows.

Milestone 17:

- Treat every local LLM response as untrusted, evolving input and preserve the
  complete raw request and response before parsing.
- Add a broad asset-intent envelope that preserves rich intent, unknown fields,
  named parts, relationships, materials, modifiers, semantic geometry, and
  construction notes.
- Add tolerant JSON ingestion with narrowly scoped repair and an auditable
  repair/default log.
- Add idempotent normalization for aliases, kinds, identifiers, materials,
  transforms, directions, review views, and recoverable omissions without
  reducing semantic detail.
- Move strict invariant validation to the deterministic compiler boundary and
  return explicit `compiled`, `needs_repair`, `needs_clarification`,
  `unsupported`, or `invalid` outcomes.
- Enforce a single submission gate: only `compiled` results may create build or
  render jobs.
- Add one focused repair pass by default and a second only for explicitly
  recoverable validation classes; stop safely after exhaustion.
- Replace generic internal-server errors with structured diagnostics containing
  stage, code, reason, preserved fields, retry count, next action, and trace ID.
- Test schema contracts, invariants, properties, and representative failure
  classes rather than every exact local LLM response.
- Maintain a curated corpus of real local LLM responses, adding fixtures only
  when they expose a new behavior class or semantic-preservation regression.
- Verify the compiler gate, repair exhaustion, diagnostics, and no-submission
  guarantees in Docker-backed integration tests.

## Blender MCP Integration Direction

Blender now has an official experimental MCP server (Blender Lab) that lets
language models control Blender, alongside a separate, widely-used community
BlenderMCP project. This raises the question of which parts of
`oeb-studio-chat` should be kept, adapted, or dropped once OEB integrates
with the Blender MCP ecosystem instead of designing a competing Blender
protocol from scratch.

Corrected architecture (OEB sits above/alongside Blender MCP, not in place
of it):

```text
ChatGPT or local model
        │
        ▼
Official Blender MCP Server
        │
        ▼
Open Blender desktop session
        ▲
        │
OEB Studio harness
```

OEB Studio keeps ownership of the production layer regardless of which
Blender MCP implementation is used underneath: canonical asset identity,
Blueprint execution, SceneSpec/ShotSpec, revision history and checkpoints,
render orchestration, asset promotion, permissions and validation, and
project memory. Blender MCP owns tool discovery/invocation against the live
Blender session.

Evaluation scope, per [Studio Chat vs. Blender MCP Review
Criteria](STUDIO-CHAT-VS-BLENDER-MCP-REVIEW-CRITERIA.md): the **official
Blender Lab MCP server only**, for now — the community BlenderMCP project is
a fallback if the official server proves structurally inadequate, not
evaluated in parallel.

### Findings from the function-by-function inventory (draft, pending MCP schema export)

27 grouped entries across `services/studio_chat.py`, `routers/studio_chat.py`,
`routers/studio_chat_ui.py`, and `tools/studio_chat.py` were catalogued
against the review criteria. No MCP install/inspection has happened yet, so
no verdict is final — these are the structural findings that will shape the
eventual keep/drop calls:

- **Studio Chat never drives a Blender session today.** Every entry is "no"
  on viewport/session control (criterion 3). The system authors a
  constrained `PrimitiveBuildSpec` (`build_method: "blender_primitives"`)
  and enqueues a generic harness `Job`; actual Blender execution happens
  downstream, outside these files. This means most of the current surface
  is naturally decoupled from whichever Blender MCP mode gets adopted — it's
  a spec-authoring/orchestration layer, not a Blender-control layer, so it
  is not automatically replaced just because Blender MCP exists.
- **No arbitrary code execution surface exists today.** Every entry is "no"
  on criterion 4 — no `bpy`, `subprocess`, `exec`, `eval`, or `Popen`
  anywhere in the service/router code, and the LLM prompts explicitly
  forbid writing Blender code or inventing Blender APIs. This already
  avoids the exact risk Blender's own MCP warning calls out (unrestricted
  model-generated code execution), and that constraint must be preserved
  through any future adapter layer rather than loosened to match a
  more permissive MCP tool.
- **~21 of 27 entries provisionally lean "keep" as OEB-owned** — they
  implement one of the eight production-layer concerns above (thread/asset
  persistence, SceneSpec compilation, build-job orchestration, canonical
  asset/revision/graph-edit/revert, milestones) and have no Blender-control
  surface to compare against an MCP tool in the first place.
- **2 entries need follow-up before any lean is trustworthy:**
  - `tools/studio_chat.py` (580-line standalone CLI) reimplements its own
    copy of the spec-compilation logic instead of importing the service
    module — possibly dead/duplicate code, independent of the MCP
    decision.
  - The legacy admin-gated bare `POST /studio-chat` endpoint looks
    superseded by the thread/build-jobs pipeline; current usage is
    unconfirmed.
- **Auth-coverage gap flagged, not yet confirmed.** Only the legacy `POST
  /studio-chat` endpoint shows explicit `require_admin` at the router
  level; thread/message/asset/edit/revert/milestone endpoints show no
  endpoint-level auth in `studio_chat.py` itself. May be covered by
  app-wide middleware not visible in that file — needs confirming
  separately from the MCP work, since "permissions and validation" is one
  of the OEB-owned concerns these functions are supposed to satisfy.
- **Not yet traced: the job-worker path that actually invokes Blender**
  (downstream of the rows that create/poll build jobs and locate rendered
  review images, e.g. `tools/export_blender.py`). That trace, plus
  installing and exporting the official MCP server's actual tool list and
  schemas, is required before criterion 1 (overlap with Blender MCP tools)
  can be evaluated — those downstream pieces are the most likely candidates
  for eventual replacement by an MCP-based adapter.

Full per-row detail lives in the "Function Inventory" section of the
[review criteria doc](STUDIO-CHAT-VS-BLENDER-MCP-REVIEW-CRITERIA.md).

### Job-worker trace and open-question resolution (step 3-4 findings)

**What invokes Blender for a queued Job.** Traced the full path from job
creation to Blender execution:

- `routers/conversations.py:210` `_build_job_payload` (imported and reused
  by `routers/studio_chat.py:1163,2768`) hardcodes `script_file:
  "tools/primitive_asset_builder.py"` and `required_capabilities:
  ["blender.command_line"]` into the job payload. The spec is serialized to
  JSON and passed as a `--spec-json` CLI argument — never as code.
- `oeb-studio-harness/worker/agent/adapters/blender.py:34`
  `BlenderCLIAdapter` is the worker that claims capability-matching jobs.
  Its `_execute_script` (line 259) builds and runs, via `subprocess.run`
  (line 556): `blender --background [--factory-startup] --python
  <script_file> -- <script_args...>`. This is a **one-shot headless
  subprocess per job** — it launches and exits with the job, confirming at
  the worker level (not just the Studio Chat service layer) that criterion
  3 is "no": there is no persistent, already-open desktop session for
  Studio Chat jobs to attach to.
- `tools/primitive_asset_builder.py` (the script actually run) has no
  `eval`, `exec`, `compile`, `subprocess`, or `os.system` calls — it parses
  `--spec-json` as data via the standard JSON module and builds geometry
  through direct `bpy` calls, not dynamically-constructed code.
- Net finding for criterion 4: the Studio Chat build path has **no
  arbitrary code-execution exposure end-to-end**, from HTTP request through
  worker subprocess to the Blender script — not just within the files the
  original inventory pass covered. `script_file` in this path is a
  hardcoded server-side constant, never taken from request/LLM input.
  (Note: `BlenderCLIAdapter` is generic and does accept `script_file` from
  other job payloads outside Studio Chat, e.g. `scene_render`/asset-review
  jobs — those were not audited here and are out of scope for this pass,
  since Studio Chat itself never sets `script_file` to anything other than
  the hardcoded constant.)

**`tools/studio_chat.py` — verdict: live CLI, not dead code.** Its default
behavior (no flags) POSTs to `{harness_url}/api/v1/studio-chat` — i.e. it
*is* the primary caller of the row-8 legacy endpoint (studio_chat.py:120-129,
468). Its own duplicated spec-compilation logic only runs behind the
explicit opt-in `--legacy-local-intake` flag (studio_chat.py:125-129), which
the CLI's own `--help` text describes as running "instead of calling
/api/v1/studio-chat." `docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md:22,143,174-223`
confirms this was a deliberate migration, not accidental drift: the CLI
started as the owner of the intake logic, that logic was moved behind the
`/api/v1/studio-chat` endpoint, and the CLI became a thin client of it by
design — the old path was intentionally kept as a documented fallback
(`--legacy-local-intake`), not left behind by mistake. One data point
supporting that the fallback path specifically is rarely exercised: it
contains a latent bug (`tools/studio_chat.py:110` references an undefined
`text` variable instead of the `request` parameter, inside
`default_components_for`) that would raise `NameError` on a
motorcycle/motorbike request — a bug that active use would likely have
surfaced. No test file imports `tools.studio_chat`; all `studio_chat`
imports in the test suite target `app.services.studio_chat` /
`app.routers.studio_chat` (the FastAPI service), confirming the CLI itself
is an untested, manual/ops tool, not a component under CI coverage.

**Bare `POST /studio-chat` (row 8) — verdict: live, not superseded.** It is
mounted at `/api/v1/studio-chat` (`main.py:138` mounts `studio_chat_router`
at `/api/v1`; `routers/studio_chat.py:109` sets prefix `/studio-chat`), and
it is exactly the endpoint `tools/studio_chat.py` targets by default (see
above) — so this endpoint and the CLI are two ends of the same still-active
path, not two independently-legacy artifacts. It remains distinct in
purpose from the newer thread/build-jobs pipeline (rows 4-6, 16-18): the
bare endpoint is a single-shot "one message in, one job out" flow used by
the CLI/ops tooling, while the thread pipeline is the persisted,
multi-turn, UI-driven flow. Both are live; neither supersedes the other
today. This does **not** resolve the `require_admin`-only auth-coverage
question raised for the thread/asset/edit/revert/milestone endpoints in the
inventory — that remains open and independent of this finding.

Both entries are correspondingly annotated as resolved in the [review
criteria doc's Function Inventory](STUDIO-CHAT-VS-BLENDER-MCP-REVIEW-CRITERIA.md).

### Next steps

1. ~~Install and inspect the official Blender MCP server; export its
   actual tool list and JSON schemas~~ **Done** — see "Official Blender
   MCP Server — Installed & Inspected" in the [review criteria
   doc](STUDIO-CHAT-VS-BLENDER-MCP-REVIEW-CRITERIA.md). Key finding:
   there is no fixed tool catalog to diff against — the entire surface is
   one generic `execute(code)` operation; `weak_sandbox.py` blocks only 5
   specific things and otherwise allows unrestricted `bpy`/Python access,
   matching the maintainers' own published security warning.
2. ~~Test whether it controls a persistent, already-open Blender desktop
   session, or only headless/one-shot runs~~ **Done** — both exist: an
   interactive `bpy.app.timers`-polled mode for a persistent session, and
   a `blender --background --command blender_mcp` headless mode
   (deferred/long-running responses unsupported in the latter). Default
   `localhost:9876` either way. Recommendation recorded in the review
   criteria doc: do not route OEB's existing headless build path through
   this mechanism — it would trade a zero-code-execution path for one
   with acknowledged unguarded code execution, for no capability gain.
3. ~~Trace the currently-unexplored job-worker path~~ **Done** — see
   "Job-worker trace and open-question resolution" above. Studio Chat's
   build path is headless/one-shot end-to-end with no code-execution
   exposure; criterion 1 (MCP tool overlap) for rows 16-20 still needs the
   official server's exported schema from step 1-2 before it can be
   evaluated.
4. ~~Resolve the two open follow-ups~~ **Done** — see above. Both
   `tools/studio_chat.py` and the bare `POST /studio-chat` endpoint are
   live and intentionally paired, not dead code; no deletion or retirement
   is warranted by this pass.
5. Steps 1-4 are now grounded in evidence. Given step 1's finding (no
   per-tool schema, single generic code-execution operation), "build an
   adapter for missing production operations" doesn't reduce to a
   tool-by-tool gap analysis the way it would for a schema'd server —
   there's nothing to diff. The production layer (SceneSpec compilation,
   canonical asset identity, revision history, render orchestration, etc.
   — rows 4-27 of the Function Inventory) stays in OEB regardless, per
   criterion 2. Still not rolling a separate Blender MCP server.
6. Disable or tightly gate any arbitrary Python execution the official or
   community MCP server exposes before any adapter path can reach it —
   Studio Chat's existing no-code-execution constraint (see Security And
   Boundaries) is the bar to preserve, not relax. Given step 1's finding,
   this isn't a config toggle to flip on an otherwise-safe server — the
   official server's only capability *is* unguarded code execution, so
   "gating" means never exposing it to unreviewed/automated callers, not
   configuring a safer mode of it.

## Decisions

- The project name is `oeb-studio-chat`.
- The first implementation should be lightweight and OEB-native.
- The local chat path must go directly to Ollama, not through a frontier model.
- The first version should focus on transparent chat, model selection, presets,
  and transcript/debug visibility.
- Harness mutation, Blender execution, and artifact creation are permitted only
  through validated harness job creation, not direct local LLM execution.
- Standalone chat assets render without default floor/wall scene shells.
  Location shells are opt-in through explicit location/set/environment intent
  and the normalized `scene_shell` flag.
- OpenWebUI remains a future robust companion, not the starting dependency.
- The generic semantic graph and headless operation compiler are the canonical
  editable core; primitive geometry is a derived worker projection.
- The next memory step is database-backed threaded chat with persisted messages
  and production events.
- Complete reference memory should use an append-only trace ledger rather than
  overloading the normal chat transcript or raw debug panel.
- The next production capability is persistent editable asset state with
  reversible revisions and named-part edit deltas.
- The first named-part edit builder should be `primitive_ship`, focused on
  deterministic operations against explicit parts rather than regenerated prose.
- Review-render status must distinguish available thumbnails from
  gallery-readiness failure so useful output is not hidden behind a generic
  failed state.
- Progress preservation should use explicit immutable milestone bundles rather
  than changing the working-render overwrite behavior.
- Local LLM output is an expressive, untrusted asset-intent proposal. The
  harness may parse, preserve, normalize, clarify, repair, or reject it, but
  may submit a worker job only after deterministic compilation returns
  `compiled`.
- Regression coverage targets contracts, invariants, properties, and distinct
  failure classes. Exact real responses become fixtures only when they reveal
  a new behavior class.
