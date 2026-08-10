---
title: Studio Chat vs. Blender MCP — Review Criteria
created: 2026-08-06T12:48:09-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: standard
production_area: pipeline
department: pipeline
status: draft
canonical: false
wiki: true
wiki_group: Standards
---
# Studio Chat vs. Blender MCP — Review Criteria

Status: draft — criteria only, no functions have been reviewed yet.

## Purpose

Decide, function by function, which existing OEB Studio Chat capabilities
(`Orlando-El-Bastardo.src`) to keep, adapt, or drop now that an official
Blender MCP server exists. The goal is not to design a competing Blender
protocol — it's to sit OEB above/alongside Blender MCP and only build what
MCP doesn't already provide.

## Target architecture

```
ChatGPT or local model
        │
        ▼
Official Blender MCP Server
        │
        ▼
Open Blender desktop session
        ▲
        │
OEB Studio harness
```

OEB Studio owns the production layer: canonical asset identity, Blueprint
execution, SceneSpec/ShotSpec, revision history and checkpoints, render
orchestration, asset promotion, permissions and validation, project memory.
Blender MCP owns tool discovery/invocation against the live Blender session.

## Scope for this pass

- Blender MCP implementation under evaluation: **official Blender Lab MCP
  server only**. The community BlenderMCP (ahujasid) project is a fallback,
  considered only if the official server proves structurally inadequate —
  not evaluated in parallel this round.
- Source of truth for current functions: `Orlando-El-Bastardo.src`.
- Local install/testing of the official MCP server and a Blender desktop
  session is authorized for this review.
- Deliverable: a function-by-function keep/drop table (separate doc),
  produced using the criteria below.

## Per-function review criteria

For each Studio Chat function, evaluate against all of the following and
record a verdict (Keep / Adapt into OEB layer / Drop) with rationale:

1. **Overlap with Blender MCP tools** — Does the official server already
   expose an equivalent tool (by capability, not necessarily by name)? If
   yes, the OEB function is a drop candidate unless it adds
   production-specific behavior on top.
2. **Production-layer ownership** — Does the function implement one of the
   OEB-owned concerns (canonical asset identity, Blueprint execution,
   SceneSpec/ShotSpec, revision history/checkpoints, render orchestration,
   asset promotion, permissions/validation, project memory)? If yes, it
   belongs in OEB regardless of MCP overlap — keep or adapt, don't drop.
3. **Viewport/session control** — Does the function depend on driving a
   persistent, already-open Blender desktop session (vs. a fire-and-forget
   headless run)? Confirm the official MCP server actually supports this
   mode before assuming the function is replaceable.
4. **Arbitrary code execution surface** — Does the function rely on
   unrestricted Python execution in Blender? If yes, it must be dropped or
   re-implemented behind a tightly gated, explicitly-permissioned path —
   never carried forward as-is, per Blender's own safety warning.
5. **Schema stability** — Is the function's behavior pinned to a specific
   tool name/schema shape? MCP does not standardize a universal Blender
   tool schema, so document the exact schema version/commit the function
   was tested against.
6. **Non-Blender dependency** — Does the function do work that has nothing
   to do with Blender control (pure OEB business logic, unrelated
   integrations)? These are out of scope for this comparison — keep as-is.
7. **Migration cost vs. value** — For functions with real overlap, weigh
   rewrite/adapter cost against how much unique value the OEB version adds
   (error handling, batching, project-specific defaults, etc.).

## Evidence required before a verdict is recorded

- The official MCP server's actual exported tool list and JSON schemas
  (not assumed from docs).
- A confirmed test result on whether the official server controls a
  persistent desktop viewport, or only headless/one-shot sessions.
- For any function verdicted "Drop," the specific MCP tool name/schema it
  is replaced by.
- For any function verdicted "Keep" due to code-execution concerns, a note
  on what gating/permission mechanism is required before it can ship.

## Out of scope for this pass

