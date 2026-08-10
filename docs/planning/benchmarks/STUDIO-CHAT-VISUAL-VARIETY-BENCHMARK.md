---
title: Studio Chat Visual-Variety Benchmark
created: 2026-08-06T15:08:01-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: register
production_area: pipeline
department: pipeline
status: active
canonical: false
wiki: true
wiki_group: Planning
---
# Studio Chat Visual-Variety Benchmark

Phase 4 of [REVIEW-AUDIT.md](../REVIEW-AUDIT.md) section 9: replace
"how many milestones shipped" with a real, re-runnable signal for whether
Studio Chat is producing more varied, detailed output over time.

## What it measures

Structural variety, not visual quality: object count and the mix of
primitive types (`Cube`/`Cylinder`/`Sphere`/`Cone`/`Torus`/wedge/hemisphere)
actually used per build, parsed from the real worker's Blender export log.
This is a cheap, objective proxy for "still just boxy primitives" versus
"using the recipe library" — it does not judge whether a build looks good,
only whether it's structurally differentiated. Pair with human/gallery
review (`/review/jobs/<job_id>`) for the subjective call.

## Tool

`tools/studio_chat_benchmark.py`. Submits a fixed set of 8 creative
prompts to a running harness's real `/api/v1/studio-chat` endpoint (same
path the CLI and browser UI use — real local LLM, real resolver/compiler,
real worker, real Blender), waits for each job, and records primitive
count/mix per job.

```bash
python3 tools/studio_chat_benchmark.py \
  --harness-url http://localhost:8088 \
  --admin-token local-admin-token \
  --output docs/planning/benchmarks/results.jsonl
```

Requires a running harness with a registered worker (the
`oeb-studio-harness-local` Docker stack + a live worker agent, e.g.
`render-mac-01`) and Ollama serving `oeb-qwen2.5-3b`. Each run appends one
JSON line to `results.jsonl` — never overwrite that file; append-only so
runs stay comparable over time.

The 8 prompts are fixed and must not be edited casually — changing a
prompt breaks comparability with prior `results.jsonl` entries for it.
They deliberately span single-category furniture (chair/cabinet/bed/table
— exercises the Phase 2 category-routing fix), a multi-part vehicle, an
aircraft, a lit prop, and a location, not just one easy case.

## Baseline run — 2026-08-06

First run, captured immediately after Phase 0-2 of the review-audit plan
landed (auth/Docker docs, heuristic-layer consolidation, and the
`scene_object_category` LLM-category-routing fix). 8/8 completed.

| Prompt | Primitives | Mix | Distinct kinds |
|---|---|---|---|
| Office chair, rounded seat | 5 | Cube×4, Cylinder×1 | 2 |
| Wooden storage cabinet, two drawers | 3 | Cube×3 | 1 |
| Small bed, soft mattress + pillow | 4 | Cube×4 | 1 |
| Round dining table, rounded corners, thin legs | 10 | Cylinder×8, Cube×2 | 2 |
| Two-wheeled motorcycle | 2 | Cylinder×2 | 1 |
| Small fighter spaceship, swept wings, cockpit | 5 | Cylinder×1, Cube×4 | 2 |
| Floor lamp, warm glow | 2 | Cylinder×2 | 1 |
| Park bench next to a tree | 7 | Cube×4, Cylinder×2, Sphere×1 | 3 |

Totals: 38 primitives across 8 builds. **Only 3 primitive kinds appear at
all — Cube, Cylinder, Sphere — across every prompt in the set.** No Cone,
Torus, wedge, or hemisphere shapes were used anywhere, and no bevel/subsurf
or other real modifier-based differentiation occurred (consistent with
`REVIEW-AUDIT.md` section 8's finding that most `shape`/`style_details`
fields are still captured but not consumed as geometry). Highest variety
in this run: the park bench (3 kinds) and the rounded table (which at
least visibly differs from the unrounded case via extra corner cylinders).
Most builds max out at 1-2 kinds.

This is the number to move. A future Phase-2-continuation pass (per
`REVIEW-AUDIT.md` section 8/10: wiring `edge_profile`/`style_details` into
real geometry ops beyond the current `rounded`/`thin_legs`-on-table case,
or widening which recipes exist at all) should be judged by whether
`distinct_primitive_kinds` and the presence of non-Cube/Cylinder/Sphere
shapes goes up on a re-run of this same prompt set — not by milestone
count.

## Re-running

Re-run after any change to the resolver, compiler, or
`tools/primitive_asset_builder.py`, and diff the new line in
`results.jsonl` against the baseline above (or a later run) to see whether
variety actually moved, regressed, or stayed flat.
