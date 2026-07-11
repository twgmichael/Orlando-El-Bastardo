# Publishing plan — automatic YouTube upload of renders

Recorded 2026-07-11 (decided with the project owner). Status: **PLANNED,
not built.** This documents the policy and design so the build is a
mechanical step.

## Policy: three tiers, only two upload

| Tier | What | Trigger | Visibility | Who decides |
|---|---|---|---|---|
| Iteration renders | Per-scene review renders during development | never uploaded | local only | — |
| Development progress | Episode cut from a successful production run | automatic, on `producer.py` delivery | **unlisted** | pipeline |
| Curated | Milestone/showcase picks (feature landings, new episodes) | human-chosen run or edit | **public** | human |

The mistake this policy exists to prevent: uploading every render. A
single working day can produce a dozen near-identical iteration clips;
they are scaffolding, not documentation. The automatic tier fires only
when the producer delivers an episode cut — the visual analog of a
PROJECT-DONE entry.

## Why upload at all

Every delivered production run leaves a permanent, linkable video
snapshot tied to a commit hash. PROJECT-DONE entries and the wiki
Journal-Log currently *describe* renders that a reader cannot see;
upload URLs close that gap. Curated public videos are the showcase
layer on top.

## Mechanics

- **API**: YouTube Data API v3 `videos.insert`, OAuth 2.0 installed-app
  flow. One-time human step: create the Google Cloud project, configure
  the OAuth consent screen, and complete the browser authorization once;
  the stored refresh token makes subsequent uploads unattended.
- **Quota**: default 10,000 units/day; an upload costs 1,600 → ~6
  uploads/day ceiling. Episode-level cadence fits comfortably;
  per-render cadence would not (a second reason for the tier policy).
- **Unverified-app caveat**: until the OAuth app passes Google's
  verification, uploads are locked to private visibility. Acceptable for
  the development-progress tier (a private/unlisted review trail);
  verification only matters when the curated public tier goes live.
- **Metadata is generated, not typed**: title from episode + scene ids;
  description auto-built from the production report (commit hash,
  delivered/blocked counts, open ticket summary); one playlist per
  episode. The upload documents itself.

## Code placement (decided 2026-07-11)

**In this repo** — `tools/upload_render.py`, invoked by `producer.py`
after the episode cut behind an explicit flag/policy (never during
plain development runs). Rationale: the upload step is part of the
production run's lifecycle; a separate repo would drift against the
hook for ~100 lines of code; the tool itself contains nothing
sensitive.

**Credentials never enter the tree.** Gitignored from day one, following
the existing `docs/local/` discipline:

1. `client_secrets.json` (OAuth app identity)
2. the stored refresh token
3. channel/playlist configuration (playlist IDs are not secrets, but
   they are channel-specific; keeping them local keeps the public tool
   generic)

The tool reads its config from the gitignored path and fails with a
clear "not configured" message when absent — a stranger cloning the
public repo gets working code that does nothing without their own
credentials.

## Documentation linkage

On upload, the video URL is recorded in the production report
(`out/production/<episode>/production_report.json`), and the
PROJECT-DONE entry for the milestone links it. The wiki Journal-Log
inherits the links via the docs → wiki mirror.

## Build checklist (code built 2026-07-11; awaiting the human OAuth step)

- [ ] Human: Google Cloud project + enable YouTube Data API v3 + OAuth
      "Desktop app" client → JSON to `.secrets/client_secrets.json`,
      then `tools/upload_render.py --auth` once (browser)
- [x] `tools/upload_render.py` (upload + metadata from production
      report + playlist management; `--dry-run` and graceful
      not-configured paths verified)
- [x] `producer.py` hook behind `--publish` (off by default; publish
      failure never fails the run)
- [x] `.gitignore` entry for `.secrets/`
- [x] This page mirrored to the wiki (PAGES table, 2026-07-11)
- [ ] Record the first upload's URL in PROJECT-DONE
