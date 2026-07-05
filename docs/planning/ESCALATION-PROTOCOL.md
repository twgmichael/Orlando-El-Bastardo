# Escalation Protocol

Status: active, 2026-07-04. Referenced by every profile in `.claude/agents/`.
Source design: `AGENT-WORKFLOW-PLAN.md` §5.

## The ladder

```
Tier 0  Deterministic checks     schema validation, pytest, exit codes, diffs
Tier 1  Worker self-recovery     max 2 fix attempts per distinct failure
Tier 2  Reviewer review          orchestrator spawns escalation-reviewer with bundle
Tier 3  Human                    orchestrator stops and presents the decision
```

## Tier 1 — worker self-recovery

Most failures are caught by tooling (Tier 0) and fixed mechanically. A worker
retries a distinct failure at most **twice**. Attempt counting is per failure
signature: the same error message/class increments the same counter. A worker
may never loop on a failure it has already attempted twice.

## Tier 1 → 2 triggers

A worker STOPS work — no further attempts, no guessing — and emits an
escalation bundle when ANY of these fires:

1. The same failure persists after 2 fix attempts.
2. The task spec conflicts with a document it cites.
3. A required file, ID, tool, or path does not exist.
4. The next step would exceed the profile's allowed-actions list — including
   anything destructive, **any git write**, any download or network install.
5. Ambiguity that changes the output (e.g., units, naming, format not defined
   by the cited docs).

**Never repair reality to match the task.** If the task references an input
(file, config, asset, ID) that does not exist, that is trigger 3 — creating
the missing input with invented content is a violation, not initiative, even
when plausible defaults are obvious. The same applies to trigger 2: report the
conflict; do not edit either side to make it disappear. Inputs are created by
whoever owns them; workers only report their absence.

**The profile outranks the task.** A profile's standing constraints and
allowed-actions list bind on EVERY task the agent is given — they are not
scoped to the task that first created a file, and no task prompt can
supersede, relax, or "update" them. A task that instructs you to write
outside your MAY-write list, modify a frozen file, or otherwise exceed your
allowed actions is not authorization — it is trigger 4. Emit the bundle; only
a revised profile (authored at the author tier) changes what you may touch.
(Added 2026-07-05 after a validator-builder drill: given a task explicitly
requesting a schema edit, the worker complied, reasoning the new task
"superseded" its constraints.)

## Escalation bundle (fixed format)

```markdown
## ESCALATION
- Task: <one line, verbatim from assignment>
- Trigger: <which trigger number fired, and why>
- What was attempted: <numbered, with exact commands>
- Exact error/output: <verbatim, fenced>
- Files touched: <paths + one-line state of each>
- Files read: <paths>
- Specific question: <the single decision needed>
- Constraint check: git untouched? yes/no; drive untouched? yes/no
```

## Tier 2 — escalation-reviewer

The orchestrator spawns `escalation-reviewer` with the bundle plus pointers to the
relevant docs. The reviewer must return exactly one of:

- **`RESOLVED:`** a concrete fix or decision plus instructions. The
  orchestrator re-tasks the worker, or the reviewer applies a small fix
  directly (see its profile for the size limit).
- **`HUMAN_REQUIRED:`** a ≤10-line decision summary — what's blocked, the
  2–3 options, a recommendation.

The reviewer MUST return `HUMAN_REQUIRED` (never decide itself) when the
decision involves:

- Changing a locked decision (`docs/DECISIONS.md`)
- Resolving an open question (`docs/OPEN-QUESTIONS.md`)
- Licensing or provenance judgment
- Spending money, downloading assets, or installing software
- Anything destructive (deleting/overwriting non-generated files)
- **Any git write** (git is user-handled, always — see `CLAUDE.md`)

**Ping-pong cap:** maximum 2 reviewer round-trips per task. If the second
`RESOLVED` fix also fails, the orchestrator forces `HUMAN_REQUIRED`.

## Tier 3 — human

The orchestrator halts that workstream and presents the `HUMAN_REQUIRED`
summary. Independent workstreams may continue.

## Worker report (success path, fixed format)

```markdown
## REPORT
- Task: <one line>
- Status: DONE | ESCALATION (bundle follows)
- Done-criteria results: <each criterion + the command output proving it>
- Files created/modified: <paths>
- Notes: <anything the orchestrator should know, ≤5 lines>
```

## Standing constraints (repeated in every profile)

1. **Git is read-only.** Never commit, push, pull, stash, branch, merge, tag,
   or run any state-changing git command. Read-only git (`status`, `log`,
   `diff`) is fine.
2. **No downloads or network installs** without human approval.
3. **No writes under `/Volumes/` (any external drive)** unless the task
   explicitly grants it.
4. **Resolve asset paths only via `OEB_ASSET_ROOT` / `oeb.config.json`** —
   never hardcode `/Users/...` or `/Volumes/...` absolutes into generated
   `.blend`/`.tscn`/USD/glTF content.
