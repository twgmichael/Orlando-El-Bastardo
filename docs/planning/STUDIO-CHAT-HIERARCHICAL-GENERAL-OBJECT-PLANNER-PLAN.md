---
title: Studio Chat Hierarchical General-Object Planner Plan
created: 2026-07-28T20:58:00-04:00
updated: 2026-07-30T00:18:29-04:00
doc_type: plan
production_area: studio_chat
department: production
status: in_progress
canonical: true
canonical_for: studio_chat_hierarchical_general_object_planner
wiki: true
wiki_group: Planning
wiki_page: Studio Chat Hierarchical General-Object Planner
---
# Studio Chat Hierarchical General-Object Planner Plan

## Milestone

Studio Chat Milestone 18

## Implementation Status

Implementation complete; live rendered acceptance remains pending. The
following executable slices are implemented:

- Versioned `hierarchical_asset_intent` schema `1.0`.
- Stable semantic parts, roles, ownership, dimensions and ratios, attachment
  anchors, semantic orientation, repetition, constraints, notes, metadata, and
  preserved extension fields.
- Contract and internal-coherence validation for schema versions, identifiers,
  required-role coverage, root uniqueness, connectedness, cycles,
  parent-child agreement, dimension resolution, attachment ownership,
  orientation axes, repetition rules, and constraint references.
- Structured hierarchy diagnostics integrated into the Milestone 17 compiler
  gate. Invalid and repairable hierarchies cannot submit jobs even when a flat
  primitive fallback exists.
- A coherent tracked-vehicle fixture and focused regression tests.
- Versioned object-archetype registry schema `1.0` and registry version
  `1.1.0`.
- Initial `tracked_vehicle_v1` knowledge for required and optional roles,
  aliases, parent-role rules, proportion ranges, attachment/contact anchors,
  orientation, repetition, shape families, and supported geometry recipes.
- Idempotent tracked-vehicle grounding that makes registry-required roles
  authoritative, records alias and requirement changes, and rejects unknown
  families or incoherent family plans before job submission.
- Geometry recipes have explicit `planned` or `available` lifecycle status.
  Available recipes must name a registered deterministic executor; all others
  fail closed at the hierarchy compiler gate.
- Family-neutral executors for hierarchy groups, compound bodies, shaped
  shells, mirrored systems, linear and radial arrays, stacked sections, and
  attached directional parts.
- Root-to-leaf dimension resolution and semantic anchor placement within the
  recipe compiler, including repeated-child propagation across mirrored
  parents and stable compiled primitive ids.
- Cross-family fixtures for a tracked machine, double-decker transit body, and
  observation tower. The same executor set compiles all three without named
  object-family branches, with structural and orthographic
  silhouette-proportion tests.
- Invalid recipe parameters produce structured diagnostics and prevent build
  submission; a valid grounded tank hierarchy now compiles through the shared
  recipe layer.
- Representative tracked vehicle, wheeled vehicle, aircraft, chair, table,
  tower, and simple-robot archetypes exercise the same hierarchy and recipe
  system.
- A constrained local-LLM decomposition pass receives only the selected
  archetype vocabulary, emits semantic hierarchy rather than coordinates, asks
  one clarification when needed, and stops after at most two invalid-response
  attempts.
- One deterministic structural repair pass canonicalizes aliases, inserts only
  registry-required roles, clamps ratios, repairs parentage, anchors,
  orientation, and repetition, and records every before/after change.
- Geometry inspection gates containment, required contact, explicit
  no-overlap constraints, repetition expansion, finite transforms, positive
  scales, unique primitive ids, and deterministic silhouette evidence for all
  seven standard review views.
- Broad-prompt and root-only fixtures verify compiled or safely rejected
  outcomes across every registered family. The server suite passes 266 tests.

The remaining Milestone 18 acceptance activity is operational rather than a
missing compiler feature: run the real local model and Blender worker against
the army-tank acceptance prompt, inspect the seven rendered views, and retain a
rendered fixture proving recognizability. Stronger aesthetic visual judgment
continues to escalate rather than being guessed by deterministic code.

