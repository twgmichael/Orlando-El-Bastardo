# Scene Graph Primitive Builder Plan

Recorded 2026-07-15. Status: **PLANNED**.

## Goal

Turn flexible creative language from tele-play or conversation into immediate
primitive 3D blocking passes for sets, locations, props, and simple assets.

The primitive builder is a storyboard and layout department, not a final asset
generator. It should quickly preserve creative intent, make spatial decisions
visible, and produce reviewable renders while final assets are sourced, built,
or replaced from modular kits.

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
  -> primitive build spec
  -> harness job
  -> Blender primitive render
  -> review page
```

The creative user should only provide the creative request. Prompt directives,
schema rules, validation, repair, logging, and job submission belong inside the
harness.

## Scene Plan Schema

Add a richer intermediate schema before the current primitive build spec.

This is the current home for the conversational asset-detail schema discussion.
Cross-reference: `docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md` covers where the
local LLM produces and repairs this data, and `docs/SCHEMA.md` covers the
broader canonical production schemas. These should eventually be consolidated
so we do not maintain competing schema narratives.

Example:

```json
{
  "scene_type": "living_room",
  "style": "modern minimalist",
  "objects": [
    {
      "id": "reclining_chair",
      "label": "reclining chair",
      "category": "seating",
      "count": 1,
      "size": "medium",
      "placement": "center",
      "shape": {
        "primary_form": "armchair",
        "corner_style": "soft",
        "edge_profile": "rounded"
      },
      "required_features": ["reclining_back"],
      "source_phrases": ["reclining chair"],
      "orientation": {
        "faces": "television"
      }
    },
    {
      "id": "television",
      "label": "television",
      "category": "screen",
      "count": 1,
      "size": "large",
      "placement": "rear_wall",
      "mounting": "wall"
    },
    {
      "id": "floor_lamp",
      "label": "floor lamp",
      "category": "lighting",
      "count": 1,
      "placement": "left_of_reclining_chair"
    }
  ],
  "relationships": [
    {
      "subject": "reclining_chair",
      "relation": "faces",
      "target": "television"
    },
    {
      "subject": "television",
      "relation": "mounted_on",
      "target": "rear_wall"
    },
    {
      "subject": "floor_lamp",
      "relation": "left_of",
      "target": "reclining_chair"
    }
  ]
}
```

## Detail And Modifier Pass-Through

Creative modifiers must survive as structured data, not only as words embedded
in labels. A prompt such as "build a dining room table with rounded corners"
should not rely on `label: "dining_table_rounded_corners"` as the only carrier
of the rounded-corner requirement.

Add these fields to scene-plan objects:

- `shape`: structured geometry intent such as `primary_form`, `corner_style`,
  `edge_profile`, `profile`, `silhouette`, and simple proportion notes.
- `required_features`: snake_case feature requirements that must be preserved
  through repair and passed to the builder.
- `source_phrases`: exact or near-exact prompt phrases that justify an object,
  shape, material, count, placement, or relationship.
- `materials`: material and finish hints when the prompt provides them.
- `style_details`: visual style modifiers that affect the object but are not
  core geometry.

Example:

```json
{
  "id": "dining_table",
  "label": "dining room table",
  "category": "surface",
  "count": 1,
  "size": "medium",
  "placement": "center",
  "mounting": "self",
  "shape": {
    "primary_form": "rectangular_table",
    "corner_style": "rounded",
    "edge_profile": "soft_beveled",
    "top_thickness": "medium"
  },
  "required_features": ["rounded_corners"],
  "source_phrases": ["dining room table", "rounded corners"],
  "parts": [
    {
      "id": "tabletop",
      "category": "surface",
      "shape": {
        "corner_style": "rounded"
      }
    },
    {
      "id": "legs",
      "category": "support",
      "count": 4
    }
  ]
}
```

Repair rule: every meaningful adjective or modifier in the creative prompt must
appear in a structured field, preferably `shape`, `required_features`,
`materials`, `style_details`, or `source_phrases`. If the prompt contains
"rounded corners" and no object has `shape.corner_style: "rounded"` or
`required_features: ["rounded_corners"]`, the plan should be considered
incomplete and repaired before job creation.

## Core Object Categories

The local LLM should classify arbitrary nouns into reusable production
categories. The primitive builder should render categories, not one-off scene
names.

Initial categories:

- `seating`: chair, couch, sofa, bench, stool, recliner
- `surface`: desk, table, counter, altar, workbench
- `storage`: cabinet, dresser, shelf, locker, crate
- `screen`: television, monitor, computer, terminal, display
- `lighting`: lamp, lantern, sconce, overhead light
- `bed`: bed, cot, bunk, examination table, gurney
- `medical`: medical device, scanner, monitor, examination equipment
- `plant`: tree, plant, bush
- `path`: road, path, walkway, corridor
- `wall_item`: window, door, sign, panel, mirror
- `machine`: console, reactor, kiosk, vending machine
- `structure`: wall, platform, stage, booth, stall
- `unknown`: fallback block with label-preserving object name

The category set should grow slowly as repeated production needs appear.

## Relationship Vocabulary

Start with a small deterministic relationship vocabulary:

- `faces`
- `left_of`
- `right_of`
- `behind`
- `in_front_of`
- `near`
- `on_top_of`
- `mounted_on`
- `inside`
- `around`
- `aligned_with`

The local LLM should extract relationships explicitly. Component names may keep
spatial hints for backward compatibility, but relationship records should be
the durable representation.

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
