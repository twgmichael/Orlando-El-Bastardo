# Production designer plan — a set-building worker agent

Recorded 2026-07-11 (designed with the project owner). Status: **PLANNED,
not built.** Extends the crew with an agent that can be assigned set and
asset tickets, survey the library, and compose sets by kitbashing
approved pieces — formalizing the process that built the sci-fi bar.

## Why this works: the proven template

The bar set (`tools/build_scifi_bar.py`) established the pattern:
**layout-as-data** — a table of (piece, position, z-rotation) assembled
deterministically, canonical node naming, marks and cameras carried
through, material fixes applied at build time. The layout was authored
by hand through a look-adjust-look loop over review renders. Two
findings de-risk the agent version: the modular CC0 pieces compose well,
and even grey-box massing read acceptably from the start — so the
agent's floor is "usable placeholder" and its ceiling is "kitbashed
final," a forgiving gradient.

## Division of labor (unchanged principles)

- The **producer** (local LLM) files tickets naming what a scene lacks.
  It never designs and never commands agents (DECISIONS 2026-07-07).
- The **production designer** (worker-tier agent) consumes a ticket and
  delivers a set. Spatial/aesthetic judgment against rendered frames is
  frontier-model work — not the local 3B's job.
- **Dispatch and aesthetic sign-off stay human.** The designer never
  downloads or generates new source assets — acquisitions remain
  human-approved (standing constraint); it composes ONLY what the
  provenance-registered library already holds, plus primitives.

## Build order

### 1. Asset index (deterministic enabler — useful regardless)

`tools/index_assets.py` → `data/asset_index.json`: walk the converted
GLB packs and record per piece — name, pack, file, bounding box, poly
count, name-derived tags (wall/floor/door/table/panel/...). The library
is ~750 pieces across 12 packs; "review available assets" must be a
query, not a per-session expedition. Regenerate on pack additions;
deterministic ordering.

### 2. Generic set assembler (deterministic)

Generalize `build_scifi_bar.py` into `tools/build_set.py` reading a
**set spec** (JSON): layout rows (piece, position, rotation), primitive
props, marks, cameras, canonical set node name, material fixes, export
targets. The designer authors DATA, not code — reviewable, diffable,
and bounded by what the assembler permits. Acceptance: rebuilding the
existing bar from a spec reproduces it (verified by introspection
manifest / node inventory, allowing for nondeterministic binary bytes).

### 3. The designer profile (`.claude/agents/production-designer.md`)

Authored per AGENT-WORKFLOW-PLAN §4 (post-author-tier: human +
reviewer-tier co-authoring against `_TEMPLATE.md`). The working loop:

1. **Requirements in** — the ticket + script text: needed marks,
   cameras, props, mood, rough dimensions.
2. **Survey** — query the asset index for candidates.
3. **Compose** — write/edit the set spec; run the assembler.
4. **Look** — headless review renders from standard angles; judge;
   adjust; repeat. (The craft loop, now the agent's inner loop.)
5. **Register** — oeb.config.json entry, resolver-map location entry,
   marks present in the GLB, camera-grammar additions if any,
   docs/PROVENANCE.md line for the assembled set.
6. **Deliver** — set GLB + set spec + review stills attached to the
   ticket; hand to pipeline-verifier.

Standing constraints (inherits the roster's): repo-relative paths only,
no absolute paths, no downloads, no git write operations, escalation
per ESCALATION-PROTOCOL when blocked.

### 4. Qualification (per AGENT-WORKFLOW-PLAN §7)

- **Dry run**: rebuild the existing sci-fi bar from its ticket — a
  known-good target with an objective comparison.
- **Drill**: a ticket requesting something the library cannot provide
  (e.g. a rideable horse-drawn carriage) — must report the gap
  precisely and stop; improvisation or acquisition attempts fail the
  drill. Mirrors the producer's missing-asset discipline.

### 5. Verification gates (unchanged discipline)

pipeline-verifier checks (canonical node, marks in GLB, clean headless
import), then a real scene render through the pipeline, then human
aesthetic sign-off. A delivered set that no scene can render is not
done.

## Assignment interface

Near-term: NEEDED ticket files under `out/production/<episode>/tickets/`
(what exists today). Later: GitHub Issues + a Project board per the
Issues discussion — producer files, human dispatches, designer claims
via label/field, thread carries the build log, close on verifier pass +
human acceptance.

## First real assignments (already queued in PROJECT-TODO)

1. Orbital-lounge dressing: instrument panels + viewports (Modular
   Sci-Fi MegaKit), booths/tables (House Interior pack), station
   personnel EXCLUDED (characters are not set dressing).
2. Bar furniture (counter/stool/glass/bottle upgrades — House Interior
   donors).
3. `rooftop_garden` — the standing ep_001 ticket.

## Non-goals

- No generative geometry/textures; composition of approved assets only.
- No autonomous acquisition of new packs.
- No self-approval: the designer never closes its own ticket.
