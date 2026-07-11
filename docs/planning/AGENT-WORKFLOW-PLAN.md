# Agentic Workflow Plan — Orchestrator + Tiered Model Delegation

Status: in progress, 2026-07-04. Steps 1–3 of §8 DONE: scaffolded, and all
three pilots QUALIFIED per §7 (lint + dry runs + escalation drills; 6 profile
bugs found and fixed — see profile changelogs). The qualification dry runs
produced the real Phase 2A deliverables (`tools/make_placeholders.py` +
verified GLB/USDC exports). Next: step 4 — run remaining Phase 2A/Phase 1 work
through the workflow. Note: profiles are routable as named subagents only in
sessions started after they were created (harness loads `.claude/agents/` at
session start).

LLMs are referred to by competence tier throughout: **author** (most capable;
writes profiles, designs, arbitrates), **reviewer** (escalations), **worker**
(execution), **utility** (trivial checks, later). The concrete model behind
each tier is deployment configuration, recorded locally in
`docs/local/MODEL-TIERS.md` (not committed).

Goal: run OEB build work through an orchestrator and a roster of worker agents
whose profiles are **written by the author tier** but **executed by the
cheaper worker tier**, escalating to the **reviewer tier** only when a genuine
issue arises, and to a **human** only when the reviewer can't resolve it.

---

## 1. Why this project is a good fit

The OEB pipeline is deliberately deterministic: JSON Schemas, a validation CLI,
headless Blender scripts, exporters with fixture tests. That gives us the one
thing delegation to smaller models depends on — **machine-checkable success
criteria**. A worker-tier agent doesn't need judgment to know whether it
succeeded; `jsonschema` validation, exit codes, and round-trip diffs tell it.
Published agent-design guidance says the same thing from the other side:
agents are viable when errors can be caught and recovered from cheaply. Ours
can — by tooling, not by intelligence.

The corollary sets the boundary: **judgment-heavy work stays at the top tier**.
Designing the schema spine (Phase 1 core decisions), resolving the open
questions in `docs/OPEN-QUESTIONS.md`, and writing/revising agent profiles are
author/reviewer-tier work. Executing against a settled design is worker-tier
work.

## 2. Model tiers and roles

| Tier | Role |
|---|---|
| Author | Writes and revises agent profiles; designs the workflow; arbitrates when the reviewer punts back |
| Reviewer | Reviews escalation bundles; fixes or decides; declares `HUMAN_REQUIRED` |
| Worker | Executes profiles: coding, bpy scripts, exporters, fixtures, verification runs |
| Utility (optional) | Later, for mechanical checks (lint runs, file-existence sweeps) — not in v1 |

Concrete model assignments, IDs, per-token pricing, and effort settings:
`docs/local/MODEL-TIERS.md` (local only). Economics summary: workers generate
~90% of tokens and the worker tier costs roughly half the reviewer tier per
token, so steady-state cost roughly halves versus running everything at the
reviewer tier — and escalations are rare by design.

## 3. Platform choice

**Phase A (now): harness-native custom subagents.** Worker profiles live as
markdown files in `.claude/agents/` with frontmatter (`name`, `description`,
the `model:` tier keyword, allowed `tools`). The interactive harness session
is the orchestrator: it decomposes work, spawns workers via the Agent tool,
receives their final reports, and routes escalations. This needs zero new
infrastructure, works with the tools already in play (Bash, file tools, the
venv, headless Blender), and keeps the human in the loop at the terminal.

**Phase B (later, if needed): Python orchestrator on the vendor API.** If we
want unattended runs (e.g., overnight regeneration of all exports), port the
same profiles to a small Python orchestrator using the vendor SDK —
worker-tier calls with the tool runner, reviewer-tier escalation calls on
demand (call details in `docs/local/MODEL-TIERS.md`). The profiles are the
portable asset; the orchestrator is thin. Do not build this until Phase A
shows the profiles are stable.

**Rejected: managed cloud agents.** Tool execution happens in a cloud
container, but our pipeline depends on local binaries (Blender 5.1.2, Godot
4.7, the external asset drive). Self-hosted sandboxes exist but are far more
machinery than a one-machine pipeline justifies.

Two structural properties of harness subagents work in our favor:

- **Workers cannot spawn agents.** All routing flows through the orchestrator —
  which is exactly the control point the escalation ladder needs.
- **Stable profiles cache well.** A frozen profile (system prompt) with the
  volatile task in the invocation prompt is the cache-friendly shape; never
  interpolate timestamps or per-run data into profile text.

## 4. The core problem: profiles that survive the handoff

A profile the author tier can execute is not automatically a profile the
worker tier can execute. The failure mode is implicit judgment: "choose a
sensible naming scheme," "handle edge cases appropriately," "use your
judgment." The author model fills those gaps; a worker model fills them
differently every run, or stalls. The authoring rules:

