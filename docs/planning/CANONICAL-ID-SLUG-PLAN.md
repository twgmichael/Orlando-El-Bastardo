---
title: Canonical ID Slug Plan
created: 2026-07-15T22:46:06-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: plan
production_area: assets
department: pipeline
status: draft
canonical: true
canonical_for: canonical_id_slugging
wiki: false
wiki_group: Planning
---
# Canonical ID Slug Plan

Recorded 2026-07-15 after a studio-chat prompt produced a confusing canonical
id for a letter-shaped ship request.

## Problem

The current prompt-to-asset path can generate canonical ids by taking the first
few useful prompt words and appending the asset variant suffix. That makes ids
short, but it can drop the most meaningful differentiator.

Example:

```text
Prompt: Build a spaceship that looks like the capital letter V.
Current canonical_id: asset_spaceship_that_looks_like_A
```

The final `_A` is the asset variant suffix, not the letter shape. The actual
problem is that the slug was truncated before preserving `capital_letter_v`.

## Decision

Canonical ids do not need to be full human-readable prompt summaries. They
should be recognizable, stable asset identities.

Use:

- `job_id` as the unique build/run key.
- `canonical_id` as the durable asset identity.
- A short semantic slug for scan/debug value.
- The existing variant suffix only for asset variant/version semantics.

Avoid pure UUID-style canonical ids for assets that humans will review, track,
or reference across jobs. Avoid prompt-prose canonical ids because they become
long, unstable, and noisy.

## Best Practice

Generate canonical ids locally with deterministic rules, not extra LLM calls.
No paid model or external service should be required.

Priority order for slug tokens:

1. Asset kind prefix: `ship`, `location`, `prop`, `character`, or `asset`.
2. Primary object identity.
3. Distinctive modifier or shape phrase.
4. Variant/version suffix.

Preserve important differentiators even when they appear late in the prompt:

- `capital letter V` -> `capital_letter_v`
- `letter V` -> `letter_v`
- `shaped like V` -> `v_shaped`
- `looks like X` -> preserve `x` when it is a short object, letter, or number.

For the example prompt, preferred output is:

```text
ship_capital_letter_v_A
```

Acceptable fallback:

```text
asset_spaceship_capital_letter_v_A
```

Bad output:

```text
asset_spaceship_that_looks_like_A
```

## Implementation Notes

- Keep the deterministic slug function small and testable.
- Do not increase LLM usage just to improve slugs.
- Normalize `spaceship`, `ship`, and `fighter` prompts toward a `ship_` prefix
  when the inferred kind is a vehicle/ship.
- Keep `job_id` in output paths to avoid collisions between repeated builds of
  the same canonical asset.
- If the project later adopts clearer version semantics, consider replacing
  `_A` with `_v001`; do not change that casually because existing assets already
  use `_A`.

## Verification Cases

```text
Build a spaceship that looks like the capital letter V.
=> ship_capital_letter_v_A

Build a spaceship shaped like a crescent.
=> ship_crescent_shaped_A

Build a small rover with two antennae.
=> vehicle_small_rover_A or prop_small_rover_A, depending on kind policy

Build a compact sci-fi garage with workbench, tool wall, lift platform, and one small rover.
=> location_sci_fi_garage_A or asset_sci_fi_garage_A, depending on kind policy
```

## Open Question

Decide whether `spaceship` should always map to `ship_` or whether all vehicles
should use a broader `vehicle_` prefix. The current recommendation is `ship_`
for space vessels because it is shorter and more domain-specific.
