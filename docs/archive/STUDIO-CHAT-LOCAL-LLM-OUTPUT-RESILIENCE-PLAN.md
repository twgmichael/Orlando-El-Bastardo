---
title: Studio Chat Local LLM Output Resilience Plan (Archived)
created: 2026-07-26T00:00:00-04:00
updated: 2026-08-15T00:00:00-04:00
archived: 2026-08-15
doc_type: progress_report
production_area: pipeline
department: production
status: archived
canonical: false
wiki: true
wiki_group: Journal
wiki_page: Studio-Chat-Local-LLM-Output-Resilience-Plan
wiki_order: 60
---
# Studio Chat Local LLM Output Resilience Plan

Date: 2026-07-26

Status: **IMPLEMENTED**

## Related Documents

- [OEB Studio Chat Lightweight Plan](../planning/OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md)
  coordinates this work as Studio Chat Milestone 17.
- [OEB Studio Chat Progress](OEB-STUDIO-CHAT-PROGRESS-2026-07-23.md)
  records the chat-to-harness implementation history.
- [Conversation To Build Loop](../planning/CONVERSATION-TO-BUILD-LOOP.md)
  defines the responsibility boundary between local models and deterministic
  workers.

## Purpose

Studio Chat cannot maintain a regression test for every exact response a local
LLM may produce. Model output is variable, evolving, and shaped by prompt
history, model version, sampling settings, and user language.

The harness should instead treat local LLM output as untrusted,
semi-structured input. It should preserve the model's expressive asset intent
while making deterministic job submission depend on explicit normalization,
validation, and compilation.

The testing strategy should cover contracts, invariants, and representative
failure classes. Real model responses should become fixtures only when they
expose a new behavior class that existing tests do not cover.

## Required Safety Invariant

Only a pipeline result with status `compiled` may create a harness worker job.

`needs_repair`, `needs_clarification`, `unsupported`, and `invalid` results must
preserve the original intent and diagnostics but must not submit build or
render work.

## Response Capture

For every local-model interaction, retain:

- User prompt and relevant thread context.
- System prompt, model identifier, and generation settings.
- Complete raw model response.
- Extracted JSON or parse failure.
- Tolerant repairs applied during ingestion.
- Normalized asset intent and a record of normalization changes.
- Resolver request, response, and retry count.
- Compiler result and diagnostics.
- Final deterministic job payload and job-creation response, when compiled.

Capture should use the existing append-only Studio Chat trace ledger and
message/asset revision records. Unknown model fields should be retained in the
audit record rather than silently discarded.

## Broad Asset Intent Envelope

Keep strict JSON as the transport container, but keep the creative schema
deliberately broad. Stable top-level fields should identify the action,
confidence, clarification or escalation state, and asset intent.

The asset intent may contain:

- Asset name, kind, and purpose.
- Objects, named parts, and features.
- Materials and visual modifiers.
- Orientation and transforms.
- Relationships and placement constraints.
- Semantic geometry and construction notes.
- Unknown extension fields preserved for later normalization or audit.

The ingestion boundary must not require primitive build operations. Primitive
geometry remains an internal compiler and worker implementation detail.

## Tolerant Ingestion

The parser should:

- Extract JSON from fenced blocks or surrounding prose.
- Accept harmless casing and alias differences.
- Repair narrowly defined syntax defects when the intended structure is
  unambiguous.
- Supply safe structural defaults for recoverable omissions.
- Preserve rich and unknown fields.
- Never invent meaningful art direction, parts, relationships, or materials.

Every repair or default must be recorded so the original and normalized forms
remain inspectable.

## Normalization

Normalization should:

- Canonicalize known aliases without reducing semantic detail.
- Normalize asset kinds, identifiers, materials, transforms, directions, and
  review views.
- Preserve modifiers such as `half`, `flat`, `squished`, `tapered`, or
  `asymmetric` as intent until a compiler explicitly supports them.
- Be idempotent: normalizing an already normalized result should not change it.
- Return structured warnings for preserved but not yet compileable intent.

Recoverable omissions may receive explicit defaults. Ambiguous creative
decisions must become clarification questions rather than guessed values.

## Compiler Boundary

