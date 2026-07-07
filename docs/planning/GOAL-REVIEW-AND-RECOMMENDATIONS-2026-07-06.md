# Goal review & recommendations — 2026-07-06

Context: honest assessment against the PROJECT GOAL — an end-to-end agent
process with zero human engagement: script in → render out, no prompts, no
blockers. Written at the author-tier model's preview expiry (handoff doc).

## Verdict

The pipeline is ~90% of the goal; the zero-engagement wrapper is the
unbuilt 10%. Today a script cannot become a render without a human present.
The missing piece is diagnosed with a written remedy
(docs/planning/SEAMLESS-RUN-PLAN.md) but not yet implemented.

## What is real and proven

- Every stage works end to end: approved brief → local LLM translator
  (vetted 4/4, JSON-schema-constrained, byte-identical to the hand-authored
  path) → deterministic resolver → validator → Blender/Godot/USD exporters →
  rendered MP4.
- Proven three times across three asset generations (grey-box → salvaged
  1999 characters → skinned v2 + kit-built set) with ONLY `oeb.config.json`
  changes — the drop-in asset promise held every time.
- Machine-checkable gates at every seam (schemas, 14-code validator,
  deterministic manifests, checksums) — the precondition for removing
  humans from the run.
- An 8-profile qualified worker roster with an escalation ladder that
  caught real failure modes in drills (invented inputs, task-prompt
  override, repair-reality check-gaming).

## What blocks zero engagement today

1. **No single entry point.** Every run to date chained the five tools by
   hand. `tools/run_pipeline.py` is specified in SEAMLESS-RUN-PLAN.md, not
   written.
2. **Permission prompts still fire.** "Always allow" saves exact command
   strings; this pipeline never repeats one. Without the entry point + one
   prefix rule, unattended operation is impossible by definition.
3. **Runs are human-initiated.** True zero engagement needs a scheduled or
   API-driven trigger (AGENT-WORKFLOW-PLAN Phase B) plus a failure policy
   for unattended breakage — the escalation ladder assumes a live
   orchestrator session.
4. **Residual engagement points:** Godot verification must run from the
   orchestrator shell (sandbox hang); asset selection/dressing remains
   human by design (authoring, not the run).

## Recommendations (ordered)

1. **Build `tools/run_pipeline.py`** (SEAMLESS-RUN-PLAN Tier 1): one CLI —
   `--brief` or `--intent` in, MP4 path out — subprocessing resolver →
   validator → exporter(s) → render → encode, with the pipeline's exit-code
   discipline. ~Half a day. This is the highest-leverage single item.
2. **Add the one permission prefix rule** for the entry point (human
   settings action, minutes), plus the Tier-2 hygiene rules for ad-hoc
   work. Then **prove it**: one attended run demonstrating zero prompts,
   recorded in PROJECT-DONE.
3. **Reassign profile authoring before new profiles are needed.** The
   workflow locks profile authoring/revision to the author tier, whose
   preview expires. Options: (a) human + reviewer tier co-author against
   `_TEMPLATE.md` + §4 rules (recommended — the rules and worked examples
   were written to survive exactly this); (b) revise AGENT-WORKFLOW-PLAN
   to delegate authoring to the reviewer tier with human sign-off.
4. **Unattended tier** (after 1–2): a scheduled run (harness cron or the
   Phase B SDK orchestrator) with a written failure policy — on nonzero
   exit, write the bundle to disk and notify; never retry-loop unattended.
5. **Quality-of-scene work, in taste order** (none block the goal): night
   lighting variant for the bar; hair/outfit dressing for the v2
   characters (pack hairstyles attach to `Head` per RIGGING.md); real
   nod/shrug/wipe clips replacing the v0 doubles; JB5K reconstruction
   (plan exists: chunk mining + silhouette tracing); v1 lipsync open
   question when dialogue display matters.
6. **Housekeeping that will bite later if skipped:** backup drive (the
   asset library still has zero redundancy); storage-plan moves now that
   the external drive is accessible; commit cadence stays with the human.

## Continuity note

Nothing in this project depends on any session's memory: trackers
(PROJECT-TODO/DONE), decisions (docs/DECISIONS.md), standards
(docs/RIGGING.md, docs/PROVENANCE.md), the workflow + escalation protocol,
profile changelogs, and the progress docs in docs/planning/ carry the full
state. A fresh orchestrator session at any tier can resume from the
repository alone — that was the design intent, and this review found it
holding.