## Related Documents

- [Studio Chat Local LLM Output Resilience Plan](STUDIO-CHAT-LOCAL-LLM-OUTPUT-RESILIENCE-PLAN.md)
  defines the Milestone 17 ingestion, normalization, compiler-outcome, repair,
  validation, and diagnostic boundary that this planner must use.
- [Scene Graph Primitive Builder Plan](SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md)
  defines the editable semantic graph and deterministic operation contract.
- [Asset Location and Orientation Standard](ASSET-LOCATION-ORIENTATION-STANDARD.md)
  defines the shared coordinate frame and semantic directions.
- [Project Roadmap](../../PROJECT-TODO.md) tracks the executable Milestone 18
  work.

## Purpose

Move Studio Chat from a capable primitive assembler to a hierarchical
general-object builder.

A broad request such as `Build an army tank` must no longer become a loose
collection of generic primitives. The planner must first produce a coherent
functional object hierarchy, ground it against reusable object-family
knowledge, solve proportions and spatial relationships, validate the result,
and only then allow deterministic geometry compilation.

The goal is not unrestricted one-shot generation. The goal is a growing,
auditable system that can turn learned object knowledge into validated,
executable construction plans.

## How The Planner Knows What An Object Looks Like

Object knowledge comes from two complementary sources:

1. The local LLM contributes learned visual and world knowledge. It proposes
   the recognizable functional decomposition of an object: for an army tank,
   a hull, turret, cannon, two tracks, road wheels, and their roles.
2. A curated object-archetype registry grounds that proposal in deterministic
   construction knowledge: required roles, typical proportion ranges,
   attachment anchors, orientation rules, symmetry, repetition, and supported
   geometry recipes.

The LLM may propose structure and intent, but it does not choose final Blender
coordinates or invent worker capabilities. Deterministic solvers own
dimensions, anchors, transforms, repetition, contact, validation, and
compiler-safe worker instructions.

The registry should encode reusable object-family patterns rather than
prompt-specific finished models. A tank archetype may know that a turret sits
on a hull and a cannon extends forward, but it should not contain one fixed
tank mesh or one hardcoded coordinate list.

## Required Safety Invariant

No broad object request may create a build job until all of the following are
true:

- The hierarchical plan has stable semantic part identifiers.
- Required functional roles are present.
- Every child has a valid parent or explicit root role.
- Dimensions and proportions are resolved within supported bounds.
- Attachments, contact relationships, and transforms agree.
- Symmetry and repetition have deterministic expansion instructions.
- Orientation resolves into the shared coordinate frame.
- Every planned part has a supported geometry strategy.
- Structural and spatial validation passes.
- The Milestone 17 compiler outcome is `compiled`.

All other outcomes must preserve the plan, diagnostics, and repair history
without submitting build or render work.

## Target Architecture

```text
creative prompt
  -> broad asset intent
  -> hierarchical LLM decomposition
  -> archetype and semantic-role grounding
  -> root-to-leaf proportion solving
  -> attachment-anchor and placement solving
  -> semantic orientation solving
  -> symmetry and repetition expansion
  -> role-specific geometry recipes
  -> structural and spatial validation
  -> deterministic graph compilation
  -> build and review renders
  -> inspection and bounded repair
```

The hierarchy remains the source of design intent. Compiled primitives or
meshes are products of the hierarchy, not replacements for it.

## Executable Work Packages

### 1. Hierarchical Asset Contract

Define `hierarchical_asset_intent` as a versioned contract. Each node must be
able to carry:

- Stable semantic part id and human-readable name.
- Functional role and shape family.
- Parent id and owned children.
- Approximate dimensions or ratios relative to a parent/root.
- Semantic attachment anchor and contact relationship.
- Forward/up directions before numeric rotation.
- Symmetry, mirror, radial-array, or linear-array instructions.
- Required, optional, and decorative status.
- Material, construction notes, constraints, and extension fields.

The contract must preserve unknown semantic fields and compile into the
existing Semantic Asset Graph without losing hierarchy.

