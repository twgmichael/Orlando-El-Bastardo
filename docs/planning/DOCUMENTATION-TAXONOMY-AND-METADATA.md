# Documentation Taxonomy And Metadata

Adopted: 2026-07-16

Status: Draft

## Purpose

OEB needs documentation that can be read by humans and routed by tools without
guessing. This document defines the production terms and metadata fields we are
adopting for project documentation, including public wiki docs and local-only
machine notes.

The goal is not bureaucracy. The goal is consistent language, predictable wiki
sync behavior, and clear production memory as the conversational 3D studio grows.

## Core Rule

Every markdown document should be taggable with explicit metadata. The metadata
should say what the document is, what production area it belongs to, whether it
is canonical, whether it belongs in the public wiki, and how it should be
grouped.

The wiki sync should read metadata instead of guessing from filenames whenever
possible.

`docs/local/**` remains deliberately excluded from git and public wiki sync, but
local docs should still use the same metadata shape for consistency and sanity.

## Front Matter Shape

Use YAML front matter at the top of markdown files:

```yaml
---
title: Asset And Location Orientation Standard
doc_type: standard
production_area: assets
department: pipeline
status: active
canonical: true
canonical_for: asset_location_orientation
wiki: true
wiki_group: Standards
adopted_terms:
  - standard
  - production_area
  - canonical
---
```

## Metadata Fields

### `title`

Human-readable document title.

Source context: common publishing, studio documentation, technical writing.

OEB use: wiki page display title and document identity.

Adopted: 2026-07-16

### `doc_type`

What kind of production document this is.

Allowed values:

- `standard`
- `plan`
- `design_record`
- `progress_report`
- `decision_log`
- `runbook`
- `reference`
- `register`
- `spec`

Adopted: 2026-07-16

### `production_area`

The production subject area the document primarily belongs to.

Allowed values:

- `assets`
- `characters`
- `props`
- `sets`
- `locations`
- `vehicles`
- `story`
- `layout`
- `animation`
- `rigging`
- `camera`
- `lighting`
- `rendering`
- `editorial`
- `sound`
- `pipeline`
- `publishing`
- `security`
- `operations`
- `documentation`

Adopted: 2026-07-16

### `department`

The production department or discipline most responsible for the document.

Allowed values:

- `art`
- `story`
- `layout`
- `modeling`
- `rigging`
- `animation`
- `camera`
- `lighting`
- `rendering`
- `editorial`
- `sound`
- `pipeline`
- `production`
- `security`

Adopted: 2026-07-16

### `status`

The lifecycle state of the document.

Allowed values:

- `draft`
- `active`
- `approved`
- `superseded`
- `archived`

Adopted: 2026-07-16

### `canonical`

Whether this document is the authoritative source for its topic.

Allowed values:

- `true`
- `false`

OEB rule: only one document should be canonical for a specific topic unless the
scope is explicit.

Adopted: 2026-07-16

### `canonical_for`

Stable snake_case topic key for the thing this document is authoritative about.

Examples:

- `asset_location_orientation`
- `wiki_sync`
- `journeyblaster_design`
- `rigging_standard`

Required when `canonical: true`.

Adopted: 2026-07-16

### `wiki`

Whether this document should be published by the wiki sync.

Allowed values:

- `true`
- `false`

OEB rule: `docs/local/**` should use `wiki: false`.

Adopted: 2026-07-16

### `wiki_group`

Sidebar group for public wiki placement.

Allowed values:

- `Home`
- `Design`
- `Standards`
- `Planning`
- `Operations`
- `Journal`
- `Tracking`

Required when `wiki: true`.

Adopted: 2026-07-16

### `adopted_terms`

List of taxonomy terms used by the document when that list is useful for
auditing or migration.

Adopted: 2026-07-16

## Adopted Production Terms

### Standard

OEB meaning: an authoritative rule set that current work should follow.

Industry source/context: animation, VFX, television, film, and game production
all use standards for naming, rigs, asset delivery, color, camera, editorial,
pipeline, and handoff requirements.

Use for: orientation rules, rigging rules, schema rules, security rules.

Adopted: 2026-07-16

### Plan

OEB meaning: intended work or architecture that may still change.

