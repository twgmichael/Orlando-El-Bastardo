---
title: Home
created: 2026-07-13T19:47:43-04:00
updated: 2026-07-16T19:16:39-04:00
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

Orlando El Bastardo is a deterministic 3D animation studio pipeline with a
working conversational build loop: creative prompt, structured scene plan,
validated job, worker render, visible review artifact, and traceable production
output. Human-authored story remains the source. Local LLMs translate intent
into constrained pipeline data; they do not generate pixels, fabricate imagery,
or write final production files without validation.

## Documentation Map

This Home page lists current, active public documentation. Historical,
superseded, and cleanup-target documents may remain in the repository, but they
are not front-door reading unless they still serve the active production state.

## Core References

- [ARCHITECTURE.md](ARCHITECTURE.md) — stack, processing pipeline, and key principles
- [SCHEMA.md](SCHEMA.md) — production schema, conversational scene-plan layers, and intent boundary
- [BAR-SCENE.md](BAR-SCENE.md) — first integration target: assets, marks, animations, cameras
- [RIGGING.md](RIGGING.md) — character skeleton, animation naming, and retargeting standard
- [PROVENANCE.md](PROVENANCE.md) — asset sources, licensing, and ownership register
- [RESOURCES.md](RESOURCES.md) — software, hardware, asset sources, and licensing policy
- [SECURITY.md](SECURITY.md) — privacy, ignored outputs, and public-repo safety posture
- [DECISIONS.md](DECISIONS.md) — locked project decisions

## Active Standards And Plans

- [planning/ASSET-LOCATION-ORIENTATION-STANDARD.md](planning/ASSET-LOCATION-ORIENTATION-STANDARD.md) — OEB local axis standard for assets and locations
- [planning/DOCUMENTATION-TAXONOMY-AND-METADATA.md](planning/DOCUMENTATION-TAXONOMY-AND-METADATA.md) — front matter taxonomy, lifecycle states, and wiki routing metadata
- [planning/WIKI-SYNC-PLAN.md](planning/WIKI-SYNC-PLAN.md) — generated wiki publishing flow and lifecycle pruning rules
- [planning/STUDIO-CHAT-ENDPOINT-PLAN.md](planning/STUDIO-CHAT-ENDPOINT-PLAN.md) — environment-neutral conversational prompt-to-job endpoint plan
- [planning/SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md](planning/SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md) — structured scene-plan and primitive-builder contract
- [planning/ASSET-REGISTRY-PLAN.md](planning/ASSET-REGISTRY-PLAN.md) — lean registry for conversation grounding and pipeline lookup
- [planning/CONVERSATION-TO-BUILD-LOOP.md](planning/CONVERSATION-TO-BUILD-LOOP.md) — prompt-to-render loop verified across local/staging configuration
- [planning/STUDIO-HARNESS-VISION.md](planning/STUDIO-HARNESS-VISION.md) — studio harness product and operations vision
- [planning/HARNESS-RENDER-QUALITY-LANGUAGE.md](planning/HARNESS-RENDER-QUALITY-LANGUAGE.md) — canonical draft/preview/final render quality language
- [planning/WORKER-AGENT-PLAN.md](planning/WORKER-AGENT-PLAN.md) — worker agent architecture, environment selection, and remaining install work
- [planning/AGENT-BUS-PLAN.md](planning/AGENT-BUS-PLAN.md) — planned production issue bus
- [planning/PUBLISHING-PLAN.md](planning/PUBLISHING-PLAN.md) — public publishing and render upload flow

## Tracking

- [../PROJECT-TODO.md](../PROJECT-TODO.md) — active roadmap and current priorities
- [../PROJECT-DONE.md](../PROJECT-DONE.md) — completed work and evidence ledger

## World-building

- [world-building/SPACESCAPE.md](world-building/SPACESCAPE.md) — deep-space environment: starfield, sun, planet; discovery, options, decision, implementation spec
- [world-building/FLIGHT-ANIMATION.md](world-building/FLIGHT-ANIMATION.md) — flight animation patterns: hero-in-rolling-ship tracking, two-phase choreography, sweep-hold-track camera
- [vehicles/JOURNEYBLASTER.md](vehicles/JOURNEYBLASTER.md) — JB100 / JB5K ship design record

## Publishing Rules

Public wiki publishing is controlled by front matter in each markdown file:
`wiki: true`, `wiki_group`, `wiki_page`, and `wiki_order`. Lifecycle status is
part of routing: `active`, `archived`, and `superseded` pages can publish when
explicitly routed; `remove_next_cleanup` is a tombstone and is pruned from the
wiki on sync. `docs/local/**` remains local-only and is always excluded.

## Non-goals

- No generative video
- No pixel manipulation to hallucinate scenes
- LLM is not the primary writer of story content
- LLM does not author final production files without validation