- Standing up or evaluating the community BlenderMCP project.
- Implementing the OEB adapter layer itself.
- Final keep/drop verdicts (tracked in the follow-up inventory doc).

## Function Inventory (draft — pending MCP schema export)

Grounded in current code only (no stale plan docs) under
`Orlando-El-Bastardo.src/`: `oeb-studio-harness/server/app/services/studio_chat.py`
(4243 lines), `.../app/routers/studio_chat.py` (3144 lines),
`.../app/routers/studio_chat_ui.py`, `.../app/schemas/studio_chat.py`,
`.../app/models/studio_chat.py`, and `tools/studio_chat.py` (580 lines).
No MCP install/inspection was performed for this pass, so per the evidence
rules above every row's lean is provisional — none are final "Drop."

### Global findings (apply to every row below unless noted)

- **Criterion 3 (viewport/session control) — No, for every entry.** Studio
  Chat never opens, drives, or holds a Blender session itself. It authors a
  constrained JSON "primitive spec" (`build_method: "blender_primitives"`)
  and enqueues a generic harness `Job` row; the actual Blender execution
  happens downstream, outside these files (presumably the headless
  `tools/export_blender.py` exporter path). This means almost the entire
  Studio Chat surface is naturally decoupled from whichever Blender MCP
  mode gets used — it's a spec-authoring/orchestration layer, not a
  Blender-control layer.
- **Criterion 4 (arbitrary code execution) — No, for every entry.** No
  `bpy`, `subprocess`, `exec(`, `eval(`, or `Popen` anywhere in the service
  or router files. The LLM prompts explicitly forbid it — e.g. service.py
  lines 95, 146, 173, 253, 262: *"Do not write Blender code," "Do not
  invent Blender APIs."* The model is constrained to a fixed primitive
  registry (box/sphere/cylinder/etc. + material + transform), not free-form
  code. This is a **positive safety finding**: Studio Chat already avoids
  the exact risk Blender's own MCP warning calls out, and that constraint
  should be preserved even if the authoring layer is later adapted.

Because C3/C4 are constant, the table below only breaks out Criterion 2
(production-layer ownership) and Criterion 6 (non-Blender dependency) per
row, plus a provisional lean.

