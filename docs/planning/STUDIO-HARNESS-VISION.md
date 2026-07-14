# Studio Production Pipeline Harness — Vision and Architecture

Recorded 2026-07-13. Source: `studio-production-harness-project-summary.json`.

## Purpose

A conversational production system that transforms scripts and creative discussion
into structured production assets, scenes, episodes, and render jobs using
interchangeable local and remote workers.

## Vision

**Goal:** Build a reusable studio operating system, not a chatbot.

**Core principle:** The harness owns workflow, memory, validation, and
orchestration. Models are replaceable specialists.

## Thesis

**Problem:**
- Frontier LLMs are expensive for routine production tasks.
- Creative intent should survive model changes.
- Artists should work conversationally instead of manipulating low-level files.

**Solution:**
- Translate conversation into structured schemas.
- Route work to the cheapest competent worker.
- Execute deterministic tools after validation.
- Maintain complete project memory and provenance.

## Architecture

| Role | Machine |
|---|---|
| Control plane | Raspberry Pi Docker orchestrator |
| Interactive client | Mac mini |
| High-power worker | Gaming PC |
| Future workers | Render nodes, vision nodes, model servers, simulation nodes |

## Production Pipeline

```
Conversation
  → Intent extraction
  → Project memory retrieval
  → Canon lookup
  → SceneSpec generation
  → Validation
  → Task routing
  → Worker execution
  → Preview
  → Vision comparison
  → Revision
  → Approval
  → Versioned asset
```

## Major Services

- Project registry
- Canon registry
- Asset registry
- Scene registry
- Episode registry
- Worker registry
- Capability registry
- Job queue
- Approval workflow
- Audit log

## Asset Strategy

Everything reusable becomes a registered asset:
ships, characters, skeletons, props, materials, camera rigs, lighting rigs,
animations, locations.

## Episode Pipeline

**Input:** Teleplay, storyboard, reference images, production notes

**Output:** Episodes, scene plans, shot lists, assets, animation jobs,
render jobs, final media

## Schemas

- `DesignIntent`
- `SceneSpec`
- `ShotSpec`
- `EpisodeSpec`
- `AssetSpec`
- `VisualObservation`
- `ToolCall`
- `ValidationReport`
- `ArtifactManifest`

## Worker Types

- Coding model
- Vision-language model
- Function router
- Blender worker
- Renderer
- Simulation worker
- Future audio and dialogue workers

## Routing Policy

**Default:** Use the least expensive competent worker.

**Escalation triggers:**
- High ambiguity
- Repeated failure
- Explicit user request

## Vision System

**Responsibilities:**
- Interpret drawings
- Extract geometry clues
- Compare renders
- Suggest revisions

**Rule:** Vision observations must distinguish observed, measured, inferred,
canon, and user-approved facts.

## Database

- **Engine:** PostgreSQL
- **Binary policy:** Store metadata only. Keep media on shared storage.

## Orchestrator (Raspberry Pi 4)

**Responsibilities:** Worker registration, heartbeats, scheduling, leases,
retries, health monitoring, backups, authentication.

## Key Decisions

- Harness is the product.
- Models are interchangeable.
- Conversation drives production.
- Schemas preserve intent.
- Deterministic tools perform creation.
- Humans approve canon changes.
- Gaming PC is optional, not required.
- Mac mini remains an interactive workstation.
- Raspberry Pi is always-on control plane.

## Future Objective

Evolve into a conversational animation studio capable of producing complete
episodic productions from scripts while preserving reusable assets and
institutional knowledge.

## Implementation Priority

1. Harness
2. Schemas
3. Asset registry
4. Worker protocol
5. Blender adapter
6. Vision pipeline
7. Episode pipeline
8. Advanced automation
