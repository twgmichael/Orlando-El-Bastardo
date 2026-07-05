# Architecture

## High-level stack

| Component | Role |
|---|---|
| Blender | Primary DCC: asset authoring, rigging, layout, animation polish, offline render |
| Godot | Realtime scene playback, previs, runtime staging, machinima control layer |
| OpenUSD | Scene composition, durable interchange, shot assembly, future-proof layer |
| glTF | Practical runtime delivery format for assets where appropriate |
| Local LLM (llama.cpp or equivalent) | Translate script content into structured scene intent or partially resolved scene spec |
| Validator + resolver | Map intent to approved assets, reject impossible references, emit deterministic outputs |

## Processing pipeline

1. Human-authored source content
2. LLM produces `SceneIntent` or a constrained structured scene draft
3. Resolver maps intent to approved assets and libraries
4. Validator checks IDs, timing, assets, and compatibility
5. Exporters emit Blender, Godot, and USD outputs
6. Human reviews and adjusts

## Key principles

- One canonical internal format, then deterministic exporters per target.
- Do not let target-specific requirements leak into authoring.
- Keep intent separate from resolved assets where possible.
- Validate every scene before export.

## LLM role

Approved: translator, constraint engine, scene fitting assistant, format conversion
layer, structured extraction layer.

Rejected: story author, freeform director, frame generator, unvalidated final file
author.

The LLM should usually output `SceneIntent` or a partially resolved `SceneSpec`,
not direct Blender/Godot/USD files. This is safer, lets a deterministic resolver
enforce approved assets, keeps the LLM constrained, and improves reproducibility.

## Export targets

- **Blender** — scene name, linked collections/assets, cameras, timeline markers, action assignments by frame, audio strips/speaker objects, render settings. Best for asset authoring, rigging, shot polish, animation editing, final offline renders.
- **Godot** — `.tscn` scene, actor nodes, set instance, camera rig nodes, `SceneDirector.gd` controller, event timeline resource. Best for realtime previs, interactive playback, branching narrative, fast iteration.
- **USD** — root layer, set/character/prop references, camera prims, timeline sidecar JSON for cue timing. Best for interchange, shot composition, multi-tool compatibility, future-proofing.