| # | Entry (file:location) | What it does | C2: production-layer ownership | C6: non-Blender | Provisional lean |
|---|---|---|---|---|---|
| 1 | `routers/studio_chat.py:115,1383` `studio_chat_runtime_version`, `studio_chat_runtime_health` | Runtime/version/health probe endpoints | No | Yes | Out of scope / non-Blender (keep as-is) |
| 2 | `routers/studio_chat.py:1355,1397` + `services/studio_chat.py:414,418` `studio_chat_models`, `studio_chat_role_presets`, `list_ollama_models` | Lists available Ollama models and chat role presets | No | Yes | Out of scope / non-Blender (keep as-is) |
| 3 | `routers/studio_chat_ui.py:11` `studio_chat_page` | Serves the Studio Chat HTML UI page | No | Yes | Out of scope / non-Blender (keep as-is) |
| 4 | `routers/studio_chat.py:1402-1513` thread list/create/get/update | CRUD for chat threads | Yes — project memory | Yes | Likely OEB-owned (keep) |
| 5 | `routers/studio_chat.py:1513-1611` thread messages & events create/list | Persists chat messages and structured thread events | Yes — project memory | Yes | Likely OEB-owned (keep) |
| 6 | `routers/studio_chat.py:1204,1238,1611-1666` `_record_thread_event`, `record_studio_chat_trace`, trace-by-thread/message/job listing | Structured audit/trace log of pipeline steps per thread/message/job | Yes — project memory / permissions&validation (auditability) | Yes | Likely OEB-owned (keep) |
| 7 | `routers/studio_chat.py:2578` `studio_chat_ollama` + `services/studio_chat.py:427,457` `ollama_chat_payload`, `chat_with_ollama` | Freeform passthrough chat call to Ollama, optionally trace-logged | No | Yes | Out of scope / non-Blender (keep as-is) |
| 8 | `routers/studio_chat.py:3115` `studio_chat` (bare `POST ""`, **only endpoint with `require_admin`**) + `services/studio_chat.py` `build_studio_chat_trace`, `ollama_generate`, `legacy_spec_prompt` | Legacy admin-gated path: single-shot chat → spec → submits to a remote harness URL or a local "conversation job" | Yes — Blueprint execution (legacy path) | Partial | **Resolved (live, not superseded)** — this is exactly what `tools/studio_chat.py` calls by default at `/api/v1/studio-chat`; still a distinct single-shot flow alongside the thread/build-jobs pipeline, not replaced by it. Remains a plausible MCP-overlap candidate for a future adapter once MCP schema is exported. See "Job-worker trace and open-question resolution" in [OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md](OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md). |
| 9 | `services/studio_chat.py:578-740` `_balanced_json_object`, `_normalize_llm_json`, `parse_assistant_json`, `parse_assistant_json_with_audit` | Repairs/parses loosely-formed LLM JSON output into structured data | No | Yes | Out of scope / non-Blender (keep as-is) |
| 10 | `services/studio_chat.py:752-1041` `primitive_registry`, `validate_primitive_spec`, `_coerce_*`, `_normalize_primitive_params`, `_normalize_material` | Defines and validates the fixed primitive-shape vocabulary (box/sphere/cylinder/etc.) and its parameters | Yes — SceneSpec | No | Likely OEB-owned (keep) |
| 11 | `services/studio_chat.py:1503-1631` `resolve_primitive_spec`, `_resolver_payload`, `_scene_plan_for_primitive` + `routers/studio_chat.py:2642` `/primitive-resolver` | LLM-in-the-loop repair/retry loop that resolves a creative request into a validated primitive spec | Yes — SceneSpec | No | Likely OEB-owned (keep) |
| 12 | `services/studio_chat.py:1650-1814` `resolve_asset_intent_normalization` + helpers | Normalizes/repairs a broader "asset intent" (multi-part object) structure before spec compilation | Yes — SceneSpec | No | Likely OEB-owned (keep) |
| 13 | `services/studio_chat.py:1814-2132` `_spec_from_resolved_primitive`, `_spec_from_hierarchical_geometry`, `build_spec_with_primitive_resolver`, `build_spec_from_assistant_response` | Compiles resolved primitives/hierarchical geometry into the final `PrimitiveBuildSpec` | Yes — SceneSpec | No | Likely OEB-owned (keep) |
| 14 | `services/studio_chat.py:3499-3873` `_compile_construction_graph_primitives`, `_compile_typed_object_primitives`, geometry helpers (half-extents, vertical bounds, placement, rotation/scale from object) | Deterministic geometry math that turns a construction graph / typed object list into placed primitives | Yes — SceneSpec | No | Likely OEB-owned (keep) |
| 15 | `services/studio_chat.py:3156-3469` `default_components_for`, `enrich_scene_plan_details`, `detail_hints_for_request`, `infer_kind` | Text-heuristics that enrich a scene plan with inferred components/details from the creative request | Yes — SceneSpec (authoring heuristics) | No | Likely OEB-owned (keep) |
| 16 | `services/studio_chat.py:2249-3100` `compile_studio_chat_build_pipeline`, `_pipeline_diagnostic`, `pipeline_allows_job_submission` | Top-level orchestrator that runs the full request→spec pipeline and gates job submission on validation outcome | Yes — SceneSpec / permissions&validation | No | Likely OEB-owned (keep) |
| 17 | `tools/studio_chat.py` (whole file, 580 lines) | Standalone CLI duplicating a large subset of the resolver/spec-compilation logic (own copies of `normalize_spec`, `derive_spec_from_scene_plan`, `scene_plan_prompt`, etc.) for offline/command-line use | Yes — SceneSpec (duplicate implementation) | No | **Resolved (live CLI, not dead code)** — default behavior calls `/api/v1/studio-chat` (row 8); the duplicated logic only runs behind the explicit opt-in `--legacy-local-intake` flag, a deliberate documented fallback, not drift. Untested by the automated suite (manual/ops tool). See "Job-worker trace and open-question resolution" in [OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md](OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md). |
| 18 | `routers/studio_chat.py:2675-2937` `create_studio_chat_build_job`, `_build_job_payload` | Turns a compiled spec into a generic harness `Job` row (with post-build-review config) and records full trace/audit trail | Yes — Blueprint execution / render orchestration | No | Likely OEB-owned (keep) |
| 19 | `routers/studio_chat.py:2939-2999` `studio_chat_build_job_status` | Polls status of a submitted build job | Yes — render orchestration | No | Likely OEB-owned (keep) |
| 20 | `routers/studio_chat.py:119-232` `_review_render_views`, `_job_output_candidates`, `_find_job_output_dir`, `_review_render_candidates`, `_find_review_render_dir`, `_view_from_render_filename` | Locates and maps rendered review-image output files produced by a build job | Yes — render orchestration | No | Likely OEB-owned (keep) |
| 21 | `routers/studio_chat.py:2053-2145` `create_studio_chat_asset`, `get_studio_chat_asset_state`, `list_studio_chat_asset_revisions` | Creates/reads canonical Studio Chat asset records and their revision history | Yes — canonical asset identity / revision history | No | Likely OEB-owned (keep) |
| 22 | `services/studio_chat.py:1034-1148` `_record_asset_revision`, `_upsert_asset_state_from_build`, `_edit_build_job_from_state` | Writes a new asset revision and reconciles asset state whenever a build/edit job completes | Yes — canonical asset identity / revision history | No | Likely OEB-owned (keep) |
| 23 | `routers/studio_chat.py:2145-2165` `get_studio_chat_asset_graph` | Returns the semantic construction graph (parts/relationships) for an asset's current state | Yes — canonical asset identity | No | Likely OEB-owned (keep) |
| 24 | `routers/studio_chat.py:2165-2212` propose/validate/apply graph operations | Dry-run and apply structured edit operations (add/remove/retarget part) against the construction graph | Yes — canonical asset identity / permissions&validation (dry-run gate) | No | Likely OEB-owned (keep) |
| 25 | `routers/studio_chat.py:2212-2438` `create_studio_chat_asset_edit` + `services/studio_chat.py:293-634` `_compile_asset_edit_state`, target-matching and rotation/scale-delta helpers | Applies a free-form edit delta to an asset with optimistic-concurrency conflict checking (`base_revision` vs. current) | Yes — canonical asset identity / revision history | No | Likely OEB-owned (keep) |
| 26 | `routers/studio_chat.py:2438-2549` `revert_studio_chat_asset` | Reverts an asset to a prior revision | Yes — revision history/checkpoints | No | Likely OEB-owned (keep) |
| 27 | `routers/studio_chat.py:1721-2053,2549-2578` thread/asset milestone create+list, `get_studio_chat_milestone`, `get_studio_chat_milestone_file` + helpers `_manifest_response`, `_milestone_file_url`, `_copy_file_if_available`, `_copy_tree_if_available`, `_write_json`, `_write_text` | Creates point-in-time "milestone" manifests (with copied output files) tied to a thread or asset, and serves their files | Yes — revision history/checkpoints | No | Likely OEB-owned (keep) |

