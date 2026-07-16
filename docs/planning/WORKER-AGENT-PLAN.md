# Worker agent plan — cross-platform harness workers + macOS menu bar

Recorded 2026-07-14. Updated 2026-07-14 (script_file + cwd + output_root live).
Status: **RUNNING** — control plane at `http://oeb-studio.docker-pi`;
mac-mini worker registered and running with menu bar app; pipeline render
scripts dispatched end-to-end; renders writing to OEB-PROJECT external drive.
Gaming-PC worker install pending.
Companion docs: AGENT-BUS-PLAN.md (GitHub Issues coordination substrate),
studio-production-pipeline-harness-ansible-spec.json (full system spec),
WORKER-AGENT-PLAN.md (this doc).

## What a worker is

A worker is a Python process that polls the harness control plane for jobs,
claims one at a time, runs it through an adapter, uploads artifacts, and
reports completion or failure. Workers are cross-platform (Mac, Windows,
Linux) and stateless — all durable state lives in the harness PostgreSQL
database.

Code lives in `oeb-studio-harness/worker/`.

## Job lifecycle (worker side)

```
poll /api/v1/jobs/eligible
  → claim /api/v1/jobs/{id}/claim          (gets a lease)
  → run adapter (in thread executor)
    ↳ concurrent lease renewal loop
  → upload artifacts → /api/v1/jobs/{id}/artifacts
  → complete /api/v1/jobs/{id}/complete
     or fail /api/v1/jobs/{id}/fail        (idempotent jobs requeue)
```

Lease renewal fires at `LEASE_RENEW_THRESHOLD` (0.4) × lease window.
If the process dies mid-job, the maintenance loop on the control plane
expires the lease and requeues idempotent jobs automatically.

## Adapters

### OllamaAdapter

Calls a local Ollama instance (`http://localhost:11434/api/chat`). Uses
`urllib` — no extra dependencies. Capabilities declared:

- `llm.scene_spec` — scene intent → SceneSpec translation
- `llm.blender_python` — Blender Python script generation
- `llm.general` — open-ended LLM tasks
- `vision.image_analysis` — image description/analysis
- `vision.render_comparison` — render QA comparisons

Config keys: `base_url`, `default_model`, `timeout_seconds`.

### BlenderCLIAdapter

Runs Blender headless. Path traversal protection on file paths (`..`
rejected). Inline Python overrides for samples and resolution from the job
payload. Tags output artifacts as `preview_render` or `final_render` based
on `payload._preview`. Capabilities declared:

- `blender.final_render`
- `blender.preview_render`
- `blender.command_line`
- `gpu.cycles_render` (gaming PC only)
- `gpu.texture_bake` (gaming PC only)

Config keys: `executable` (path or bare `blender`), `max_concurrent`,
`timeout_seconds`.

**Payload fields — `blend_file` mode:**

| Field | Required | Description |
|---|---|---|
| `blend_file` | yes | Path to a `.blend` file — `blender --background <file>` |
| `output_path` | yes | Render output path (no `..`); supports `{output_root}` and `{job_id}` |
| `frame` | no | Single frame to render (default: 1) |
| `start_frame` / `end_frame` | no | Frame range (uses `--render-anim`) |
| `engine` | no | Render engine, default `CYCLES` |
| `samples` | no | Cycle sample count override |
| `resolution_x` / `resolution_y` | no | Resolution overrides |
| `format` | no | Output format, default `PNG` |
| `_preview` | no | If true, artifact tagged `preview_render` instead of `final_render` |

**Payload fields — `script_file` mode:**

| Field | Required | Description |
|---|---|---|
| `script_file` | yes | Path to a `.py` script — `blender --background --python <file>` |
| `cwd` | no | Working directory for the Blender process; use repo root for scripts that call `os.getcwd()` |
| `script_args` | no | List of strings appended after `--`; `{output_root}` and `{job_id}` are substituted in each arg |
| `output_path` | no | If given, artifacts are collected from this path after the script exits |
| `_preview` | no | If true, artifact tagged `preview_render` instead of `final_render` |

Both modes reject `..` in any path. Specifying both `blend_file` and
`script_file` is an error.

## Configuration

Each machine gets a YAML config file. Env vars override config file values:

| Env var | Purpose |
|---|---|
| `OEB_HARNESS_URL` | Control plane base URL |
| `OEB_ENROLLMENT_TOKEN` | Token presented at registration (from vault) |

Harness URL: `http://oeb-studio.docker-pi` (resolves via Pi-hole wildcard
`*.docker-pi` on network devices; Mac resolves via `/etc/hosts` managed by
the macos-setup playbook from the `traefik_domains` list in host_vars).

Template configs:

- `config-examples/mac-mini.yml` — `qwen2.5-coder:14b`, artifact store at
  `/Users/Shared/oeb-studio-harness/artifacts`, `blender` on PATH
- `config-examples/gaming-pc.yml` — `qwen2.5-coder:32b`, artifact store at
  `Z:/oeb-studio-harness/artifacts` (SMB share), full Windows Blender path

Key config fields: `worker_id`, `platform`, `capabilities`, `resources`
(ram_gb, gpu_type, vram_gb, available_storage_gb), `poll_interval_seconds`,
`heartbeat_interval_seconds`, `artifact_store_root`, `output_root`.

