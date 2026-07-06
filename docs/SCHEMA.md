# Schema design

> **Implemented 2026-07-04** (JSON Schema draft 2020-12, all v1.0.0):
> `schemas/scenespec.schema.json` (SceneSpec + ShotSpec, the six-cue
> discriminated union, ActorSpec/SetSpec/PropSpec/RenderSpec/ExportSpec, and
> `target_bindings` as `$defs`), `schemas/sceneintent.schema.json`,
> `schemas/validationreport.schema.json`, `schemas/camera-grammar.schema.json`
> (data: `data/camera_grammar.json`), `schemas/oeb-config.schema.json`
> (instance: `oeb.config.json` — `OEB_ASSET_ROOT` env var overrides its
> `asset_root`). Reference fixtures: `fixtures/bar_scene.scenespec.json` and
> `fixtures/bar_scene.sceneintent.json`, both schema-validated.
> Conventions: all times in seconds; cue `start_time` is relative to its
> shot's `start_time`; `DialogueCue.duration` is required (explicit-timing
> decision); logical IDs match `^[a-z][a-zA-Z0-9_]*$` and are never paths.
> SceneIntent `shot_intents[].beat_orders` is REQUIRED (2026-07-06, Phase 5
> integration fix: an uncovered shot resolves empty and silently drops its
> beats' dialogue; requiring it also forces grammar-constrained LLM decoding
> to emit it).

## Canonical objects

`ProjectSpec`, `EpisodeSpec`, `SceneSpec`, `ShotSpec`, `ActorSpec`, `SetSpec`,
`PropSpec`, `DialogueCue`, `AnimationCue`, `CameraCue`, `LightingCue`, `AudioCue`,
`FXCue`, `RenderSpec`, `ExportSpec`, `ValidationReport`.

## SceneSpec — required fields

`schema_version`, `scene_id`, `units`, `set`, `actors`, `shots`, `render`.

## ShotSpec — required fields

`shot_id`, `order`, `start_time`, `end_time`, `camera_setup`, `cues`.

## Cue types

`animation`, `dialogue`, `camera`, `lighting`, `audio`, `fx` — modeled as a
discriminated union keyed on a `type` field.

## Design rules

- Separate logical IDs from target-specific bindings.
- Keep intent separate from resolved assets when possible.
- Prefer discriminated unions for cue types using a `type` field.
- Validate before export.
- Use a canonical schema with exporter-specific target adapters.

## Logical identity vs target bindings

```json
{
  "logical_identity": {
    "actor_id": "mom",
    "character_id": "char_mom_v4"
  },
  "target_bindings": {
    "usd_path": "/Chars/Mom",
    "godot_node": "Actors/Mom",
    "blender_object": "CHR_Mom"
  }
}
```

## SceneIntent (the LLM output boundary)

Fields: `scene_id`, `location_tag`, `time_of_day`, `actors`, `beats`,
`shot_intents`.

The resolver converts `SceneIntent` into a `SceneSpec` by mapping intent to
approved assets.

## Validation

Minimum checks:

- All referenced actor IDs exist
- All clip IDs exist in the animation library
- All camera IDs are valid
- Cue times fit within scene/shot bounds
- Set marks and spawn points exist
- Audio assets exist
- No duplicate IDs
- Exporter bindings resolve cleanly

Common warnings: dialogue likely too long for shot, unknown animation clip,
missing prop asset, unsupported camera grammar.