### Summary

- 27 grouped entries catalogued.
- 0 flagged as code-execution risks (Criterion 4) — confirmed no
  arbitrary/model-generated code execution anywhere in current Studio Chat
  source; the design already constrains the LLM to a fixed primitive
  schema.
- 0 entries depend on a persistent Blender viewport/session (Criterion 3)
  — Studio Chat is entirely a headless spec-authoring + job-orchestration
  layer today.
- ~21 of 27 entries are provisionally "Likely OEB-owned (keep)" — they
  implement one of the eight OEB-owned production concerns and have no
  Blender-control surface to compare against MCP at all.
- 4 entries (rows 1-3, 7, 9) are non-Blender infra/UX and out of scope for
  the MCP comparison entirely.
- 2 entries (rows 8, 17) originally needed follow-up before a lean could be
  trusted — **both resolved**: both are confirmed live and intentionally
  paired (the CLI calls the endpoint by default), not dead code. See
  below.

### Open questions / needs follow-up

- **RESOLVED — Row 17 (`tools/studio_chat.py`) — dead code or live CLI?**
  Live CLI, not dead. Default (no-flag) behavior calls `/api/v1/studio-chat`
  (row 8); its own duplicated spec-compilation logic is an explicit,
  documented opt-in fallback (`--legacy-local-intake`), confirmed
  intentional by `Orlando-El-Bastardo.src/docs/planning/STUDIO-CHAT-ENDPOINT-PLAN.md:174-223`.
  Not covered by the automated test suite (no test imports
  `tools.studio_chat`). No deletion warranted by this pass. Full evidence
  in [OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md](OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md),
  "Job-worker trace and open-question resolution".