Industry source/context: production plans, technical implementation plans,
shooting plans, department plans, delivery plans.

Use for: upcoming build work, workflow proposals, implementation roadmaps.

Adopted: 2026-07-16

### Design Record

OEB meaning: creative development history for a specific asset, vehicle,
location, character, or visual concept.

Industry source/context: production design records, art department references,
asset design bibles, model packets, look-development notes.

Use for: JourneyBlaster, bar scene visual direction, recurring asset families.

Adopted: 2026-07-16

### Progress Report

OEB meaning: dated production progress and findings. Historical, not canonical.

Industry source/context: dailies notes, production reports, milestone reports,
department status updates.

Use for: dated `PROGRESS-*` docs and milestone summaries.

Adopted: 2026-07-16

### Decision Log

OEB meaning: locked decisions with enough rationale to prevent re-litigating
the same issue.

Industry source/context: production decision logs, show bible decisions,
technical direction records.

Use for: irreversible or high-impact choices about pipeline, workflow, story,
assets, or standards.

Adopted: 2026-07-16

### Runbook

OEB meaning: step-by-step operating procedure for a tool, service, machine, or
pipeline task.

Industry source/context: pipeline operations, render farm operations, editorial
handoff procedures, studio support docs.

Use for: local commands, worker operations, deployment, recovery steps.

Adopted: 2026-07-16

### Reference

OEB meaning: supporting research, examples, source analysis, or contextual
notes.

Industry source/context: visual reference boards, technical references, shot
references, production research packets.

Use for: spacescape research, animation technique notes, external resource
notes.

Adopted: 2026-07-16

### Register

OEB meaning: tracked inventory of project facts.

Industry source/context: asset registers, shot registers, license registers,
production tracking databases.

Use for: provenance, asset registry, open questions.

Adopted: 2026-07-16

### Spec

OEB meaning: implementation-ready technical contract.

Industry source/context: pipeline specs, delivery specs, schema specs, vendor
handoff specifications.

Use for: schemas, API contracts, harness implementation specs.

Adopted: 2026-07-16

## Lifecycle Rules

`draft` means exploratory or incomplete.

`active` means current work should consult it, but it may still change.

`approved` means accepted as binding until superseded.

`superseded` means replaced by a newer canonical document.

`archived` means preserved for history only.

Progress reports stay historical. They should not be canonical unless a specific
exception is explicitly recorded.

## Wiki Sync Rules

The wiki sync should eventually use document metadata as the routing contract.

Rules:

- `wiki: true` means publish to the public wiki.
- `wiki: false` means do not publish.
- `wiki_group` controls sidebar group.
- `title` controls display title unless a tool-specific override is added later.
- `canonical: true` should be visible in generated wiki output.
- `canonical_for` is required when `canonical: true`.
- Missing metadata should warn during migration.
- After migration, missing required metadata should fail the sync for public docs.
- `docs/local/**` must never publish, even if accidentally tagged otherwise.

## Application Examples

### Orientation Standard

```yaml
---
title: Asset And Location Orientation Standard
doc_type: standard
production_area: assets
department: pipeline
status: active
canonical: true
canonical_for: asset_location_orientation
wiki: true
wiki_group: Standards
---
```

### JourneyBlaster Design Record

```yaml
---
title: JourneyBlaster Ship Design Record
doc_type: design_record
production_area: vehicles
department: art
status: active
canonical: true
canonical_for: journeyblaster_design
wiki: true
wiki_group: Design
---
```

### Progress Report

```yaml
---
title: Progress 2026-07-06 Phase 4 And 5
doc_type: progress_report
production_area: pipeline
department: production
status: archived
canonical: false
wiki: true
wiki_group: Journal
---
```

### Local Commands

```yaml
---
title: Local Commands
doc_type: runbook
production_area: operations
department: pipeline
status: active
canonical: false
wiki: false
wiki_group: Operations
---
```

## Migration Plan

1. Add this metadata format to new docs first.
2. Tag public wiki docs incrementally.
3. Tag `docs/local/**` for consistency with `wiki: false`.
4. Update `tools/sync_wiki.py` to read front matter.
5. Keep the current hard-coded page table only until metadata coverage is good
   enough to replace it.
6. Keep `docs/local/**` hard-excluded regardless of metadata.

