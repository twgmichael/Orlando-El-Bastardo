---
title: Architecture
created: 2026-07-03T21:43:45-04:00
updated: 2026-08-08T00:00:00-04:00
doc_type: spec
production_area: pipeline
department: pipeline
status: active
canonical: true
canonical_for: pipeline_architecture
wiki: true
wiki_group: Design
wiki_page: Architecture
wiki_order: 10
---
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
- Automation may lower fidelity, substitute assets, simplify motion, invent
  provisional staging, and make provisional creative decisions. It may not
  silently convert those decisions into canonical truth. The model can write
  the draft; humans decide what becomes production truth. See "LLM role"
  below.

## Mathematics, Language, And Blueprint

At the center of every 3D model are mathematics and language. Mathematics
defines what can exist; language defines what is intended. The Blueprint
connects the two by describing mathematical constructions in human terms so
any compatible builder can realize them.

The studio catalogs mathematical definitions and operations, not every
conceivable shape. A primitive is a named mathematical definition rather than
necessarily a saved object. Shapes emerge by composing primitives, operations,
constraints, and relationships.

Store mathematics rather than meshes whenever mathematics fully preserves the
intent. A particular mesh becomes authoritative only when its exact realization
carries meaningful artistic or production decisions, including sculpting,
topology, UV layout, rigging, simulation results, or deliberate optimization.

```text
human language
  -> Blueprint (precise intent)
  -> semantic asset graph
  -> deterministic mathematical operations
  -> builder-specific geometry
  -> rendered pixels
```

## Canonical Semantic State

The durable editable model is a semantic asset or scene graph, not a generated
GLB and not the transient state of a browser or DCC. The graph contains named
parts, relationships, transforms, materials, constraints, construction
definitions, and revision identity.

Chat, viewport, renderer, undo history, agents, and headless tests must all
read and write this same canonical state. A browser editor is one client of the
graph; it must not become a second source of truth.

Every mutation crosses one structured operation API. The initial vocabulary
should cover:

- `add`
- `remove`
- `replace`
- `move`
- `rotate`
- `attach`
- `recolor`
- `resize`
- `group`
- `undo`

Operations name their targets, expected base revision, parameters, and
preserved constraints. They produce a proposed graph diff before mutation.
The same operation compiler and validator serve UI actions, agent actions,
tests, and headless automation.

Validation must compare requested intent, selected targets, proposed operations,
and graph invariants before committing a revision. A request to add a tube
must not be accepted as an operation that replaces a cone. Stale revisions,
missing or ambiguous targets, unsupported operations, and broken constraints
must fail without mutating canonical state.

Agent and MCP interfaces should expose information and authority separately:

- resources: scene summary, selected revision, part catalog, and constraints
- tools: inspect, propose, validate, apply, undo, and render
- prompts: task-specific translation guidance and examples

Agents use the same operation API as human-facing clients. Human-in-the-loop
surfaces should show the proposed edit, selected targets, graph diff,
validation result, and resulting revision, with undo and retry available.

## Editor Adoption Sequence

Learn from Pascal Editor's architecture before considering its application or
components. Borrow its semantic scene graph, operation-driven editing,
agent-access pattern, shared live state, and review affordances now.

Adopt editor capability in this order:

1. Define the OEB semantic asset graph and revision model.
2. Implement the deterministic, headless operation compiler and validator.
3. Add a lightweight WebGL sandbox that edits the same graph through the same
   operation API.
4. Evaluate Pascal-style components or embedding only when they save work
   without changing the established contracts.

Do not embed a full external editor before asset state, revisions, and the
operation vocabulary are stable. The editor must conform to OEB's core rather
than define it.

## LLM role

Automation may lower fidelity, substitute assets, simplify motion, invent
provisional staging, and make provisional creative decisions. It may not
silently convert those decisions into canonical truth. This replaces the
older, stricter framing of this section: the model can write the draft;
humans decide what becomes production truth. A draft carries no authority
of its own — it becomes production truth only through the same human
review/promotion step Canonical Assets already require, never by default
and never silently.

Approved: translator, constraint engine, scene fitting assistant, format
conversion layer, structured extraction layer, and — scoped to provisional
draft output only, never to anything treated as final — semantic asset
substitution, motion simplification, and provisional staging/blocking
decisions.

Rejected: story authorship (inventing narrative content beyond the
human-authored source), silently promoting a provisional or draft decision
to canonical or production truth, and unvalidated final file authorship.

The LLM should usually output `SceneIntent` or a partially resolved `SceneSpec`,
not direct Blender/Godot/USD files. This is safer, lets a deterministic resolver
enforce approved assets, keeps the LLM constrained, and improves reproducibility.

## Export targets

- **Blender** — scene name, linked collections/assets, cameras, timeline markers, action assignments by frame, audio strips/speaker objects, render settings. Best for asset authoring, rigging, shot polish, animation editing, final offline renders.
- **Godot** — `.tscn` scene, actor nodes, set instance, camera rig nodes, `SceneDirector.gd` controller, event timeline resource. Best for realtime previs, interactive playback, branching narrative, fast iteration.
- **USD** — root layer, set/character/prop references, camera prims, timeline sidecar JSON for cue timing. Best for interchange, shot composition, multi-tool compatibility, future-proofing.
