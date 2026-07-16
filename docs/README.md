---
title: Home
created: 2026-07-13T19:47:43-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: reference
production_area: documentation
department: production
status: active
canonical: true
canonical_for: documentation_index
wiki: true
wiki_group: Home
wiki_page: Home
wiki_order: 0
---
# Orlando El Bastardo — Documentation

3D animation orchestration pipeline. Human-authored content is compiled into
validated scene specifications and exporter-ready files for Blender, Godot, and
USD workflows. A local LLM translates approved source content into structured
pipeline data — it does not generate pixels, fabricate imagery, or write story.

## Documents

Public wiki publishing is controlled by front matter in each markdown file:
`wiki: true`, `wiki_group`, `wiki_page`, and `wiki_order`. `docs/local/**`
remains local-only and is always excluded from the wiki sync.

- [ARCHITECTURE.md](ARCHITECTURE.md) — stack, processing pipeline, key principles
- [SCHEMA.md](SCHEMA.md) — canonical objects, SceneSpec/ShotSpec/cue design, intent boundary
- [RESOURCES.md](RESOURCES.md) — software, hardware, asset sources, licensing policy
- [BAR-SCENE.md](BAR-SCENE.md) — first integration target: assets, marks, animations, cameras
- [DECISIONS.md](DECISIONS.md) — locked decisions from the research phase
- [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) — unresolved design questions
- [vehicles/JOURNEYBLASTER.md](vehicles/JOURNEYBLASTER.md) — JB100 / JB5K ship design record

## World-building

- [world-building/SPACESCAPE.md](world-building/SPACESCAPE.md) — deep-space environment: starfield, sun, planet; discovery, options, decision, implementation spec
- [world-building/FLIGHT-ANIMATION.md](world-building/FLIGHT-ANIMATION.md) — flight animation patterns: hero-in-rolling-ship tracking, two-phase choreography, sweep-hold-track camera

## Non-goals

- No generative video
- No pixel manipulation to hallucinate scenes
- LLM is not the primary writer of story content
- LLM does not author final production files without validation
