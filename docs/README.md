# Orlando El Bastardo — Documentation

3D animation orchestration pipeline. Human-authored content is compiled into
validated scene specifications and exporter-ready files for Blender, Godot, and
USD workflows. A local LLM translates approved source content into structured
pipeline data — it does not generate pixels, fabricate imagery, or write story.

## Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — stack, processing pipeline, key principles
- [SCHEMA.md](SCHEMA.md) — canonical objects, SceneSpec/ShotSpec/cue design, intent boundary
- [RESOURCES.md](RESOURCES.md) — software, hardware, asset sources, licensing policy
- [BAR-SCENE.md](BAR-SCENE.md) — first integration target: assets, marks, animations, cameras
- [DECISIONS.md](DECISIONS.md) — locked decisions from the research phase
- [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) — unresolved design questions

## Non-goals

- No generative video
- No pixel manipulation to hallucinate scenes
- LLM is not the primary writer of story content
- LLM does not author final production files without validation