The deterministic compiler validates:

- Required identifiers and asset ownership.
- Numeric bounds and transform shapes.
- Named-part and relationship references.
- Material and modifier support.
- Output paths and artifact declarations.
- Construction operations available to the worker.
- Completeness of the executable build plan.

The compiler returns one of:

- `compiled`: complete deterministic build operations are available.
- `needs_repair`: the intent is useful but has a focused, repairable contract
  mismatch.
- `needs_clarification`: a user decision is required.
- `unsupported`: intent is preserved, but no deterministic compilation path is
  available.
- `invalid`: the response cannot be safely interpreted.

## Bounded Repair

Allow one focused local-LLM repair pass by default. A second attempt is allowed
only for an explicitly recoverable validation class.

The repair prompt should contain:

- The original user request.
- The raw and normalized asset intent.
- The exact compiler diagnostic.
- The narrow output contract required to resolve that diagnostic.
- An instruction to preserve user intent and avoid inventing new assets or
  implementation APIs.

If repair still does not compile, stop. Show a clarification or diagnostic,
preserve the complete exchange, and submit no job.

## Test Strategy

Test behavior classes rather than every exact model sentence.

Required contract and failure-class coverage:

- Valid minimal and rich asset intent.
- JSON inside fences or surrounding prose.
- Malformed but narrowly repairable JSON.
- Irrecoverable JSON.
- Missing required and optional fields.
- Extra and unknown fields.
- Unexpected asset kinds and aliases.
- Semantic geometry, named parts, relationships, and construction notes.
- Materials and geometric modifiers.
- Clarification and escalation responses.
- Normalization defaults, aliases, and idempotence.
- Compiler success, unsupported intent, and invalid intent.
- One-pass repair success.
- Repair exhaustion.
- Guaranteed no-submission for every result other than `compiled`.
- Structured diagnostics instead of generic HTTP 500 responses.

Add property-oriented tests for invariants:

- Unknown fields survive ingestion and normalization.
- Normalization is idempotent.
- Valid rich intent does not lose semantic detail.
- Invalid numeric values never reach a worker payload.
- A worker job is created if and only if compilation succeeds.

## Regression Fixture Policy

Maintain a curated corpus of real local LLM exchanges.

Add a response fixture only when it:

- Reveals a new parser, normalizer, validator, compiler, or diagnostic behavior
  class.
- Reproduces a production failure that existing representative fixtures do not
  cover.
- Protects an important semantic-preservation invariant.

Each fixture should identify the behavior it protects, redact sensitive
values, preserve the original raw response, and include the expected pipeline
outcome. Do not add fixtures that differ only in wording from an already
covered behavior class.

## Diagnostics

Replace generic server failures with structured diagnostics containing:

- Pipeline stage.
- Outcome status.
- Human-readable reason.
- Machine-readable diagnostic code.
- Recoverable and preserved fields.
- Repair attempt count.
- Suggested next action.
- Trace identifier for Raw Debug and audit lookup.

Normal chat should show the useful clarification or failure summary. Raw Debug
and trace views should retain the complete technical record.

## Implementation Order

1. Define the broad asset-intent envelope and pipeline outcome contract.
2. Centralize raw response capture and trace correlation.
3. Add tolerant parsing with an explicit repair log.
4. Add idempotent normalization with semantic field preservation.
5. Move strict validation to the deterministic compiler boundary.
6. Enforce the `compiled`-only job-submission gate.
7. Add the bounded repair pass.
8. Add structured API and inline chat diagnostics.
9. Build the failure-class, property, and fixture test suites.
10. Exercise representative fixtures through Docker-backed integration tests.

## Acceptance Criteria

- Arbitrary local LLM output is preserved before parsing.
- Rich asset intent survives parsing and normalization.
- Recoverable structural defects are repaired transparently and audibly.
- Ambiguous creative decisions result in clarification rather than invention.
- Unsupported intent is retained and reported without creating a worker job.
- Only `compiled` results can create build or render jobs.
- Known failure classes return structured diagnostics and never a generic
  internal server error.
- New real-response fixtures are added by behavior class, not exact wording.
- Docker-backed tests verify the end-to-end submission gate.