### 2. Object-Archetype Registry

Status: **IMPLEMENTED FOR THE V1 REPRESENTATIVE FAMILY SET** — tracked vehicle,
wheeled vehicle, aircraft, chair, table, tower, and simple robot families are
registered under registry version `1.1.0`.

Implement a versioned registry of reusable object-family knowledge. Each
archetype should declare:

- Required and optional semantic roles.
- Role aliases and recognizable synonyms.
- Parent-child rules.
- Typical dimension and proportion ranges.
- Allowed attachment anchors and contact relationships.
- Default semantic orientation.
- Symmetry and repetition expectations.
- Supported geometry recipe for each role.

Begin with representative families that exercise different construction
patterns: tracked vehicle, wheeled vehicle, aircraft, chair, table, tower, and
simple robot.

### 3. LLM Hierarchical Decomposition

Status: **IMPLEMENTED** — broad prompts for registered families invoke a
constrained semantic-only planner. Valid fenced or plain JSON is accepted,
material ambiguity returns one clarification without retrying, and malformed
responses stop after two attempts without submitting work.

Add a constrained planner prompt and strict response contract. Given a broad
asset intent, the local LLM should propose:

- The matching object family or an explicit unknown family.
- Major functional parts.
- Parent-child ownership.
- Required versus optional parts.
- Semantic relationships and orientations.
- Relative size language, without final numeric coordinates.

The planner must ask for clarification when multiple materially different
interpretations are plausible. Real local-model responses must be captured as
fixtures by behavior class.

### 4. Archetype Grounding And Role Normalization

Status: **IMPLEMENTED** — canonical grounding remains idempotent; one bounded
repair pass supplies deterministic required structure while preserving valid
optional extensions and recording auditable changes.

Ground the proposed hierarchy against the registry:

- Resolve aliases such as `barrel` to `cannon` and `treads` to `tracks`.
- Match proposed parts to canonical functional roles.
- Add an omitted required role only when the archetype makes it
  deterministic and non-creative.
- Preserve unfamiliar optional parts as extensions.
- Reject contradictory parentage or unsupported object families.
- Emit structured change records and diagnostics.

Grounding must be idempotent.

### 5. Root-To-Leaf Proportion Solver

Status: **IMPLEMENTED FOR REGISTERED V1 RANGES** — canonical root sizes and
relative child ratios resolve root-to-leaf, with invalid ratios clamped to
archetype bounds by the bounded repair pass.

Assign a canonical root bounding box, then solve child dimensions from the
root downward. The solver must:

- Apply archetype ratio ranges.
- Respect explicit user size instructions.
- Preserve proportional relationships across nested parts.
- Prevent repeated parts and decorative details from inheriting full
  root-sized defaults.
- Produce diagnostics when constraints cannot be satisfied.

This is the primary defense against failures such as rocket fins becoming
larger than the body.

### 6. Attachment And Placement Solver

Status: **IMPLEMENTED FOR V1 SEMANTIC ANCHORS** — placements resolve after
dimensions, contact and containment are inspected, and explicit no-overlap
constraints fail closed.

Define semantic anchors such as `top_center`, `bottom_center`,
`front_center`, `rear_center`, `left_side`, `right_side`, `inside`, and
`around`.

Resolve child placement only after dimensions are known. Verify that:

- Attached parts touch their supporting parent.
- On-top-of parts are centered and supported unless explicitly offset.
- Mirrored parts remain on opposite sides.
- Contained parts remain inside their parent envelope.
- Distinct parts do not unintentionally occupy the same space.

### 7. Semantic Orientation Resolver

Status: **IMPLEMENTED FOR V1 PRIMITIVE DIRECTIONS** — semantic forward/up axes
resolve deterministically and review evidence is produced for every standard
view.

Express intent with semantic directions before converting to Euler rotations:

- A tank cannon points forward.
- Track length runs front-to-rear.
- Road-wheel axles run left-to-right.
- A turret base faces down toward the hull.
- A rocket nose points up and fins extend outward near the body bottom.