- **RESOLVED — Row 8 (bare `POST /studio-chat`) — still in active use?**
  Yes. It's exactly the endpoint `tools/studio_chat.py` targets by default,
  so the CLI and this endpoint are two ends of the same live path, not
  independently-legacy artifacts. It remains a distinct single-shot flow
  alongside (not superseded by) the thread/build-jobs pipeline. Does not
  resolve the separate auth-coverage question below. Full evidence in
  [OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md](OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md),
  "Job-worker trace and open-question resolution".
- **Auth/permissions coverage gap (cuts across many rows).** Only row 8
  has an explicit `Depends(require_admin)` at the router level. None of
  the thread, message, asset, edit, revert, or milestone endpoints (rows
  4-6, 21-27) show endpoint-level auth in this file. It's possible auth is
  enforced by app-wide middleware not visible in `studio_chat.py` itself —
  that needs to be confirmed by reading the app's middleware/dependency
  setup before treating this as a real gap. If it *is* a gap, it's a
  pre-existing issue independent of the Blender MCP decision, but worth
  flagging since "permissions and validation" is one of the criteria-2
  OEB-owned concerns these functions are supposed to satisfy.
- **Schema-stability tag (Criterion 5) is thin.** The only explicit schema
  marker carried through specs is the string `build_method:
  "blender_primitives"` (service.py lines 1844, 2118, 4036, 4098). There's
  no version number attached to the primitive registry itself — worth
  deciding whether that needs to become an explicit version once specs
  need to be compared against a specific MCP tool-schema snapshot.
- **RESOLVED — downstream consumer of the `Job` payload.** Traced:
  `routers/conversations.py:210` `_build_job_payload` hardcodes
  `script_file: "tools/primitive_asset_builder.py"`; the worker
  (`oeb-studio-harness/worker/agent/adapters/blender.py:34`
  `BlenderCLIAdapter._execute_script`, line 259) runs it via
  `subprocess.run(["blender", "--background", "--python", script, "--",
  ...args])` — a one-shot headless process per job, confirming no
  persistent-viewport dependency at the worker level either. No
  `eval`/`exec`/dynamic code in `tools/primitive_asset_builder.py`;
  `--spec-json` is parsed as data. Net: no code-execution exposure
  end-to-end for the Studio Chat build path. Criterion 1 (MCP tool
  overlap) for rows 16-20 still needs the official MCP server's exported
  schema (next-steps items 1-2) before it can be evaluated — that part is
  unchanged. Full trace in
  [OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md](OEB-STUDIO-CHAT-LIGHTWEIGHT-PLAN.md),
  "Job-worker trace and open-question resolution". Note: `BlenderCLIAdapter`
  is a generic worker also used by `scene_render`/asset-review jobs outside
  Studio Chat — those other callers' `script_file` sources were not audited
  here and remain out of scope for this pass.

