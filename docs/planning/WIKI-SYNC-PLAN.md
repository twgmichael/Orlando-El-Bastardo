---
title: Wiki Sync Plan
created: 2026-07-11T19:12:29-04:00
updated: 2026-07-16T11:56:04-04:00
doc_type: plan
production_area: publishing
department: pipeline
status: active
canonical: true
canonical_for: wiki_sync
wiki: true
wiki_group: Planning
wiki_page: Wiki-Sync-Plan
wiki_order: 60
---
# Wiki sync plan — docs → GitHub wiki, automated on push

Recorded 2026-07-11 (decided with the project owner). Updated 2026-07-16 for
metadata-driven wiki routing.

## What exists

`tools/sync_wiki.py` — one-way docs → wiki mirror. The repo is canonical;
the wiki is a generated artifact, never hand-edited.

- Public pages are discovered from markdown front matter. `wiki: true`
  publishes a page; `wiki_group`, `wiki_page`, and `wiki_order` route it in
  the generated wiki. Public pages must also include the core taxonomy fields:
  `created`, `updated`, `doc_type`, `production_area`, `department`, `status`,
  and `canonical` (`canonical_for` when canonical).
- Document lifecycle is enforced during sync:
  - `status: active` publishes normally when `wiki: true`.
  - `status: archived` publishes normally when `wiki: true`, with archived
    status visible in the metadata banner.
  - `status: superseded` publishes only when `wiki: true`, requires
    `superseded_by`, and adds a superseded-by banner line.
  - `status: remove_next_cleanup` never publishes, even if `wiki: true`; any
    existing generated wiki page is pruned on the next sync.
- The hard-coded `PAGES` table was removed on 2026-07-16. Adding a public wiki
  doc is now a metadata change in the document itself.
- Per-page banner: source path + commit hash + "the repo is canonical" plus a
  compact metadata line with document type, status, canonical topic, and file
  lifecycle stamps.
- Link rewriting: doc-to-doc links become wiki page links (plain markdown
  syntax — GitHub resolves it and it avoids `[[pipe]]` order ambiguity).
  Links are resolved by source path, not just basename; links to other repo
  files become absolute `blob/main` URLs.
- Generated `_Sidebar` (grouped: Design / Standards / Planning / Journal /
  Tracking) and `_Footer`; orphaned wiki pages pruned — the script owns
  the whole page set.
- Hard exclusion: `docs/local/**` is ignored even if a local file is
  accidentally tagged `wiki: true`.
- Verified live 2026-07-11: all pages HTTP 200; Home, sidebar, and banner
  links resolve from every page URL.

## The automation decision: GitHub Action on push to main

Manual cadence (run script, push wiki clone) works but relies on a human
habit, and the wiki silently lags when the habit slips. Decided: a
workflow that makes the mirror a server-side consequence of pushing docs.

Design:

- **Trigger**: `push` to `main`, with a `paths` filter — `docs/**`,
  `PROJECT-TODO.md`, `PROJECT-DONE.md`, `tools/sync_wiki.py`, and the workflow
  file itself. Doc-free pushes don't run it.
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

## Metadata routing — COMPLETED 2026-07-16

- [x] Public wiki pages tagged with front matter: `title`, `wiki`,
      `wiki_group`, `wiki_page`, and `wiki_order`
- [x] `tools/sync_wiki.py` discovers pages from metadata instead of a
      hard-coded page table
- [x] Wiki output strips front matter before writing generated pages
- [x] `docs/local/**` remains hard-excluded even if tagged `wiki: true`
- [x] Dry-run verified against the local wiki clone: 37 content pages plus
      `_Sidebar` and `_Footer`

## Lifecycle routing — COMPLETED 2026-07-16

- [x] `tools/sync_wiki.py` validates allowed lifecycle statuses.
- [x] `status: superseded` requires `superseded_by` and writes a wiki banner
      pointing to the replacement when published.
- [x] `status: remove_next_cleanup` acts as a committed tombstone: the source
      file remains in the repo until a later cleanup, but the wiki page is not
      generated and any previous generated page is pruned.
- [x] `status: archived` remains publishable; archived means historical value,
      not deletion.

## Full taxonomy pass — COMPLETED 2026-07-16

- [x] All project-authored markdown tagged with the core taxonomy:
      `doc_type`, `production_area`, `department`, `status`, and `canonical`
- [x] All project-authored markdown stamped with filesystem-sourced `created`
      and `updated` values
- [x] Canonical documents carry `canonical_for`
- [x] Local docs under `docs/local/**` tagged with `wiki: false`
- [x] Agent profile markdown under `.claude/agents/` augmented without removing
      agent harness fields (`name`, `description`, `model`, `tools`)
- [x] Sync fails fast when a public wiki page is missing required taxonomy
      fields
