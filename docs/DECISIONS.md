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
| v1 lipsync (2026-07-07) | None for now — dialogue is timing/markers only; viseme fields are a later minor-version schema bump |
| Producer role (2026-07-07) | The local LLM ("the producer") drives the toolchain with provided assets only and tickets the crew (per-episode files); it never commands agents; all runs human-initiated during development — docs/planning/PRODUCER-PLAN.md |
| Profile authoring post-author-tier (2026-07-07) | Human + reviewer-tier co-authoring against `.claude/agents/_TEMPLATE.md` and AGENT-WORKFLOW-PLAN §4 rules; qualification bar (§7) unchanged |
| Model names in agent frontmatter (2026-07-11) | Accepted exception to the tier-names-only rule: the `model:` field in `.claude/agents/*.md` is functional Claude Code configuration (agents select their model through it) and stays in the public repo. Prose still uses tier names only; assignments/pricing detail remains in `docs/local/MODEL-TIERS.md` |

## Framing context (from handoff)

- Prefer a practical, buildable path over speculative AI hype.
- Explicitly avoiding generative video.
- Strongest product framing: an AI scene compiler front end.
- First useful target: a narrow working demo, not a broad platform.