The resolver must convert these directions into the canonical local coordinate
frame and test them from every standard review view.

### 8. Compound Geometry Recipe Compiler

Status: **IMPLEMENTED FOR THE V1 SHARED EXECUTOR SET** — family-neutral
executors compile hierarchy groups, compound bodies, shaped shells, mirrored
systems, repeated arrays, stacked sections, and attached directional parts
into deterministic primitive plans. Further mesh strategies and rendered
inspection remain open.

Map grounded semantic roles to supported construction recipes. Recipes may use
multiple primitives, semantic geometry, arrays, modifiers, or future mesh
strategies.

Examples:

- Tank hull: beveled compound hull form.
- Turret: low rounded or faceted rotating body.
- Cannon: barrel and muzzle assembly.
- Track: track envelope with simplified tread or repeated links.
- Road wheels: repeated side-oriented cylinders.

Concrete objects must not collapse into generic boxes when a supported
compound recipe exists.

#### Generalization-First Geometry Recipe Layer

Status: **IMPLEMENTED AND STRUCTURALLY VERIFIED** — the same executor set
passes tracked-machine, double-decker-transit, and observation-tower fixtures.
The suite checks family-neutral source, stable expansion, inherited mirrored
repetition, linear and radial arrays, invalid-parameter diagnostics, submission
gating, and distinct orthographic silhouette proportions. Rendered review
evidence remains part of Work Package 12.

Before expanding the object-archetype registry, implement deterministic,
reusable geometry-recipe executors for:

- Compound bodies.
- Beveled and rounded shells.
- Mirrored wheel and track systems.
- Linear and radial arrays.
- Stacked structural sections.
- Attached directional parts such as barrels, wings, handles, and pipes.

Recipes must consume semantic roles, dimensions, proportions, attachment
anchors, orientation, symmetry, and repetition from
`hierarchical_asset_intent`. Recipe executors must not contain named-object
logic such as `build_tank` or `build_bus`.

Acceptance criteria:

- Each recipe is exercised successfully across at least three unrelated object
  families.
- A tank, a double-decker bus, and at least one non-vehicle fixture exercise
  the shared recipe layer.
- Recipe executors contain no object-family-specific construction branches.
- Unsupported recipe parameters fail with structured diagnostics and do not
  submit a build.
- The compiler returns `compiled` only when every required role resolves to an
  available deterministic executor.
- Structural and visual tests verify hierarchy, contact, orientation,
  proportions, repetition, and recognizable silhouettes.
- Additional object archetypes are deferred until this generalization suite
  passes.

### 9. Symmetry And Repetition Expansion

Status: **IMPLEMENTED** — mirrored, radial, and linear repetition expands to
stable instance ids; linear arrays use the parent span when spacing is not
explicit.

Implement deterministic:

- Left/right mirroring.
- Radial arrays.
- Linear arrays.
- Equal distribution within a parent span.
- Repetition counts derived from available space and role constraints.

The hierarchy should retain one semantic repeated-group definition while the
compiled graph receives stable instance ids.

### 10. Validation Gates

Status: **IMPLEMENTED** — contract, archetype, recipe, compile, and geometry
inspection failures return structured diagnostics and cannot submit jobs.

Validate the plan in stages:

- Schema and identifier validity.
- Required-role coverage.
- Parent-child connectedness.
- Ratio and dimension bounds.
- Attachment and supported-contact validity.
- Semantic direction and numeric orientation agreement.
- Symmetry and repetition consistency.
- Collision, containment, and unintended-overlap checks.
- Supported geometry coverage.
- Deterministic compilation completeness.

Diagnostics must identify the part, failed constraint, pipeline stage, repair
class, and suggested next action.

### 11. Bounded Structural And Spatial Repair

Status: **IMPLEMENTED FOR DETERMINISTIC V1 REPAIRS** — one repair pass handles
missing required roles, ratios, parentage, anchors, orientation, and
repetition. Creative ambiguity returns clarification.

