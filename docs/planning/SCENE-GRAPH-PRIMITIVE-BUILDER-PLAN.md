---
title: Scene Graph Primitive Builder Plan
created: 2026-07-15T09:25:43-04:00
updated: 2026-08-15T00:00:00-04:00
doc_type: plan
production_area: assets
department: pipeline
status: active
canonical: true
canonical_for: scene_graph_primitive_builder
wiki: true
wiki_group: Planning
wiki_page: Scene-Graph-Primitive-Builder-Plan
wiki_order: 140
---
# Scene Graph Primitive Builder Plan

Recorded 2026-07-15. Status: **PLANNED**.

## Goal

Turn flexible creative language from tele-play or conversation into immediate
primitive 3D blocking passes for sets, locations, props, and simple assets.

The primitive builder is a storyboard and layout department, not a final asset
generator. It should quickly preserve creative intent, make spatial decisions
visible, and produce reviewable renders while final assets are sourced, built,
or replaced from modular kits.

## Original OEB Direction

This plan predates the later Pascal Editor discussion. The original OEB
direction, recorded 2026-07-15, was already to move beyond prompt-shaped
primitive strings into a semantic scene plan that preserves objects,
relationships, placement, modifiers, and source phrases before any Blender
primitive is generated.

The original requirements were:

- Keep creative language as the user-facing input.
- Have the local LLM translate language into structured semantic intent.
- Preserve named objects, relationships, modifiers, materials, and placement.
- Use deterministic harness code to validate, repair, and compile the plan.
- Generate primitive build specs and review renders as artifacts of intent.
- Avoid hardcoding every possible room, prop, staging phrase, or object type in
  Python.

That direction came from OEB's own conversation-to-build work and the failure
mode of component strings being too lossy for production use.

## Problem

The first conversation-to-build slice proved the harness can produce rendered
primitive scenes, but it also exposed the core limitation:

- Component strings alone are too lossy for natural language.
- Prompt directives help, but should not carry the whole system.
- Python should not hardcode every possible room, prop, or staging phrase.
- Natural language relationships like "facing", "mounted on", "left of", and
  "behind" need to survive as structured build instructions.

The harness needs the local LLM to translate creative text into a semantic
scene plan, and then a deterministic builder should render that plan using
reusable category and relationship rules.

## Target Pipeline

```text
creative request
  -> local LLM scene-plan extraction
  -> repair/validation pass
  -> semantic asset graph
  -> validated operation compiler
  -> primitive build spec
  -> harness job
  -> Blender primitive render
  -> review page
```

The creative user should only provide the creative request. Prompt directives,
schema rules, validation, repair, logging, and job submission belong inside the
harness.

The semantic graph is the editable product. Primitive build specs, GLBs,
Blender scenes, previews, and review renders are deterministic realizations or
artifacts of a graph revision unless production-specific work makes one of
those realizations authoritative.

## Shared Operation Contract

All graph changes must be expressed as structured commands and must pass
through the same headless compiler and validator whether they originate in
Studio Chat, a WebGL editor, an agent/MCP client, a test, or a future embedded
editor.

The first generic operation vocabulary is:

- `add`
- `remove`
- `replace`
- `move`
- `rotate`
- `attach`
- `recolor`
- `resize`
- `group`
- `undo`

Each proposed operation must include the requested intent, named target or
targets, expected base revision, parameters, and constraints that must remain
true. Before mutation, the harness must:

1. Resolve and display the selected targets.
2. Compare the proposed operation with the requested intent.
3. Compile the operation deterministically.
4. Validate graph invariants and constraints.
5. Produce a reviewable diff.
6. Commit a new revision only after validation succeeds.

This is the boundary that prevents an instruction such as "add a tube" from
silently compiling into "replace the cone." A failed proposal preserves the
current graph unchanged and returns a structured diagnostic suitable for
retry, clarification, or human correction.

The core must operate without a browser. The browser viewport, chat, undo
history, render queue, tests, and agents are clients of one canonical graph and
revision stream rather than owners of parallel state.

## Lessons From Similar Projects

Similar open source 3D sandbox and WebGL editor projects sharpen the roadmap,
but they do not replace OEB's plan or become source dependencies by default.
The useful lesson is architectural: interactive 3D editing works best when the
scene is editable semantic state, not only a mesh export or a one-shot build
result.

Borrow these ideas as references:

- A semantic scene graph that remains the source of truth.
- Structured edit operations shared by chat, UI, agents, tests, and render.
- Agent/MCP-style separation between resources, tools, prompts, and mutation
  authority.
