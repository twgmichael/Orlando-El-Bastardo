---
title: Local Asset Builder Support Notes
created: 2026-07-21T13:45:07-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: reference
production_area: assets
department: art
status: archived
canonical: false
wiki: false
wiki_group: Operations
---
# Local Asset Builder Support Notes

Date: 2026-07-21

Status: **RECORDED**

## Context

Recent archive salvage work recovered and organized several OEB ship assets:
`rough-Ellipso-mark-s1`, corrected `rough-ventradi-cruiser`, and rebuilt
`rough-bugblatter-cruiser`.

The Bugblatter pass was especially instructive. The original recovered file
mostly contained ball-turret, cannon spline, and profile geometry rather than a
complete cruiser hull. The working asset was therefore rebuilt as a primitive
landing cruiser using the recovered turret data and reference screenshots:
terrain-camouflaged hull, small distributed turrets, four gray landing-pad
tubes, and standard angle/action renders.

That result confirmed that future OEB asset work should shift away from
one-off salvage as the default. Salvage remains useful for recovered parts and
visual references, but the repeatable workflow should be:

```text
describe model -> build primitive asset -> render review views -> request changes
```

This matches OEB's crude retro production style, current hardware, and the
need for fast reviewable iteration.

## Discovery

The current docs and harness already contain most of the boundaries needed for
a local asset-builder role:

- `docs/DECISIONS.md` defines the local LLM as a translator from approved
  content into structured pipeline formats, not a freeform production artist.
- `docs/DECISIONS.md` also locks in a deterministic Blender/Godot/local-LLM
  toolchain and describes the local LLM as a toolchain producer.
- `docs/planning/CONVERSATION-TO-BUILD-LOOP.md` assigns the local LLM strict
  JSON output, small buildable jobs, clarification, and escalation when unsafe.
- `docs/planning/CONVERSATION-TO-BUILD-LOOP.md` assigns workers deterministic
  duties: build from spec, use Blender primitives, export GLB, render preview
  images, register artifacts, and update job status.
- `docs/planning/SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md` defines the target
  pipeline from creative request through local LLM scene-plan extraction,
  validation, primitive build spec, harness job, Blender render, and review
  page.
- `docs/planning/ASSET-LOCATION-ORIENTATION-STANDARD.md` defines the shared
  asset-local direction contract: `+X` front, `-X` rear, `-Y` left, `+Y`
  right, `+Z` up, and `-Z` down.

The implementation also has relevant existing surfaces:

- `server/app/schemas/conversation.py` already has `SceneObject`,
  `ScenePlan`, and `PrimitiveBuildSpec`.
- `worker/agent/adapters/ollama.py` already advertises `llm.scene_spec` and
  `llm.blender_python`.
- `worker/agent/adapters/blender.py` already defines Blender capabilities and
  standard asset review views.
- `server/app/services/asset_review.py` and `server/app/routers/jobs.py`
  already expose canonical asset review render job creation.
- `server/app/routers/artifacts.py` and `worker/agent/job_runner.py` already
  upload artifacts with provenance and review metadata.

The missing piece is not a broad architectural decision. It is a constrained
asset-builder and asset-edit contract that sits beside the current scene-plan
and primitive-build schemas.

## Local Hardware Research

The local Mac mini has Ollama, llama.cpp, an M4 with 32 GB memory, and
`oeb-qwen2.5-3b`. This should be useful for simple structured edits,
classification, schema filling, and constrained transformations, but it is too
small to be treated as the primary creative asset builder.

`render-pc-01` has 64 GB RAM and 6 GB VRAM. It should be useful for Blender
and render jobs, and may be practical for some 7B or 14B local model work. It
should not be planned around 32B-class local models.

Vision judgment and ambiguous art direction should remain frontier-model work.
Local models should do bounded translation and routine production formatting.

## Discussion

The local asset-builder role should be named and constrained. It should not
invent arbitrary production assets, bypass the artifact system, or become a
general freeform Blender author.

It should instead translate human-approved creative requests into small,
reviewable primitive jobs such as:

- Build a new primitive ship, prop, set piece, or blocking asset from named
  parts.
- Apply a constrained edit to a named part or material.
- Produce a review render request after a GLB is exported.
- Escalate when the request depends on ambiguous art direction, missing
  reference material, or unavailable assets.

Named primitive builders are the right shape for the first implementation.
Examples include ship, furniture, simple prop, terrain piece, and room/set
builders. Each builder should own a limited vocabulary of parts, placement
rules, proportions, materials, and defaults. The local LLM can select and fill
one of these builders, but the deterministic worker should execute the builder.

Asset edits need their own schema because conversational changes such as
`move the hull back 10%`, `make the turrets smaller`, or `add four landing-pad
tubes` are different from a first-build request. The orientation standard makes
these edits tractable as structured deltas instead of prompt-only instructions.

Review generation should remain a first-class harness concern. Asset-builder
jobs should produce or register GLB artifacts, then route review render jobs
through the existing standard views: top, bottom, left, right, front, back, and
action.

## Recommendations

Add a constrained asset-builder support layer in small increments:

1. Add schema models for asset-builder requests and asset-edit requests beside
   the existing conversation schemas.
2. Include named target parts, edit operations, relative directions, scalar
   amounts, material changes, requested builder type, and escalation reasons.
3. Validate edit requests against the OEB orientation standard and known part
   names before any Blender work is queued.
4. Route accepted build specs to deterministic named primitive builders rather
   than asking a local model to generate unconstrained Blender code.
5. Keep `llm.blender_python` available for bounded helper generation only, not
   as the default production path.
6. Register generated GLB files as normal artifacts with provenance and review
   metadata.
7. Automatically create or suggest asset-review render jobs after successful
   asset export.
8. Escalate to a frontier model only for ambiguous art direction, visual
   judgment, reference interpretation, or cases where local validation cannot
   safely choose.

## Decisions

No additional user questions are needed before the next design or
implementation pass.

The next work should proceed under these decisions:

- The local LLM asset-builder role is a structured production translator, not
  a freeform artist.
- Primitive asset generation should use named deterministic builders.
- Asset edits should use a constrained schema rather than freeform prose.
- The OEB orientation standard is sufficient for directional edit semantics.
- Blender workers should remain responsible for export and render execution.
- Existing artifact upload, provenance, and review metadata paths should be
  reused.
- Review views should remain canonical and multi-angle for standalone assets.
- Frontier models should be reserved for ambiguous art direction and image
  judgment.

## Open Implementation Notes

The highest-value next implementation target is a schema and route design for:

```text
creative request
  -> local LLM asset-build or asset-edit request
  -> validation and repair
  -> named primitive builder job
  -> GLB export
  -> artifact registration
  -> asset-review render job
  -> review page
```

The expected first schema addition is a constrained asset edit request with
fields for target asset, target part, operation, axis or semantic direction,
amount, units, material delta, requested review views, and escalation metadata.

The expected first builder addition is a named primitive ship builder because
the recent OEB ship work provides clear test cases: Ellipso, Ventradi,
Bugblatter, and other rough retro fleet assets.