Add narrowly scoped repair operations for deterministic failures:

- Add a missing archetype-required part.
- Resize a part into its allowed ratio range.
- Move a floating part to its declared anchor.
- Rotate a directional part onto its required axis.
- Reattach or redistribute repeated parts.

Repairs must record before/after state and stop under the Milestone 17 bounded
repair policy. Ambiguous aesthetic or identity decisions require
clarification.

### 12. Plan, Build, Inspect, Repair Loop

Status: **IMPLEMENTED THROUGH DETERMINISTIC CANDIDATE INSPECTION; LIVE RENDERED
ACCEPTANCE PENDING** — compiled geometry is checked against hierarchy metadata
and silhouette bounds before submission, and successful jobs retain the
existing seven-view review request. The final rendered army-tank acceptance
run remains to be captured.

After deterministic compilation:

1. Build the candidate asset.
2. Render all standard review views.
3. Inspect structural evidence against the validated hierarchy.
4. Classify visible failures such as missing, floating, intersecting,
   misoriented, or disproportionate parts.
5. Apply one permitted repair and rebuild, or stop with diagnostics.

Initial inspection may use deterministic geometry metadata and silhouettes.
Stronger visual judgment may be escalated rather than guessed.

### 13. Fixtures, Evaluations, And Incremental Rollout

Status: **IMPLEMENTED FOR STRUCTURAL PIPELINE COVERAGE** — fixtures exercise
successful decomposition, invalid bounded responses, clarification, repair,
collision, containment, and all seven registered families. A live rendered
army-tank fixture remains the final acceptance artifact.

Create real-response fixtures and rendered acceptance cases for:

- Army tank.
- Fire truck or other wheeled vehicle.
- Biplane or other aircraft.
- Office chair.
- Castle tower.
- Simple robot.

Evaluate hierarchy, required-part coverage, proportions, attachments,
orientation, repetition, deterministic compilation, review inspection, and
repair behavior.

Roll out by supported object family rather than claiming universal support:

1. Vehicles.
2. Furniture.
3. Architecture.
4. Machines and tools.
5. Creatures and characters.
6. Novel and unrecognized compositions.

Successful validated plans may become reusable family examples. They must not
become a brittle catalog that prevents novel composition.

## Army Tank Reference Walkthrough

For `Build an army tank`, the expected planning result is conceptually:

```text
army_tank
├── hull
│   ├── upper_hull
│   └── lower_hull
├── turret
│   ├── turret_body
│   └── cannon
└── running_gear
    ├── left_track
    │   └── left_road_wheels
    └── right_track
        └── right_road_wheels
```

Expected grounded relationships:

- The turret attaches to `hull.top_center`.
- The cannon attaches to `turret.front_center` and points `front`.
- Tracks mirror across the hull's left and right sides.
- Road wheels repeat inside each track span.
- The hull is wide and low.
- The turret is smaller than the hull.
- The cannon is narrow and elongated.

The exact style may vary, but these relationships must remain recognizable and
physically coherent.

## Milestone 18 Acceptance Target

`Build an army tank` reliably produces a recognizable, correctly proportioned
tank with a hull, turret, forward cannon, two side tracks, and repeated road
wheels without prompt-specific hardcoded coordinates.

Acceptance requires:

- The local LLM produces or repairs into the canonical hierarchy.
- Archetype grounding preserves user intent and supplies only deterministic
  required structure.
- Proportion, attachment, orientation, symmetry, and repetition solvers pass.
- Every required role compiles through supported geometry recipes.
- Standard review renders show one connected tank rather than scattered
  primitives.
- Invalid, ambiguous, or unsupported plans create no job and return structured
  diagnostics.
- The same architecture passes representative non-tank object-family fixtures.

## Explicit Non-Goals

- A universal object model in one release.
- A fixed catalog of finished named-object meshes.
- Letting the local LLM emit Blender code or final arbitrary coordinates.
- Silently inventing ambiguous creative direction.
- Using visual review to bypass structural validation.
- Preserving obsolete primitive-only compatibility paths during alpha.
