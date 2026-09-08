---
title: LLM Competence Benchmark Plan
created: 2026-08-17T00:00:00-04:00
updated: 2026-08-17T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: draft
canonical: true
canonical_for: llm_competence_benchmark
wiki: true
wiki_group: Planning
wiki_order: 204
---
# LLM Competence Benchmark Plan

Recorded 2026-08-17. Status: **doc gap closed — this plan now owns the
benchmark-grading system referenced from
`docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md` (open question 2) and
`docs/planning/BUILD-SEQUENCE-PLAN.md` (Phase 2). Nothing built yet.**

## Why this exists, and why it's a separate doc

Two docs already reference "a benchmark system" that grades local vs.
cloud LLM competence per task/confidence level (see
`docs/planning/HARNESS-RESOURCE-MODEL-PLAN.md`'s "Uniform job envelope
and confidence levels" section), but neither owned it. Investigating the
doc gap found `docs/planning/benchmarks/results.jsonl` **already exists**
— it's the real output of `tools/studio_chat_benchmark.py`, owned by
`docs/planning/benchmarks/STUDIO-CHAT-VISUAL-VARIETY-BENCHMARK.md` (Phase
4 of `docs/planning/REVIEW-AUDIT.md` section 9). That benchmark grades
something unrelated — Studio Chat's render *output variety* (primitive
count/mix), not LLM *task competence*. Reusing that path or that doc for
this work would conflate two unrelated concerns under one name/schema, so
this is a dedicated doc with its own results file:
`docs/planning/benchmarks/llm_competence_results.jsonl`.

## What this benchmarks

Ongoing, evidence-driven grading of each LLM resource (local Qwen2.5-3B,
Claude, OpenAI) against each task type and confidence level (see
`HARNESS-RESOURCE-MODEL-PLAN.md`'s confidence-level spectrum, level 0
through level 5) — not a static preference table, the same
"let evidence decide, don't guess" position already established by this
session's local-vs-Haiku discussion. This is the concrete mechanism for
`HARNESS-RESOURCE-MODEL-PLAN.md` open question 2 ("who defines 'ranked
competence,' and how").

**Named first test case** (from `PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s
"Open concern: is a paid call a hard default for the full-script grouping
pass?"): whether a local-only, chunked/windowed full-script grouping pass
can substitute for one large cloud call at acceptable quality. The
Opus-tier full-script call (`PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s
"Leveraging the cloud call as a dual-purpose investment") is planned as a
calibration fixture for exactly this.

## Not built

Nothing in this document has been implemented. No results file exists at
`docs/planning/benchmarks/llm_competence_results.jsonl`. No benchmark
harness, prompt set, or grading rubric exists for LLM task competence
(distinct from the existing, unrelated Studio Chat variety benchmark).
Scheduler logic that would consume these grades is Phase 2 work in
`docs/planning/BUILD-SEQUENCE-PLAN.md`, gated behind Phase 0.
