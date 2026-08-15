---
title: Conversational Scene Schema
created: 2026-08-15T00:00:00-04:00
updated: 2026-08-15T00:00:00-04:00
doc_type: spec
production_area: pipeline
department: pipeline
status: active
canonical: true
canonical_for: conversational_scene_schema
wiki: true
wiki_group: Design
wiki_page: Conversational-Scene-Schema
wiki_order: 25
---
# Conversational scene schema

The intermediate, LLM-facing schema layer that sits between a creative prompt
and the canonical production schema in `docs/SCHEMA.md`. It is the shape the
local LLM produces and repairs before a deterministic builder compiles it into
primitives, and before (where applicable) it is promoted toward a full
`SceneSpec`.

This spec was consolidated 2026-08-15 from duplicated schema sections
previously split across `docs/planning/SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md`
("Scene Plan Schema", "Detail And Modifier Pass-Through", "Core Object
Categories", "Relationship Vocabulary") and
`docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md` ("Detail Preservation Contract",
which carried a near-identical example). Both docs now point here instead of
re-defining the shape. `docs/SCHEMA.md` covers the canonical production
schema this layer feeds into; `SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md` covers
the surrounding architecture (semantic asset graph, operation contract,
rollout plan); `STUDIO-CHAT-ENDPOINT-PLAN.md` covers the HTTP endpoint that
produces and repairs this data.

## Scene Plan Schema

A richer intermediate schema than a raw primitive build spec.

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

Fields on scene-plan objects:

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

## Detail Preservation Contract (endpoint usage)

The studio-chat endpoint (`docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md`) prompts
and repairs the local LLM against this schema so meaningful creative details
pass through into structured fields. For example, "build a dining room table
with rounded corners" should produce an object with fields such as:

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