## Official Blender MCP Server — Installed & Inspected (next-steps items 1-2)

Installed and read directly from source on this machine (macOS, Blender
5.1.2 already present at `/Applications/Blender.app`, network available).
This section satisfies the "Evidence required" rule above: findings below
are from the actual installed extension, not assumed from docs.

### How it was installed (reproducible, CLI-only)

```text
blender --command extension repo-add --name "Blender Lab" \
  --url "https://lab.blender.org/" blender_lab
blender --background --python-expr \
  "import bpy; bpy.context.preferences.system.use_online_access = True; bpy.ops.wm.save_userpref()"
blender --command extension sync
blender --command extension install -e blender_lab.mcp
```

The repo URL (`https://lab.blender.org/`) is not published as plain text
anywhere on `blender.org/lab/mcp-server/` — it's embedded in a drag-and-drop
button's `data-id` attribute, extracted by fetching that page with a
browser user agent (`projects.blender.org` and a plain `WebFetch` both
return HTTP 403 for this site; `curl` with a standard browser
`User-Agent` succeeds). Enabling `use_online_access` was required before
`extension sync` would run — Blender treats reaching any extension
repository as "online access" requiring explicit opt-in.

Installed to `~/Library/Application Support/Blender/5.1/extensions/blender_lab/mcp/`.
Extension: id `mcp`, version `1.0.0`, maintainer "Blender Lab", 8 source
files, ~1,565 lines total.

### Architecture is three separate components, only one of which is installed

Per `blender.org/lab/mcp-server/`'s own "Installation" section: *"three
external tools must be manually downloaded, installed, and run"*:

1. **Add-on** (installed above) — runs inside Blender, opens a local TCP
   socket, executes requests. This is all that lives in the `mcp`
   extension package.
2. **LLM Client** — e.g. Claude, llama.cpp's web UI — not installed as
   part of this pass.
3. **MCP Server** — the actual MCP-protocol (stdio) process that a client
   like Claude/ChatGPT talks to over MCP, which then relays to the add-on's
   TCP socket. Distributed separately as an `.mcpb` bundle from the
   releases page, or built from source. **Not installed as part of this
   pass** — not needed to answer the tool-schema question (see below), and
   stands up a listener a real LLM client would drive, which is beyond
   what this review requires.

### There is no per-tool JSON schema catalog to export — this changes criterion 1 and criterion 5

The earlier "Evidence required" item asking for "the official MCP server's
actual exported tool list and JSON schemas" assumed a catalog of named
tools (`get_scene_info`, `create_object`, etc.), by analogy with
third-party Blender MCP projects. Reading the installed add-on's source
shows that assumption is wrong for the *official* server specifically:

- The add-on's socket protocol (`mcp_to_blender_server.py`) accepts exactly
  one request shape: `{"type": "execute", "code": "<python>", "strict_json":
  bool}`. There is no dispatch table of named operations — `code` is
  handed straight to Python's `exec()` (`_execute_code`,
  `mcp_to_blender_server.py:198-256`), with the result read back from a
  `result` dict the executed code must populate.
- The official page's own usage examples (Data-block renaming, scene
  debugging, Geometry Nodes documentation, polycount analysis) are all
  natural-language prompts that the LLM itself turns into ad hoc Python —
  not calls to pre-defined tools with fixed parameters.
- Practical effect: **criterion 1 (overlap with Blender MCP tools) cannot
  be evaluated function-by-function against a schema, because there isn't
  one to diff against.** The real comparison is architectural, not
  per-tool: does OEB's constrained-vocabulary spec-authoring approach get
  replaced by "let the LLM write Blender Python," or does it stay in
  front of that capability as a safety/determinism layer? See
  recommendation below.
- Criterion 5 (schema stability) is moot for the same reason — there is no
  schema shape to pin a version against on the MCP side. OEB's own
  `build_method: "blender_primitives"` marker remains the only stable
  contract in this picture.

### Code-execution safety — confirmed, not assumed

