# Agent bus plan — GitHub Issues/Project as the crew's coordination substrate

Recorded 2026-07-11 (designed with the project owner). Status: **PLANNED,
not built.** This plan AMENDS the orchestration story in
AGENT-WORKFLOW-PLAN: the reviewer-tier orchestrator and worker agents
currently coordinate inside single sessions (context handoffs,
session-bound escalation bundles); the bus gives that same protocol a
durable, queryable substrate so agents can be assigned tasks, work
independently across sessions and days, and report done through the
middle — with the producer and orchestrator tracking progress from it.

## Audience (decided 2026-07-11)

The Issues and the Project board are FOR THE AGENTS — Claude-tier
workers, the local LLM crew, the orchestrator, the producer. The human
is not the operator of this system: humans appear only at policy edges
(qualifying new agent types, acceptance gates, budget/dispatch
decisions) and can read any view at leisure. Human-facing narrative
stays in PROJECT-TODO/DONE and docs/ — those do not migrate.

## Issue format: human-readable top, machine-canonical payload

Each task issue carries BOTH (decided 2026-07-11):

1. **A human-readable description on top** — a short templated prose
   paragraph: what, why, which scene/episode, acceptance criteria in a
   sentence. Sensible to any human who opens the issue.
2. **A fenced structured payload below** (JSON) — the canonical task
   spec: kind, inputs, acceptance criteria, artifact contract, routing.

Discipline (the one real cost — same rule as the wiki mirror): the
structured block is truth; the prose is a GENERATED view, templated
from the payload at filing time by the bus helper, never
hand-maintained. Task changes go through the helper, which regenerates
both. Hand-edited prose is cosmetic; agents never parse it. This is
`tickets.py`'s proven .json + .md pattern applied to issues — zero
recurring human effort, ~50–150 tokens per issue read, and for
frontier-tier agents the prose is signal, not overhead (intent context
improves judgment). Only the local-LLM wrapper strictly needs the
fenced block.

Agent comments are structured result blocks with a mandatory one-line
`summary` field — threads stay human-skimmable for free.

## The protocol

- **State machine** (single Project field):
  `queued → claimed → in-progress → needs-verify → verified → done`,
  plus `blocked` and `escalated`.
- **Claiming**: an agent claims by setting the `agent:` field and
  posting a claim comment — the mutual-exclusion mechanism so
  independent agents don't collide.
- **Completion**: a structured result comment — artifacts produced,
  commits referenced, verification evidence, deviations, open
  questions — then state → `needs-verify`.
- **Routing labels/fields**: `stream:production` | `stream:tooling`,
  `kind:*` (location/prop/clip/audio/…), `area:*`
  (resolver/exporter/producer/…), `agent:*`, `episode:*`.
- **Nothing reaches `done` without verifier evidence** — the same
  discipline the pipeline already enforces elsewhere.

## One shared helper: `tools/agent_bus.py`

Wraps `gh` with exactly the protocol verbs — `file`, `claim`, `report`,
`block`, `query` — plus the prose-from-payload template. Every agent
speaks through it identically; a new agent type is "plugged in" the
moment it can call these verbs. That is the flexibility requirement:
the protocol is the contract, not the agent's species.

## Roles on the bus

- **Producer** (local LLM + deterministic driver): FILES production
  issues from NEEDED tickets; its production reports cite live issue
  states. It still never designs and never commands agents.
- **Orchestrator** (reviewer tier): triages `queued`, assigns, watches
  `blocked`/`escalated`, requests verification, closes on `verified` —
  ESCALATION-PROTOCOL on a durable substrate.
- **Workers** (Claude-tier agents — e.g. the planned production
  designer — and local-LLM workers behind thin deterministic wrappers;
  the local model never touches `gh` itself): poll for their
  assignments on wake, work independently, report through the bus. The
  issue IS the context — no session handoffs.
- **Verifier**: consumes `needs-verify`, posts pass/fail evidence.
- **Human**: policy edges only.

## Two streams, one Project

- `stream:production` — asset work, filed by the producer (labels from
  ticket kinds, milestone per episode). First customers: the pilot
  backlog and the production-designer assignments
  (PRODUCTION-DESIGNER-PLAN).
- `stream:tooling` — pipeline development (Godot/USD move cues, night
  lighting, camera offsets…), filed by orchestrator/human as items
  become ACTIVE work ("issue-ize on activation" — no bulk backlog
  import; PROJECT-TODO remains the narrative roadmap).

One Project, saved views per audience: asset board grouped by kind,
tooling table grouped by area, roadmap by episode. Shared custom
fields: `status`, `agent`, `episode`, `verified`.

## Constraints designed around

- **Identity**: all agents share one GitHub token — the `agent:` field
  is the real identity layer, not GitHub assignees. Per-agent GitHub
  App identities are a later upgrade if attribution ever matters.
- **Poll, not push**: agents check the bus when they wake; fully
  autonomous cycles eventually want a scheduled trigger (a later
  decision — all runs remain human-initiated during development, per
  DECISIONS 2026-07-07).
- **`gh` scope**: Projects v2 needs the `project` scope added to the
  existing auth once (human step).

## Build checklist (when actioned)

- [ ] Human: create the GitHub Project (one), add `project` scope to
      `gh` auth
- [ ] `tools/agent_bus.py` (verbs + payload schema + prose template)
- [ ] Label/field taxonomy created in the repo/Project
- [ ] `tickets.py` extension: NEEDED tickets also file
      `stream:production` issues (ticket files remain canonical)
- [ ] Orchestrator + worker profile amendments: bus verbs in standing
      instructions
- [ ] Pointer added to AGENT-WORKFLOW-PLAN's orchestration section
      (this plan amends it)
- [ ] First live run: file the pilot-backlog issues, dispatch one to
      the production designer once that profile is qualified
      (PRODUCTION-DESIGNER-PLAN)