- Live editor state that can be inspected, diffed, validated, undone, and
  rendered.
- Human review affordances before committing risky mutations.

Do not borrow source code, schemas, or application boundaries until OEB's own
contracts are stable.

## Pascal Editor Reference Boundary

Pascal Editor is an architectural reference, not a current dependency. It is
useful because it reinforces the "editable semantic scene" direction OEB
already had, and because its agent-facing scene manipulation model is close to
the workflow OEB wants for chat, WebGL, and future MCP-style tools.

Use Pascal Editor to clarify priorities:

- The graph is the editable product.
- The operation API is the shared mutation boundary.
- Agents inspect and propose changes; deterministic tools validate and apply.
- Browser editing, chat editing, and headless automation must share one core.

Do not embed a full external editor yet. First stabilize:

1. OEB semantic asset graph and constraint representation.
2. Revision identity, optimistic concurrency, diffs, and undo.
3. Deterministic operation vocabulary, compiler, and validator.
4. Agent resources and mutation tools separated from translation prompts.
5. A lightweight WebGL sandbox that exercises the same headless core.

After those contracts survive real editing workflows, evaluate whether
Pascal-style components reduce implementation cost without becoming a second
source of truth.

## TODO

- [x] Define the OEB semantic asset graph schema for assets, scene parts,
  geometry definitions, transforms, materials, relationships, attachments,
  constraints, construction notes, and revision identity.
- [x] Define the shared operation contract for `add`, `remove`, `replace`,
  `move`, `rotate`, `attach`, `detach`, `recolor`, `resize`, `group`,
  `ungroup`, and `undo`.
- [x] Build a headless operation compiler that consumes graph state and
  operation requests, then returns `compiled`, `needs_repair`,
  `needs_clarification`, `unsupported`, or `invalid`.
- [x] Add graph invariant and constraint validation before any operation can
  commit a new revision.
- [x] Produce reviewable graph diffs showing selected targets, intended
  operation, preserved constraints, and before/after state before mutation.
- [x] Make Studio Chat asset edits use the graph and operation contract instead
  of ad hoc primitive-state patching.
- [x] Expose agent/MCP-style scene resources separately from mutation tools:
  scene summary, selected revision, part catalog, constraints, inspect,
  propose, validate, apply, undo, and render.
- [ ] Add a lightweight WebGL sandbox only after the graph and operation
  contract are stable enough for both chat and headless tests.
- [ ] Evaluate Pascal-style embedding or component reuse only after OEB's graph,
  operation API, revision model, and validation rules survive real editing
  workflows.

Milestone 16 implementation:

- `app/schemas/semantic_asset_graph.py` defines the canonical graph, operation,
  result, diagnostic, and diff contracts.
- `app/services/semantic_asset_graph.py` provides the browser-independent
  normalizer, validator, compiler, graph diff, summary, part catalog, and
  primitive-builder projection.
- `GET /api/v1/studio-chat/assets/{asset_id}/graph` exposes inspectable graph
  resources.
- `POST .../operations/propose` and `POST .../operations/validate` compile
  without mutation.
- `POST .../operations/apply` uses the same request contract and commits only
  a `compiled` proposal; the existing edit route uses this same core.
- The existing revert route compiles through `undo`.
- Accepted edits continue to create deterministic Blender build/review jobs;
  rejected proposals create neither a revision nor a job.
- Primitive arrays remain a derived worker projection inside asset state while
  the semantic graph is authoritative.

## Scene Plan Schema

The intermediate schema before the current primitive build spec — object
categories, relationship vocabulary, and the detail/modifier pass-through
contract — is now specified in full in `docs/CONVERSATIONAL-SCENE-SCHEMA.md`
(consolidated 2026-08-15 from this doc and
`docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md`). `docs/SCHEMA.md` covers the
downstream canonical production schema this layer feeds into.

## Repair Pass

Add a local LLM repair pass after initial scene-plan extraction.

The repair pass should compare the creative request against the scene plan and
fix omissions before job creation.

Inputs:

- original creative request
- full prompt sent to the local LLM
- raw local LLM response
- parsed scene plan
- simple named-object extraction from the creative request

Repair responsibilities:

- Ensure every named object in the creative request appears in `objects`.
- Preserve quantities such as "two chairs" or "3 trees".
- Preserve size hints such as "large", "small", "wide", "tall".
- Preserve shape and style modifiers such as "rounded corners", "thin legs",
  "brushed metal", "tapered", "curved", "soft", and "wide".