1. **One job per agent.** Narrow mission, stated in one sentence. If a profile
   needs the word "and" in its mission, split it.
2. **Procedure, not intent.** Numbered steps with exact commands, exact paths,
   exact expected outputs. "Run `.venv/bin/python -m pytest tests/ -x`; a zero
   exit code is required before proceeding" — not "make sure tests pass."
3. **Machine-checkable done criteria.** Every profile ends with a DONE checklist
   the worker must verify by running something — schema validation, exporter
   round-trip, file-exists checks against the canonical IDs in
   `docs/BAR-SCENE.md`. If a criterion can't be checked by a command, it
   doesn't belong in a worker-tier profile.
4. **Bounded discretion.** Enumerate what the agent MAY do (files it may write,
   commands it may run) and state that everything else is an escalation, not an
   improvisation. Include the standing constraints in every profile:
   - **Git is read-only. Never commit, push, pull, stash, branch, or merge.**
   - No downloads or network installs without human approval.
   - No writes under `/Volumes/` (any external drive) unless the task explicitly grants it.
   - Resolve asset paths only via `OEB_ASSET_ROOT` / `oeb.config.json`, never
     hardcoded absolutes.
5. **Prescriptive tool triggers.** Say *when* to use a tool, not just that it
   exists ("Before editing any schema, read `docs/SCHEMA.md`"; "After writing
   any `.py` that imports `bpy`, verify it with
   `blender --background --python <file>` and check the exit code").
   Current models under-reach for tools unless the trigger condition is explicit.
6. **Self-contained context.** The profile names every document the worker needs
   (`docs/SCHEMA.md`, `docs/BAR-SCENE.md`, the schema files) and instructs it to
   read them first. Assume zero conversation history.
7. **Worked examples.** One small input→output example per profile (e.g., a
   correct cue object, a correct placeholder naming table). Few-shot anchors do
   more for a smaller model than paragraphs of description.
8. **Report format is specified.** The worker's final message follows a fixed
   template (below), so the orchestrator can parse success vs. escalation
   without interpretation.

## 5. The escalation ladder

```
Tier 0  Deterministic checks     schema validation, pytest, exit codes, diffs
Tier 1  Worker self-recovery     max 2 fix attempts per distinct failure
Tier 2  Reviewer review          orchestrator spawns escalation-reviewer with bundle
Tier 3  Human                    orchestrator stops and presents the decision
```

**Tier 0 → 1.** Most failures are caught by tooling and fixed mechanically.
The worker retries a distinct failure at most **twice**. Attempt counting is per
failure signature (same error → same counter), so it can't loop.

**Tier 1 → 2 triggers (objective, listed in every profile):**
- Same failure after 2 fix attempts.
- The task spec conflicts with a document it cites (e.g., TODO says one mark
  name, BAR-SCENE.md says another).
- A required file, ID, tool, or path doesn't exist.
- The next step would exceed the allowed-actions list (including anything
  destructive, any git write, any download).
- Ambiguity that changes the output ("schema doesn't say if `start_time` is
  seconds or frames").

On any trigger, the worker STOPS work and emits an **escalation bundle** — it
does not keep trying, and it does not guess.

**Escalation bundle format** (fixed template so the reviewer starts warm, not
cold):

```markdown
## ESCALATION
- Task: <one line, verbatim from assignment>
- Trigger: <which trigger fired>
- What was attempted: <numbered, with exact commands>
- Exact error/output: <verbatim, fenced>
- Files touched: <paths + one-line state of each>
- Files read: <paths>
- Specific question: <the single decision needed>
- Constraint check: git untouched? yes/no; drive untouched? yes/no
```

**Tier 2.** The orchestrator spawns `escalation-reviewer` (a reviewer-tier
profile) with the bundle plus pointers to the relevant docs. The reviewer must
return exactly one of:
- `RESOLVED:` a concrete fix or decision + instructions; orchestrator re-tasks
  the worker (or lets the reviewer apply a small fix directly if it's cheaper).
- `HUMAN_REQUIRED:` a ≤10-line decision summary: what's blocked, the 2–3
  options, its recommendation. The reviewer escalates to human when: the
  decision is a locked-decision change (`docs/DECISIONS.md`), an open question
  (`docs/OPEN-QUESTIONS.md`), a licensing/provenance judgment, spending or
  downloading, anything destructive, or any git write.

**Tier 3.** The orchestrator halts that workstream and presents the
`HUMAN_REQUIRED` summary. Other independent workstreams may continue.

**Worker report template** (success path):

```markdown
## REPORT
- Task: <one line>
- Status: DONE | ESCALATION (bundle follows)
- Done-criteria results: <each criterion + the command output proving it>
- Files created/modified: <paths>
- Notes: <anything the orchestrator should know, ≤5 lines>
```

## 6. Proposed roster (start small)

Pilot with two workers plus the reviewer; expand only after the pilots hold up.

| Agent | Tier | Phase | Mission |
|---|---|---|---|
| `placeholder-builder` | worker | 2A | Write/extend `make_placeholders.py` (headless bpy): grey-box set, props, 2 rigged characters, marks, cameras, keyed actions — named exactly to `docs/BAR-SCENE.md` IDs; export glTF+USD; verify round-trip |
| `pipeline-verifier` | worker | 2A–5 | Run the validation CLI, schema checks, and glTF/USD round-trip checks; diff against expectations; produce a pass/fail report. Never fixes — only verifies and reports (keeps generation and verification in separate contexts) |
| `escalation-reviewer` | reviewer | all | Consume escalation bundles; RESOLVED or HUMAN_REQUIRED |

Second wave (after pilot): `schema-fixture-writer` (author the bar-scene
SceneSpec fixture against the finished schemas), `exporter-dev` (one profile,
parameterized by target: Blender / Godot / USD), `doc-scribe` (move TODO items
to DONE with dates, record provenance entries).

Deliberately **not** delegated: Phase 1 schema design itself, open-question
resolution, profile authoring, anything touching git or money. Those stay with
the author tier/the human at the terminal.

## 7. Proving a profile is worker-ready

The author tier writing "clear" instructions isn't evidence; the test is
empirical. Before a profile enters the roster:

1. **Lint pass** (checklist review of the profile text): no judgment words
   ("appropriate", "sensible", "as needed"), every step has a verification,
   every path exists, done-criteria are all commands, escalation triggers
   present, standing constraints present, report template present.
2. **Dry run:** spawn the agent on the worker tier with a real, small task.
   It must reach DONE with zero escalations and zero constraint violations.
3. **Escalation drill:** give it a task with a planted defect (a missing file,
   or a spec contradiction). It must emit a well-formed bundle within its
   2-attempt budget — not flail, not guess, not "fix" the wrong thing.
4. Failures in 2–3 are **profile bugs**: the author tier revises the profile,
   not the worker. Log each revision cause in the profile's changelog block so
   the authoring rules improve over time.

## 8. Implementation steps

1. **Scaffold** — create `.claude/agents/` and a `_TEMPLATE.md` encoding §4's
   structure (frontmatter; Mission / Required reading / Allowed actions /
   Procedure / Done criteria / Escalation triggers / Bundle + Report templates /
   Worked example / Changelog). Add `docs/planning/ESCALATION-PROTOCOL.md`
   capturing §5 verbatim so profiles can reference it instead of restating it.
2. **Author pilots** (author tier): `placeholder-builder`, `pipeline-verifier`,
   `escalation-reviewer`.
3. **Qualify pilots** per §7 against real Phase 2A tasks (the placeholder
   script is the ideal first dry run — self-contained, fully checkable).
4. **Run Phase 2A through the workflow.** Orchestrator (main session)
   decomposes, workers execute, verifier gates. Human reviews only DONE
   reports and Tier-3 summaries.
5. **Expand the roster** for Phase 3–4 (resolver, validator, exporters) once
   the pilot loop is stable. Track escalation rate per profile; a profile that
   escalates >~20% of runs needs revision, not a bigger model.
6. **(Optional, later)** Port to a Python/SDK orchestrator for unattended runs
   if a need appears.

## 9. Risks and mitigations

- **Workers silently violating constraints** (the expensive failure) → standing
  constraints repeated in every profile, verifier agent checks `git status`
  porcelain output as part of every run, and workers get no broader tool
  access than their profile needs.
- **Escalation ping-pong** (reviewer fix fails, worker re-escalates, repeat) →
  cap at 2 reviewer round-trips per task, then force `HUMAN_REQUIRED`.
- **Profile drift vs. docs** — profiles cite documents by path; when SCHEMA.md
  or BAR-SCENE.md changes, the changing session must grep `.claude/agents/`
  for references and flag stale profiles.
- **Cost surprise from retries** — the 2-attempt and 2-round-trip caps bound
  the worst case; the verifier's pass/fail reports make waste visible.

## 10. Orchestrator model (DECIDED 2026-07-04)

The author tier orchestrates while profiles are being authored and qualified
(steps 1–3). Once the pilot roster is qualified, day-to-day orchestration
drops to the reviewer tier. The author tier is recalled only for profile
revisions (and new profile authoring).

AMENDED 2026-07-07 (author tier no longer available): profile authoring and
revision is now **human + reviewer-tier co-authoring** against
`.claude/agents/_TEMPLATE.md` and the §4 rules. The qualification bar (§7 —
lint, dry run, escalation drill) is unchanged and non-negotiable.
