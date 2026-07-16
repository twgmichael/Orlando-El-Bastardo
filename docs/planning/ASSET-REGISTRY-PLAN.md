---
title: Asset Registry Plan
created: 2026-07-14T19:24:07-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: plan
production_area: assets
department: pipeline
status: draft
canonical: true
canonical_for: asset_registry
wiki: true
wiki_group: Planning
wiki_page: Asset-Registry-Plan
wiki_order: 120
---
# Asset Registry — Harness DB Plan

Recorded 2026-07-14. Status: **PLANNED, not built.**

## Goal

Move the canonical asset registry from `oeb.config.json` into the PostgreSQL
harness database. `oeb.config.json` is a flat file tied to a single machine;
the harness needs a queryable, globally-accessible registry that any connected
worker can consult, that carries status and provenance, and that the future
conversational pipeline (conversation → intent extraction → canon lookup) can
interrogate directly.

Assets are **global to the harness** — not scoped to a project. Orlando El
Bastardo is the production we are building these tools to serve, but the
harness is designed to be reused by other productions.

## Current state

`oeb.config.json` holds 9 assets (2 characters, 1 set, 4 bar props, 2 ships)
with three fields per asset: `file` (relative path), `node` (GLB node name),
and `kind`. The harness seed step will read this file and populate the DB.
`oeb.config.json` stays in place for local pipeline tools (`producer.py`,
exporters) until those tools are explicitly migrated; the DB becomes the
authoritative source for harness-mediated workflows.

## DB schema — `assets` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | harness-internal identity |
| `canonical_id` | String(128) UNIQUE NOT NULL | OEB naming convention (`char_hero_v1`) |
| `name` | String(256) | human-readable display name |
| `kind` | String(64) NOT NULL | enum (see below) |
| `file_path` | String(512) | relative to asset root (`characters/oeb_dressed_characters.glb`) |
| `node_name` | String(256) nullable | node within the file, when relevant |
| `format` | String(32) | derived from extension: `glb`, `fbx`, `usdc`, `png`, … |
| `status` | String(32) | `available` / `wip` / `needed` / `missing` |
| `provenance` | JSON | source, license, notes, seeded_at |
| `tags` | JSON | string array for ad-hoc search |
| `metadata` | JSON | kind-specific extra fields (catch-all) |
| `created_at` | DateTime(tz) | |
| `updated_at` | DateTime(tz) | |

**No project FK.** Assets are global.

### Kind enum (string values)

`character` · `set` · `prop` · `ship` · `animation` · `skeleton` ·
`material` · `camera_rig` · `lighting_rig` · `location`

Note: JB5K and JB100 are currently typed `prop` in `oeb.config.json`. The
seed imports them as-is; they can be reclassified to `ship` manually after
import.

### Status enum

| Value | Meaning |
|---|---|
| `available` | file confirmed present, ready for pipeline use |
| `wip` | in progress — may be imported but not production-ready |
| `needed` | referenced by a script or scene but not yet built (mirrors NEEDED tickets) |
| `missing` | was registered, file no longer found |

## Migration

`server/migrations/versions/0003_assets.py`

Creates the `assets` table with a unique index on `canonical_id` and a
standard index on `kind` for filtered list queries.

## Pydantic schemas (`server/app/schemas/asset.py`)

- `AssetCreate` — all writable fields; `canonical_id` + `kind` required
- `AssetUpdate` — all fields optional (PATCH semantics)
- `AssetRead` — full record returned by the API

## Router (`server/app/routers/assets.py`)

Mounted at `/api/v1/assets`.

| Method | Path | Description |
|---|---|---|
| GET | `/` | List assets. Query params: `kind`, `status`, `q` (canonical_id prefix match) |
| GET | `/{canonical_id}` | Fetch one asset |
| POST | `/` | Create asset |
| PUT | `/{canonical_id}` | Full update |
| PATCH | `/{canonical_id}` | Partial update |
| DELETE | `/{canonical_id}` | Remove |
| POST | `/seed` | One-shot import from `oeb.config.json` (idempotent upsert) |

## Seed endpoint (`POST /api/v1/assets/seed`)

- Reads `oeb.config.json` from a path configured via `OEB_CONFIG_PATH` env
  var (default: relative path resolved from the server's working directory,
  same pattern as `OEB_ASSET_ROOT`)
- For each entry in the `assets` map:
  - `canonical_id` ← map key
  - `file_path` ← `file`
  - `node_name` ← `node`
  - `kind` ← `kind`
  - `format` ← extension of `file` (e.g. `glb`)
  - `name` ← `canonical_id` (editable later)
  - `status` ← `available`
  - `provenance` ← `{"source": "oeb.config.json", "seeded_at": "<iso timestamp>"}`
- **Upsert on `canonical_id`** — safe to re-run; existing records are not
  overwritten unless a `force=true` query param is passed
- Returns `{"created": N, "skipped": N, "errors": [...]}`

## File layout

```
server/app/models/asset.py          SQLAlchemy model
server/app/schemas/asset.py         Pydantic schemas
server/app/routers/assets.py        FastAPI router
server/migrations/versions/0003_assets.py
```

Register the router in `server/app/main.py` alongside the existing routers.

## Out of scope for this phase

- **oeb.config.json deprecation** — local pipeline tools continue reading
  it until they are explicitly migrated to query the harness API
- **Asset file upload** — DB stores metadata only; media lives on
  OEB-PROJECT drive (existing policy)
- **Asset versioning table** — version is baked into `canonical_id` per
  current convention (`_v1`, `_v2`); no separate versions relation needed yet
- **Asset ↔ job foreign key** — job payloads reference `canonical_id` as
  a string field; no DB-level FK yet
- **Canon/scene/episode registries** — follow-on work after the asset
  registry is running

## Build checklist

- [ ] `0003_assets.py` migration
- [ ] `server/app/models/asset.py` SQLAlchemy model
- [ ] `server/app/schemas/asset.py` Pydantic schemas
- [ ] `server/app/routers/assets.py` CRUD + seed endpoint
- [ ] Register router in `main.py`
- [ ] Run migration on docker-pi-01
- [ ] `POST /api/v1/assets/seed` with OEB_CONFIG_PATH pointed at `oeb.config.json`
- [ ] Verify all 9 assets appear in `GET /api/v1/assets`
