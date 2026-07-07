# Decisions (locked in research phase, 2026-07-03)

| Decision | Result |
|---|---|
| LLM role | Translator for approved content into structured pipeline formats, not content writer |
| Pipeline philosophy | Deterministic asset/rig-based 3D pipeline, not generative video |
| Core tools | Blender + Godot + local LLM + optional USD layer |
| Canonical data strategy | SceneSpec / ShotSpec / cue-based schema with exporters |
| First milestone scene | Hero in a bar chatting with a bartender |
| Primary machine | Apple-silicon workstation (specifics in `docs/local/MACHINE-NOTES.md`, local only) |
| Asset sourcing defaults | Favor CC0-friendly sources first |
| v0 staging (2026-07-04) | Seated-only: hero starts seated at `hero_barstool_A`; no locomotion in v0 |
| Dialogue timing (2026-07-04) | Explicitly authored: `DialogueCue.duration` is schema-required |
| Camera grammar storage (2026-07-04) | JSON data (`data/camera_grammar.json` + schema); code interprets, data defines |
| LLM output boundary (2026-07-04) | SceneIntent only — LLM never emits asset/clip IDs; resolver maps to approved assets |
| Skeleton & retargeting standard (2026-07-06) | `oeb_humanoid_v1` = UE-mannequin naming as shipped by Quaternius UBC/UAL (65 joints, T-pose, in-place clips, bone maps as data) — full spec in docs/RIGGING.md |

## Framing context (from handoff)

- Prefer a practical, buildable path over speculative AI hype.
- Explicitly avoiding generative video.
- Strongest product framing: an AI scene compiler front end.
- First useful target: a narrow working demo, not a broad platform.
