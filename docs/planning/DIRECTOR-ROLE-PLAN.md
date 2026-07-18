---
title: Director Role Plan
created: 2026-07-17T00:00:00-04:00
updated: 2026-07-17T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: production
status: active
canonical: true
canonical_for: director_role
wiki: true
wiki_group: Planning
wiki_page: Director-Role-Plan
wiki_order: 24
---
# Director Role Plan

Recorded 2026-07-17 from review of `oeb-text-adventures.md` and follow-up
discussion about the distinction between producer and director responsibilities
inside `oeb-studio-harness`.

## Discovery

The reviewed note described an "AI Director" that would translate teleplay
content into assembled 3D scenes by loading environments and props, placing
characters, assigning motion, framing cameras, applying lighting, maintaining
continuity, and producing editable scenes for final rendering.

That surfaced an important naming and architecture risk in the current project:
the existing "producer" language already covers script-to-render orchestration,
but it does not fully cover creative staging. Treating the producer as both
logistics manager and director would blur two different responsibilities.

The project already has a strong producer pipeline:

- deterministic screenplay parsing;
- local LLM translation under schema constraints;
- resolver and validator gates;
- asset-library enforcement;
- NEEDED tickets for missing locations, props, clips, and capabilities;
- Blender/Godot/USD export targets;
- render QA and episode assembly.

The missing layer is a distinct, constrained director role: a system that turns
scene facts into intentional shot design, blocking, pacing, performance intent,
and continuity before resolution and export.

## Research From Current Project State

The current architecture says the LLM may act as translator, constraint engine,
scene fitting assistant, format conversion layer, or structured extraction
layer. It explicitly rejects the LLM as story author, freeform director, frame
generator, or unvalidated final-file author.

The producer plan says the producer oversees script-to-render production using
only the provided asset library. If a script names anything outside the library,
the producer halts that scene and emits a structured NEEDED report. The producer
does not improvise, substitute, or build missing capabilities.

The studio harness vision says the harness owns workflow, memory, validation,
and orchestration, while models are replaceable specialists. That supports a
director model as a bounded specialist, not as a privileged authority over the
pipeline.

The scene-graph primitive builder plan already points in the same direction for
conversation-driven layout: flexible creative language needs a semantic
intermediate plan, and natural-language relationships like `faces`,
`left_of`, `behind`, and `mounted_on` must survive as structured build
instructions.

## Role Definitions

### Producer

The producer is the logistics and orchestration layer.

The producer answers: "Can this script or request be produced with the current
studio resources, and what jobs must run?"

Producer responsibilities:

- accept a script, scene, or creative request as input;
- split work into scenes or jobs;
- invoke translator, director, resolver, validator, exporter, renderer, and QA
  steps in order;
- consult the asset registry, resolver map, camera grammar, clip library, and
  harness capability registry;
- classify failures as bugs, missing assets, missing vocabulary, or missing
  capabilities;
- emit structured NEEDED tickets when production cannot proceed honestly;
- assemble production reports, artifacts, and episode outputs;
- keep the run deterministic, auditable, and bounded.

The producer must not rewrite the story, silently substitute available assets,
invent props, author shots for taste, bypass validation, or hide gaps.

### Director

The director is the creative staging layer.

The director answers: "Given this scene, how should it play on screen?"

Director responsibilities:

- convert scene facts into a shot plan;
- choose shot purposes such as establishing, reveal, reaction, insert,
  over-shoulder, close-up, medium, or tracking shot;
- define blocking: actor start positions, entrances, exits, movement, facing,
  spacing, following, turning, sitting, standing, and prop interaction;
- define pacing: beat timing, holds, pauses, reaction windows, and emphasis;
- preserve continuity: actor positions across shots, screen direction, eyelines,
  prop state, and entry/exit state;
- express performance intent in broad, mappable terms such as tense, casual,
  hurried, suspicious, comic, restrained, or confrontational;
- choose from approved camera grammar and lighting presets where available;
- produce structured, reviewable direction before final `SceneSpec` resolution.

The director must not create new story events, rewrite dialogue, substitute
unavailable locations or characters, directly author Blender/Godot/USD files,
or decide that missing requirements are acceptable. If direction requires a
camera setup, animation, lighting preset, prop, or set mark that does not exist,
the director should express that requirement structurally so the producer and
resolver can report it.

## Proposed Pipeline Position

Current simplified shape:

```text
script
  -> scene intent / structured extraction
  -> resolver
  -> validator
  -> exporter
  -> render
```

Recommended shape:

```text
script scene
  -> factual scene extraction
  -> DirectorPlan
  -> resolver
  -> validator
  -> exporter
  -> render
```

In this shape:

- `SceneIntent` records what the script says happened.
- `DirectorPlan` records how the scene should be staged, shot, paced, and kept
  continuous.
- `SceneSpec` records the resolved, validated production instructions.
- The producer orchestrates the movement between those artifacts.

## DirectorPlan Sketch

`DirectorPlan` should be a constrained intermediate artifact, not a replacement
for `SceneIntent` or `SceneSpec`.

Example shape:

```json
{
  "scene_id": "engineering_engines_online",
  "dramatic_intent": "urgent command",
  "shots": [
    {
      "shot_id": "wide_entry",
      "purpose": "establish location and movement",
      "camera_intent": "wide_establishing",
      "beats": [
        {
          "actor": "captain",
          "action": "enter",
          "from": "door",
          "to": "console",
          "timing": "0-4s"
        },
        {
          "actor": "engineer",
          "action": "follow",
          "from": "door",
          "to": "behind_captain",
          "timing": "1-5s"
        }
      ]
    },
    {
      "shot_id": "captain_closeup",
      "purpose": "emphasize order",
      "camera_intent": "closeup_front",
      "continuity_from": "wide_entry",
      "beats": [
        {
          "actor": "captain",
          "action": "speak",
          "dialogue": "Bring the engines online.",
          "timing": "5-7s"
        }
      ]
    }
  ],
  "continuity": {
    "captain_position_after_scene": "console",
    "engineer_position_after_scene": "behind_captain",
    "screen_direction": "captain_moves_left_to_right"
  }
}
```

Open schema work:

- decide whether `DirectorPlan` is a new schema or a named section within the
  planned schema consolidation;
- define a small camera-intent vocabulary that maps cleanly to
  `data/camera_grammar.json`;
- define a small blocking vocabulary that maps cleanly to marks, movement cues,
  animation clips, and scene relationships;
- define continuity fields that are cheap enough to validate in early versions;
- define how missing direction requirements become NEEDED tickets.

## Recommendations

1. Add a distinct `DirectorPlan` layer between factual scene extraction and
   resolver/export.
2. Keep the director constrained to structured direction, not direct file
   authoring or asset invention.
3. Preserve the producer as the logistics owner: job dispatch, feasibility,
   failure classification, reports, and tickets.
4. Make the director output human-reviewable before render. This gives the
   project an explicit place to revise staging without touching exporter code.
5. Treat the initial director as a small vocabulary system: shot purpose,
   blocking, pacing, continuity, performance intent, camera intent, and lighting
   mood.
6. Reuse existing project rails: schema validation, resolver mapping, approved
   asset IDs, camera grammar, clip libraries, and NEEDED ticket behavior.
7. Avoid adding generative video or unconstrained animation systems to the core
   path. External motion or facial-animation tools may later feed the asset and
   clip library, but they should not bypass the producer/resolver/validator
   chain.

## Decisions

- The producer and director are distinct roles.
- The producer owns orchestration, feasibility, reporting, and tickets.
- The director owns shot design, blocking, pacing, performance intent, and
  continuity.
- The director is constrained and schema-bound; it is not a freeform AI
  filmmaker.
- The director must not invent unavailable assets, rewrite story facts, or
  directly author target files.
- Missing director requirements should become structured requirements that the
  producer/resolver can surface as NEEDED work.
- The recommended architecture is:

```text
script scene
  -> factual scene extraction
  -> DirectorPlan
  -> resolved SceneSpec
  -> validation
  -> export/render/QA
  -> production report
```

## Near-Term Work

- Add `DirectorPlan` to the schema consolidation discussion alongside
  `SceneIntent`, conversational scene plans, primitive build specs, and
  `SceneSpec`.
- Draft a minimal `directorplan.schema.json` with conservative vocabularies.
- Create one fixture from the pilot or bar scene showing factual extraction,
  director plan, and resolved scene spec side by side.
- Decide where the director step runs in `tools/producer.py` once the schema is
  real.
- Add a qualification drill: one in-library scene should produce useful staged
  direction; one scene needing an unavailable camera, mark, or clip should
  produce a clean NEEDED path rather than a hidden substitution.