`weak_sandbox.py` (161 lines, ships with the official add-on) is
explicitly self-described in its own docstring: *"Note that this isn't
really a sandbox, more guidance that some things should not be done."* It
blocks exactly five things: `sys.exit()`, and four operators —
`wm.quit_blender`, `wm.read_factory_settings`, `wm.read_factory_userpref`,
`wm.read_userpref` (`weak_sandbox.py:52-70`). Everything else — file I/O,
network calls, `bpy.data` mutation/deletion, arbitrary shell access via
Python — is reachable from LLM-generated code with no additional guard.

The official `blender.org/lab/mcp-server/` page states this directly, as
a security warning (verbatim, fetched 2026-08-05):

> "The MCP server will execute LLM generated code in Blender without any
> guards in place to protect your data from removal or being sent to a
> remote location. To keep your data safe it is recommended to use a
> virtual machine, or a system without access to sensitive information."

This confirms the original brief's premise and Studio Chat's existing
no-code-execution design constraint (criterion 4, this doc's Function
Inventory section) is not incidental — it is exactly the risk class the
official server itself warns about. Preserve that constraint; do not let
an OEB/MCP adapter widen it.

### Viewport/session control — confirmed both modes exist (revises earlier third-party-sourced assumption)

Third-party docs quoted earlier in this file implied desktop-only
operation. The installed source shows both modes are real, and are two
different code paths in the same add-on:

- **Interactive (persistent desktop session):** `execute_interactive.py`
  registers a `bpy.app.timers` callback (0.05s active / 1.0s idle poll
  interval) that services the socket from Blender's main loop. Supports
  *deferred* responses (`deferred_tool.py`) for long-running operations —
  the client gets an "in progress" response and polls `check_is_finished`.
- **Headless/background:** `blender --background file.blend --command
  blender_mcp [--host H] [--port P]` (`cli.py`) blocks and serves requests
  synchronously via `execute_blocking.py`'s `select()` loop. Deferred
  responses are explicitly unsupported in this mode — every request must
  finish before returning.

Default in both modes: `localhost:9876` (`mcp_to_blender_server.py:36-37`).