- Preserve exact source phrases for important modifiers so trace debugging can
  show why a feature appeared.
- Preserve mounting and placement hints such as "on wall", "in corner",
  "behind desk", and "on table".
- Extract relationships such as "facing", "next to", "left of", and
  "mounted on".
- Avoid inventing unavailable final assets; primitive placeholders are fine.

Repair output should be the same scene-plan schema.

If the repair pass still cannot produce valid JSON, the harness should either:

- fall back to a deterministic component-list plan, or
- ask a clarification question if the request is too ambiguous.

## Logging And Audit Trail

Persist every major transformation so prompt patterns can be studied.

Already implemented:

- `jobs.description`: creative request
- `jobs.payload.conversation.creative_request`
- `jobs.payload.conversation.spec`
- `jobs.llm_response`: raw local LLM response

Add next:

- raw scene-plan response
- parsed scene plan
- repair prompt
- repaired scene plan
- validation warnings
- final primitive build spec

These can initially live in `jobs.payload.conversation` before adding dedicated
tables.

## API And Schema Changes

Add optional fields to conversation job payloads:

```json
{
  "creative_request": "...",
  "llm_response": "...",
  "scene_plan": {},
  "repaired_scene_plan": {},
  "spec": {}
}
```

Keep the current `spec.components` path working while the scene-plan path is
introduced. This keeps existing jobs and review pages compatible.

## Builder Changes

Update `tools/primitive_asset_builder.py` in stages:

1. Accept `scene_plan` in addition to the existing primitive build spec.
2. Convert each scene-plan object to a primitive object using category rules.
3. Place objects with deterministic default layout rules.
4. Apply relationships after initial placement.
5. Orient objects for `faces` relationships.
6. Mount wall items flush against walls.
7. Include scene-plan metadata in the manifest.

The builder should never silently drop an object. Unknown categories should
render as labeled fallback primitives using the object id.

## Local LLM Prompt Strategy

Keep prompt directives in code, not in the creative user's message.

The intake prompt should ask for:

- strict JSON
- scene type
- object list with ids, labels, categories, count, size, placement, mounting
- relationship list
- no external assets
- primitive-friendly interpretation

The repair prompt should be narrower:

- compare request to plan
- list missing named objects
- fix quantities and relationships
- output only the corrected scene plan JSON

## Rollout Plan

### Phase 1: Documented Scene Plan Shape

- Add Pydantic schemas for `ScenePlan`, `SceneObject`, and
  `SpatialRelationship`.
- Add unit-level parser/normalizer tests for common prompts.
- Keep existing `PrimitiveBuildSpec` intact.

### Phase 2: Local LLM Scene Plan Extraction

- Update `tools/studio_chat.py` to request a scene plan first.
- Store raw scene-plan response and parsed scene plan.
- Derive the current primitive build spec from the scene plan for compatibility.
- Keep `--dry-run` showing every transformation.

### Phase 3: Repair Pass

- Add simple named-object extraction from the creative request.
- Add repair prompt and local LLM call.
- Store repair response and repaired plan.
- Use repaired plan for job submission when valid.

### Phase 4: Builder Scene-Plan Support

- Teach `primitive_asset_builder` to read `scene_plan`.
- Build primitives by object category.
- Apply relationships and orientation.
- Preserve component-list fallback.

### Phase 5: Review And Debug UI

- Show creative request, raw response, scene plan, repaired scene plan, final
  build spec, and warnings on the review page.
- Make omitted/repaired objects visible to the creative team.

### Phase 6: Production Hardening

- Add regression prompts for repeated production cases.
- Add validation warnings when named objects are missing.
- Add escalation path for repeated repair failure.
- Promote successful category and relationship rules into documented harness
  behavior.

## Success Criteria

- A creative user can ask for arbitrary simple sets, props, or locations without
  copying system directives.
- Every named object in the request is represented in the scene plan or flagged.
- Quantities and size hints survive into the build.
- Relationships like "facing the TV" and "mounted on rear wall" affect layout.
- The primitive render is crude but visibly specific to the request.
- The review page explains what the local LLM produced, what was repaired, and
  what was built.

## Immediate Next Build Task

Implement Phase 1 and Phase 2 behind the existing CLI:

```text
tools/studio_chat.py
  creative request
  -> scene plan LLM call
  -> parsed scene plan
  -> compatibility PrimitiveBuildSpec
  -> existing /api/v1/conversations/jobs endpoint
```

Do not remove the current component-list path. The new scene-plan path should
be additive until it has proven reliable across real prompts.
