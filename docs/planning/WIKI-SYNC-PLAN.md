# Wiki sync plan — docs → GitHub wiki, automated on push

Recorded 2026-07-11 (decided with the project owner). The mirror itself is
BUILT and live; the automation tier is **PLANNED, not built**.

## What exists (built 2026-07-11)

`tools/sync_wiki.py` — one-way docs → wiki mirror. The repo is canonical;
the wiki is a generated artifact, never hand-edited.

- 20 pages: `docs/` + `docs/planning/` + Roadmap (PROJECT-TODO.md) +
  Journal-Log (PROJECT-DONE.md), mapped by the script's `PAGES` table
  (adding a doc = one table line).
- Per-page banner: source path + commit hash + "the repo is canonical."
- Link rewriting: doc-to-doc links become wiki page links (plain markdown
  syntax — GitHub resolves it and it avoids `[[pipe]]` order ambiguity);
  links to other repo files become absolute `blob/main` URLs.
- Generated `_Sidebar` (grouped: Design / Standards / Planning / Journal /
  Tracking) and `_Footer`; orphaned wiki pages pruned — the script owns
  the whole page set.
- Hard exclusions: `docs/local/**` (refused outright), CLAUDE.md,
  LICENSE.md, the root README.
- Verified live 2026-07-11: all pages HTTP 200; Home, sidebar, and banner
  links resolve from every page URL.

## The automation decision: GitHub Action on push to main

Manual cadence (run script, push wiki clone) works but relies on a human
habit, and the wiki silently lags when the habit slips. Decided: a
workflow that makes the mirror a server-side consequence of pushing docs.

Design:

- **Trigger**: `push` to `main`, with a `paths` filter — `docs/**`,
  `PROJECT-TODO.md`, `PROJECT-DONE.md`, `tools/sync_wiki.py`. Doc-free
  pushes don't run it.
- **Job**: check out the repo at the pushed commit; clone
  `<repo>.wiki.git`; run `tools/sync_wiki.py --wiki <clone>`; commit and
  push the wiki only if pages changed.
- **Auth**: the workflow's built-in `GITHUB_TOKEN` with
  `permissions: contents: write` — it can push to the same repo's wiki
  git. No personal tokens, no secrets to manage.
- **Correctness property**: the action checks out the exact commit that
  triggered it, so every page banner cites the commit whose content it
  mirrors — the manual flow could drift (sync run against uncommitted
  working-tree content stamps a stale hash).

## Git-policy note

Project rule: git write operations are human-only in working sessions.
This workflow is the one sanctioned exception, and it is scoped to stay
that way: a deterministic script, writing only to the wiki repository
(a generated artifact by definition), triggered only by a human pushing
to main. The main repository's history is never touched by automation.
Wiki commits will show bot authorship — appropriate for a mirror no one
should hand-edit anyway.

## Failure mode

If the action fails (transient GitHub issue, script error on a new doc),
the wiki lags — same consequence as the manual habit slipping, now with
a visible red ✗ on the commit instead of silence. No data is at risk;
re-running the action or pushing any docs change re-syncs fully (the
mirror is stateless — every run regenerates every page).

## Build checklist — COMPLETED 2026-07-11

- [x] `.github/workflows/wiki-sync.yml` per the design above
- [x] `docs/planning/PUBLISHING-PLAN.md` and this file added to the
      `PAGES` table (22 pages mirrored)
- [x] Verified on the first triggering push: action ran (success, 9 s),
      wiki updated by github-actions[bot], live banner hashes match the
      pushed commit exactly
- [x] Manual re-sync habit retired from PROJECT-TODO; the local wiki
      clone is inspection-only from here on
