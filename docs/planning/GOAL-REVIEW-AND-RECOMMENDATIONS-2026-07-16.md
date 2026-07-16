---
title: Goal Review (2026-07-16)
created: 2026-07-16T11:46:27-04:00
updated: 2026-07-16T11:46:27-04:00
doc_type: progress_report
production_area: operations
department: production
status: active
canonical: false
wiki: true
wiki_group: Journal
wiki_page: Goal-Review-2026-07-16
wiki_order: 20
---
# Goal review & recommendations — 2026-07-16

Context: reassessment after the July 6 seamless-run proof, the July 11
screenplay-to-episode production run, the July 14 studio harness deployment,
and the July 16 documentation taxonomy and wiki-routing pass.

## Verdict

The original zero-engagement goal has been met. A brief, intent, or screenplay
can now enter a deterministic pipeline and produce validated renders and
production tickets without interactive prompting.

The active goal is now broader: a conversational 3D animation studio. A
creative prompt should become a structured job, preserve meaningful details,
resolve or generate appropriate assets, produce a visible review artifact, and
return enough trace data for a human or assistant to understand what happened.

The project is past proof-of-pipeline and into proof-of-studio.

## What is real and proven

- `tools/run_pipeline.py` proved the seamless run on 2026-07-06: brief or
  intent in, resolver, validator, Blender/Godot/USD export, render, MP4, exit
  0, zero permission prompts.
- `tools/producer.py` proved the production run on 2026-07-11: screenplay in,
  rendered pilot teaser out, with NEEDED tickets for missing assets, dressing,
  audio, and stand-ins.
- Motion grammar v1 reached the production spine: arrivals, exits, move cues,
  medium cameras, and NLA crossfades are now part of the delivered loop.
- The studio harness is live as of 2026-07-14: FastAPI control plane,
  PostgreSQL, worker registration, Blender CLI dispatch, output-root routing,
  and a macOS menu bar worker.
- The first conversation-to-build path exists through `tools/studio_chat.py`
  and the studio chat endpoint plan. Local LLM output is usable but lossy, so
  structured scene-plan details and deterministic enrichment are now part of
  the intended contract.
- Documentation publishing has moved to metadata-driven wiki routing. Public
  docs carry front matter taxonomy, and `docs/local/**` stays excluded even if
  tagged.

## What needs realignment now

1. **Promote the current goal language.** The public project narrative should
   consistently describe the goal as a conversational 3D animation studio, not
   only a zero-prompt batch pipeline.
2. **Finish the studio chat endpoint.** The CLI proof should become a hosted,
   interface-agnostic endpoint that accepts creative prompts and returns job
   status, review links, trace links, and preserved prompt-loop data.
3. **Keep structured detail first-class.** Scene-plan prompts, repair prompts,
   primitive-builder input, debug traces, and schema documentation should all
   preserve details such as shape, required features, source phrases,
   materials, style details, and parts.
4. **Complete orientation enforcement.** The project has adopted `+X` front,
   `-X` rear/back, `-Y` left, `+Y` right, `+Z` up, and `-Z` down. Keep builder
   placement, camera metadata, manifest metadata, prompts, and tests aligned.
5. **Build only the registry needed for conversation grounding.** The asset
   registry should stay lean: canonical ID, kind, tags, availability, and seed
   data from `oeb.config.json`.
6. **Move public docs away from local development debris.** Public-facing
   docs should not depend on `.claude`, exact local paths, local device names,
   or personal settings files.
7. **Close the remaining production gaps.** Bar furniture, night lighting,
   pilot dressing/audio tickets, Godot/USD move-cue support, agent bus work,
   and the additional worker install remain useful next targets.

## Recommendations

1. Make the July 16 goal statement the current public frame: creative sentence
   to visible shot, with deterministic validation and traceability.
2. Treat `STUDIO-CHAT-ENDPOINT-PLAN.md`, `SCENE-GRAPH-PRIMITIVE-BUILDER-PLAN.md`,
   `SCHEMA.md`, and the orientation standard as the immediate documentation
   alignment set.
3. Keep `PROJECT-TODO.md` as the active backlog and `PROJECT-DONE.md` as the
   evidence ledger; do not make archived reviews carry current status.
4. Use metadata-driven wiki routing as the documentation publishing contract.
   Add new public pages by front matter, not by script tables.
5. Before broad publication, continue removing local-only identity, path, and
   device details from public docs unless they are intentionally part of
   copyright, provenance, or project ownership.

## Continuity note

The repository now carries the project state without relying on session memory:
roadmap, done ledger, schema docs, orientation standard, wiki routing taxonomy,
studio chat plan, primitive-builder plan, and harness plans. The next session
should be able to resume from those documents and ask a narrower question:
what shortens the distance from a creative sentence to a visible, reviewable
shot?