This means the official server's headless mode is architecturally close
to OEB's actual worker pattern (`blender --background --python
tools/primitive_asset_builder.py`, confirmed above) — both are one-shot
headless Blender invocations. The difference is *what* gets executed
inside that process: OEB's worker runs a fixed, args-driven script with no
dynamic code; the official MCP server's headless mode still `exec()`s
arbitrary LLM-generated Python, with the same weak-sandbox exposure as
interactive mode.

### Recommendation this evidence supports

Do not route OEB's existing headless build path (Studio Chat → `Job` →
`BlenderCLIAdapter` → `primitive_asset_builder.py`) through the official
MCP server's `execute_blender_code`-equivalent mechanism — doing so would
trade a zero-code-execution path for one with acknowledged,
maintainer-stated, unguarded code execution, for no capability gain (OEB
already gets headless Blender invocation today). The official MCP server
is better scoped as an *interactive assistant* surface (scene debugging,
renaming, ad hoc analysis via chat) that could sit alongside Studio Chat
for exploratory/human-in-the-loop use, gated separately (per this doc's
"Out of scope" and the lightweight plan's next-steps item 6), rather than
as a replacement for the production build pipeline.

## Community Blender MCP (ahujasid/blender-mcp) — Inspected

Out of scope for the formal keep/drop review (which is scoped to the
official server only, per "Scope for this pass" above), but investigated
for integration ideas and to understand what the wider community is
building. Cloned to a local scratch directory (not part of this repo,
not installed into Blender) and read directly from source: v1.8.0,
`addon.py` (2,883 lines, Blender-side socket server) + `src/blender_mcp/`
(the MCP server package, `server.py` 1,254 lines).

### Real advantage over the official server: an actual named-tool schema

Unlike the official server's single generic `execute(code)` operation,
this project defines 23 distinct `@mcp.tool()` functions with real
per-tool parameters — `get_scene_info`, `get_object_info`,
`get_viewport_screenshot`, `execute_blender_code`, plus a full asset-
sourcing suite: PolyHaven (`search_polyhaven_assets`,
`download_polyhaven_asset`, `set_texture`), Sketchfab (`search_sketchfab_models`,
`download_sketchfab_model`), and AI mesh generation via Hyper3D/Rodin and
Hunyuan3D (`generate_hyper3d_model_via_text/images`,
`generate_hunyuan3d_model`, plus polling/import tools for both). This is
the one part of the community project genuinely worth learning from: if
OEB ever wants an external asset-sourcing capability (stock HDRIs/textures/
models, or AI mesh generation as a build-pipeline input), this is a
working reference for what that integration surface looks like — not
something to adopt wholesale, but worth a look when that need is real.

Still runs on the same default `localhost:9876` as the official add-on
(`addon.py` `bl_info` version `(1, 2)`, port default at
`bpy.types.Scene.blendermcp_port` = 9876) — the two cannot run
simultaneously without reconfiguring one's port.

### Finding worth flagging clearly: telemetry claims don't match the code

This is a materially different risk profile from the official server's
"unguarded local exec" warning — this project also **phones home to a
third-party cloud backend by design**, and its own privacy documentation
is inconsistent with its own implementation:

- `src/blender_mcp/telemetry.py` sends events (tool name, success,
  duration, Blender version, platform, a persistent per-machine UUID) to
  a Supabase REST endpoint on every tool call, enabled by default —
  opt-out only, via an env var (`DISABLE_TELEMETRY` /
  `BLENDER_MCP_DISABLE_TELEMETRY` / `MCP_DISABLE_TELEMETRY`), not opt-in.
- With a separate "consent" toggle (checked live via a
  `get_telemetry_consent` round-trip to the Blender addon), it additionally
  sends **raw prompt text and the actual executed Python code**
  (`telemetry_decorator.py` `rich_telemetry_tool(..., capture_code=True)`
  on `execute_blender_code`) to the same backend.
- `get_viewport_screenshot` (`server.py:294-371`) uploads the captured
  viewport screenshot to third-party Supabase Storage "for telemetry"
  whenever consent is on (`telemetry.upload_screenshot`, gated by
  `_check_user_consent()`).
- **`TERMS_AND_CONDITIONS.md` directly contradicts this**: under "Data I
  Collect," it states *"I do **not** collect: Screenshots or images of
  your viewport."* The code just read does exactly that, conditioned on
  the same consent flag the terms document doesn't mention screenshots
  needing. The README's separate claim that telemetry is "completely
  anonymous" is also inconsistent with a persistent per-install UUID plus,
  under consent, raw prompt/code capture — that's pseudonymous at best,
  not anonymous.
- The actual Supabase URL/anon key live in `src/blender_mcp/config.py`,
  which is deliberately git-ignored ("Local config secrets") — not present
  in the public repo, so this behavior couldn't be fully exercised from
  this clone. The PyPI-distributed package (what `uvx blender-mcp` /
  `pip install blender-mcp` actually installs) almost certainly ships a
  real `config.py`; running from source here would no-op telemetry
  silently (every call site wraps `get_telemetry()` in a broad
  `try/except`).

Net: this is not a "maybe risky if misused" finding like the official
server's exec warning — it's a documented mismatch between what the
project's own terms say it doesn't collect and what a code path does. If
this project is ever adopted for anything beyond source-reading, that
mismatch needs independent verification against whatever is actually in
the published PyPI package's `config.py`/consent-default behavior before
any real usage, not just a reading of this public repo.

### Not otherwise re-litigated

The core execution model (`execute_blender_code`, `addon.py`'s
`execute_code` handler) is the same class of risk already covered for the
official server — arbitrary `exec()` against `bpy` with no real sandbox.
Nothing here changes this doc's recommendation not to route Studio Chat's
production build path through either project's code-execution mechanism.
