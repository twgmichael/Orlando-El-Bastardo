---
title: Prop Builder Plan
created: 2026-08-08T00:00:00-04:00
updated: 2026-08-15T00:00:00-04:00
doc_type: plan
production_area: props
department: art
status: draft
canonical: true
canonical_for: prop_builder_agent
wiki: false
wiki_group: Planning
wiki_order: 81
---
# Prop builder plan — a placeholder for a not-yet-scoped worker agent

Status: **ASPIRATIONAL, not scoped, not built.** Recorded per
docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 5: "prop
builder" is a stated future production-role agent in the same family as
`AGENT-BUS-PLAN.md`'s Producer and `PRODUCTION-DESIGNER-PLAN.md`'s set
designer — named as an example of the roster growing over time, not yet
given the detailed build order, profile file, or qualification drill
`PRODUCTION-DESIGNER-PLAN.md` already has for set designer.

## What's already decided, by extension from the rest of this family

- Coordinates through the same `AGENT-BUS-PLAN.md` substrate (issue
  state machine, structured result comments, `stream:production`
  routing) — no separate coordination mechanism.
- Gets "first level access" to the toolchain, including Studio Chat for
  real generative construction, paired with full audit of every use
  (Studio Chat thread citations in bus completion comments) — same as
  set designer's updated non-goals.
- Bound by the same guardrails as every agent in this family
  (UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 4): no story invention, no
  freehanding a finished-looking hero or production asset. Composition
  and reasonable generative construction within those guardrails, not
  design authority — Producer's own division-of-labor principle
  ("never designs, never commands agents") is the template every worker
  in this family inherits its boundaries from, even though a worker
  (unlike Producer) does execute build work itself.

## What's explicitly not decided yet

Everything `PRODUCTION-DESIGNER-PLAN.md` had to work out for set
designer, prop builder still needs, scoped when it's actually picked up:

- Division of labor specifics — how "prop" work differs from "set"
  work enough to warrant a separate profile rather than folding into
  set designer's own scope (e.g. per-prop vs. whole-set composition,
  smaller/faster turnaround expectations).
- Working loop (requirements-in / survey / compose / look / register /
  deliver, or a different shape).
- Qualification dry run + drill (per AGENT-WORKFLOW-PLAN §7).
- First real assignments.
- `.claude/agents/prop-builder.md` profile authoring (post-author-tier,
  human + reviewer-tier co-authoring against `_TEMPLATE.md`, per
  AGENT-WORKFLOW-PLAN §4).

## Non-goals (inherited provisionally, confirm when scoped)

- No autonomous acquisition of new packs.
- No self-approval: the same "never closes its own ticket" rule set
  designer has.
