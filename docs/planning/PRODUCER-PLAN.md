# The Producer — plan for script-to-render oversight (provided assets only)

Recorded 2026-07-07 from session feedback + clarification. Status: PLANNED.

## Terminology

The local LLM is henceforth **the producer** — in the film sense: the role
that manages logistics and shepherds a script through the machinery to a
finished render. It oversees; it does not create.

## The goal, as clarified

Give the producer a script; receive fully rendered scenes — **using the
provided asset library only.**

- The producer works exclusively with what exists in `oeb.config.json`, the
  resolver map, the camera grammar, and the clip library.
- If a script names anything not in the library — a location, character,
  prop, or action the vocabulary doesn't cover — the producer's job is to
  stop that scene and emit an **obvious, structured MISSING/NEEDED
  response**, never to improvise, substitute, or build.
- Building new assets and capabilities (everything this project did by hand
  to get here: hero, bartender, the bar set, clips) is explicitly OUT of the
  producer's scope. That remains build-time work for the human + agent crew,
  one capability at a time. (An earlier draft of this plan included
  producer-driven "capability menus" — cut by this clarification; noted only
  as a possible far-future extension.)

## Design judgment (from the session's evidence)

Don't build a smart producer — build a studio whose paperwork is so
structured a clerk can run it. The vetted 3B model is reliable exactly when
rails force correctness (constrained decoding, required fields — see the
`beat_orders` false-pass lesson) and unreliable when asked for judgment. So:

- The producer is a **deterministic state machine** (`tools/producer.py`,
  plain code) that consults the LLM only at labeled decision points, each
  with a constrained output schema and its own vetting matrix — the same
  standard the translator passed.
- The producer's authority is bounded like a worker profile's: extraction
  and template-filling only; anything off-script becomes a NEEDED report
  and a halt. "The profile outranks the task" applies to the LLM itself.

## What already exists that this builds on

- **Gap detection is done and deterministic:** the resolver's
  `RESOLVE-ERROR E_UNMAPPED_*` codes and the validator's 14-code report ARE
  the missing-asset sensors. The producer only needs them surfaced as
  structured output, not stderr prose.
- The single front door (`tools/run_pipeline.py`, proven unattended,
  zero prompts).
- The qualified worker roster + escalation protocol for anything the
  producer tickets out.

## The plan

### P1 — Production reports (~1 day) — TICKETING BUILT 2026-07-07

Ticketing shipped: `tools/tickets.py` (failure classification: only
missing-library error classes become NEEDED tickets; bugs stay FAILED) +
`run_pipeline.py --episode <id>` integration, exit code 4 = BLOCKED with
ticket written. Verified: delivered path, blocked path
(`NEEDED-*.json` + `.md` under `out/production/<episode>/tickets/`,
`report.json` index with `open_tickets`), and the validator-side
classifier against a real broken report. Remaining in P1: render QA gates,
run-time translation fidelity gate (review flag 2), name-extraction polish
for validator messages.

Every stage emits machine-readable JSON status (the validator already
does). `run_pipeline.py` gains a run manifest. The centerpiece: the
**NEEDED report** — when resolution/validation fails on missing vocabulary
or assets, the scene halts with e.g.:

```json
{
  "scene_id": "sc_rooftop_007",
  "status": "NEEDS_ASSETS",
  "missing": [
    { "kind": "location", "tag": "rooftop_garden" },
    { "kind": "clip", "id": "bartender_turn_toward" }
  ],
  "source": "resolver E_UNMAPPED_LOCATION; validator unknown_clip"
}
```

Plus cheap render QA gates (non-black frame sampling, duration vs. spec,
cut count vs. shots) so "rendered" is machine-verified, not assumed.

### P2 — The script desk (~1 day)

Scripts today are single-scene briefs. Needed: script → scene-brief
chunking (the producer's first LLM decision point — extraction with
constrained decoding, never writing), per-scene runs, episode assembly
(concat + slate), and a config/world snapshot per episode for continuity.

### P3 — The producer driver (~2 days)

`tools/producer.py`: script in → chunk → per scene: translate → run →
on success: QA + collect; on gap: NEEDED report, halt that scene, continue
the others → episode out with a final production report (delivered scenes,
needed scenes, tickets). Unattended failure policy: one retry per distinct
failure, then halt with the bundle on disk — never loop.

### P4 — Producer qualification (~1 day)

The producer earns its title the way every agent here did:

- **Dry run:** a two-scene script fully inside the library → both scenes
  rendered unattended.
- **Missing-asset drill:** a script naming an absent location/prop/action →
  a clean NEEDED report and a halt for that scene, other scenes unaffected,
  zero improvisation, zero writes outside its outputs. (The
  escalation-drill philosophy, applied to the producer.)
- Per-decision-point vetting matrices, temp-0 gate + sampled configs,
  fidelity judged on resolved output — all per the established harness.

## Division of labor

- **Producer (local LLM):** script chunking, brief translation, menu-free
  template filling. Nothing else.
- **Deterministic code:** the loop, the reports, the gates, the assembly.
- **Human + reviewer-tier sessions + worker roster:** building the driver
  and reports (P1–P3), and ALL new assets/capabilities the NEEDED reports
  ask for — then the library grows and the same scripts pass.

## Acceptance (the maximal goal, testably)

A provided script whose scenes use only library assets renders end-to-end
with no human involvement; the same script with one out-of-library scene
delivers every other scene AND a NEEDED report a human can act on at a
glance. When both hold, the producer is real.