`output_root` sets the base output path for renders on this machine. Job
payload paths and `script_args` can contain `{output_root}` and `{job_id}`,
which are substituted at runtime. This keeps job payloads machine-agnostic
and lets repeated canonical ids write into separate job-scoped directories.
Example:
- mac-mini: `/Volumes/OEB-PROJECT/OEB-PRODUCTION`
- gaming-pc: `Z:/OEB-PROJECT/OEB-PRODUCTION`

## Registration and authentication

On first start the worker posts to `/api/v1/workers/register` with the
enrollment token. The harness issues a per-worker token, which is saved to
`token_file` (chmod 0600) and reused on subsequent starts. If registration
fails (harness not yet reachable), the worker retries with exponential
backoff: 5 s → 10 s → 20 s → … → 60 s cap. This lets the worker survive
cold starts where the harness comes up after the worker process.

## Installing on a machine

```bash
# from oeb-studio-harness/worker/
pip install -r requirements.txt

# copy and edit a config
cp config-examples/mac-mini.yml my-config.yml   # or gaming-pc.yml

# set secrets (never commit these)
export OEB_HARNESS_URL=http://oeb-studio.docker-pi
export OEB_ENROLLMENT_TOKEN=<from vault — grep API_ADMIN_TOKEN on Pi harness.env>

# run (plain worker, no UI)
python agent/main.py my-config.yml

# run (macOS menu bar — Mac mini preferred entry point)
python oeb_menu_bar.py my-config.yml
```

**Tip:** retrieve the enrollment token without exposing it in shell history:
```bash
ssh docker-pi-01.local "grep WORKER_ENROLLMENT_TOKEN /mnt/docker-data/oeb-studio-harness/harness.env"
```

**API + Swagger UI:** `http://oeb-studio.docker-pi/docs` — FastAPI
auto-generated interactive docs. Use it to create projects, submit jobs, and
inspect responses without writing curl commands. Authenticate with the admin
token (retrieve via `grep API_ADMIN_TOKEN` on the Pi's `harness.env`).

Prerequisites per machine:

| Prerequisite | Mac mini | Gaming PC |
|---|---|---|
| Python 3.11+ | ✓ | ✓ |
| Ollama + model pulled | ✓ | ✓ |
| Blender on PATH or configured | ✓ | ✓ (full path in config) |
| `artifact_store_root` writable | `/Users/Shared/…` | `Z:/…` (SMB mount) |
| `rumps` (macOS only) | required for menu bar | n/a |

Pending: `pyproject.toml` for clean `pip install -e .` instead of bare
`requirements.txt`.

## macOS menu bar app (`oeb_menu_bar.py`)

Designed for the Mac mini, which doubles as a desktop workstation. Surfaces
worker state in the macOS menu bar so the operator can see at a glance
whether a job is running without opening a terminal or browser.

**Architecture:**
- Main thread: `rumps` app (AppKit `NSStatusBar` — required by macOS)
- Daemon thread: asyncio event loop running the full worker
- Bridge: thread-safe `queue.Queue` drained by a `rumps.Timer` every 1 s

**Icons (`worker/icons/`):**

| File | State | Description |
|---|---|---|
| `icon-idle.png` | Idle | OEB badge, black on transparent |
| `icon-busy.png` | Busy | OEB badge with rotation arrows, black on transparent |
| `icon-idle-dark.png` | Idle (explicit dark) | White variant |
| `icon-busy-dark.png` | Busy (explicit dark) | White variant |

All icons are 44 × 44 px (Retina). Set as macOS template images
(`template=True` in rumps) — the OS handles light/dark rendering
automatically; the explicit dark variants exist if manual control is needed.

**Menu items:**
- Status line: `"Idle"` / `"Running: <job title>"`
- *(separator)*
- `"Open Dashboard"` — opens harness URL in the default browser
- *(separator)*
- `"Quit"`

**State hooks** wired into `HeartbeatLoop`:
- `on_busy(job_id, job_title)` → swaps to busy icon, updates status line
- `on_idle()` → swaps to idle icon, resets status line

## Worker machines

| Machine | Worker ID | Notable capabilities | Status |
|---|---|---|---|
| Mac mini (M-series) | `mac-mini` | llm.*, vision.*, blender.preview | Running (menu bar) |
| Gaming PC (RTX 4090) | `gaming-pc` | blender.final_render, gpu.cycles_render, gpu.texture_bake | Not yet installed |

## Open work

- [x] Mac mini worker installed and running — DONE 2026-07-14
- [x] First project created in harness — DONE 2026-07-14
- [x] First job submitted and claimed end-to-end — DONE 2026-07-14
- [x] `script_file` + `cwd` support in BlenderCLIAdapter — DONE 2026-07-14
- [x] `output_root` per-worker config + `{output_root}` substitution — DONE 2026-07-14
- [x] First pipeline render script dispatched via harness — DONE 2026-07-14
- [x] Renders writing to `/Volumes/OEB-PROJECT/OEB-PRODUCTION` — DONE 2026-07-14
- [x] PostgreSQL port 5432 exposed for direct SQL client access — DONE 2026-07-14
- [ ] Install worker on gaming PC
- [ ] Add `pyproject.toml` for clean `pip install -e .`
- [ ] Commit `oeb-studio.docker-pi` to `traefik_domains` in host_vars
  (currently added manually to `/etc/hosts` via macos-setup playbook)
- [ ] Wire worker into the agent bus once AGENT-BUS-PLAN.md is actioned
