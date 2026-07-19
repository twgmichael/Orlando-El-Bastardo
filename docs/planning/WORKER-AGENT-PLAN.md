---
title: Worker Agent Plan
created: 2026-07-14T18:00:35-04:00
updated: 2026-07-16T19:16:39-04:00
doc_type: plan
production_area: operations
department: pipeline
status: active
canonical: true
canonical_for: worker_agent
wiki: true
wiki_group: Planning
wiki_page: Worker-Agent-Plan
wiki_order: 90
---
# Worker agent plan — cross-platform harness workers + macOS menu bar

Recorded 2026-07-14. Updated 2026-07-16 (local/staging environment split
verified).
Status: **RUNNING** — control plane at `http://oeb-studio.docker-pi`;
mac-mini worker registered; pipeline render scripts dispatched end-to-end;
renders writing to OEB-PROJECT external drive. The worker must be launched
against the same harness environment as the queued job.
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

Use `OEB_HARNESS_URL` to select the environment:

| Environment | Harness URL |
|---|---|
| local Docker | `http://127.0.0.1:8088` |
| staging docker-pi | `http://oeb-studio.docker-pi` |

The staging URL resolves via Pi-hole wildcard `*.docker-pi` on network
devices; Mac hosts entries are managed by the Pi admin macOS setup flow from
the `traefik_domains` list in host vars.

Template configs:

- `config-examples/mac-mini.yml` — `qwen2.5-coder:14b`, artifact store at
  the configured `OEB_ARTIFACT_STORE_ROOT`, `blender` on PATH
- `config-examples/macbook-air.yml` — Intel MacBook Air 8,2 lightweight
  preview/build worker, project storage on external drive, no LLM capability
  advertised until a small local model is proven reliable
- `config-examples/gaming-pc.yml` — Linux worker on the external SSD,
  `qwen2.5-coder:32b`, artifact store under
  the configured `OEB_ARTIFACT_STORE_ROOT`, Blender on
  PATH unless `OEB_BLENDER_EXECUTABLE` overrides it

Key config fields: `worker_id`, `platform`, `capabilities`, `resources`
(ram_gb, gpu_type, vram_gb, available_storage_gb), `poll_interval_seconds`,
`heartbeat_interval_seconds`, `artifact_store_root`, `output_root`,
`workspace_root`.

`output_root` sets the base output path for renders on this machine. Job
payload paths and `script_args` can contain `{output_root}` and `{job_id}`,
which are substituted at runtime. This keeps job payloads machine-agnostic
and lets repeated canonical ids write into separate job-scoped directories.
Example:
- Mac workers: `<mac-project-output-root>`
- Linux GPU workers: `<linux-project-output-root>`

## Registration and authentication

On first start the worker posts to `/api/v1/workers/register` with the
enrollment token. The harness issues a per-worker token, which is saved to
`token_file` (chmod 0600) and reused on subsequent starts. If registration
fails (harness not yet reachable), the worker retries with exponential
backoff: 5 s → 10 s → 20 s → … → 60 s cap. This lets the worker survive
cold starts where the harness comes up after the worker process.

Registration is per harness environment. A worker polling the local harness is
not online for staging, even if it has the same `worker_id` and capabilities.
When a staging job remains `pending` with no attempts, first confirm that the
worker process is polling the staging `OEB_HARNESS_URL`.

## Installing on a machine

```bash
# from oeb-studio-harness/worker/
pip install -r requirements.txt

# copy and edit a config
cp config-examples/mac-mini.yml my-config.yml   # or gaming-pc.yml

# set secrets (never commit these)
export OEB_HARNESS_URL=http://oeb-studio.docker-pi
export OEB_ENROLLMENT_TOKEN=<from vault — grep WORKER_ENROLLMENT_TOKEN on Pi harness.env>

# run (plain worker, no UI)
python agent/main.py my-config.yml

# run (macOS menu bar — Mac mini preferred entry point)
python oeb_menu_bar.py my-config.yml
```

**Tip:** retrieve the enrollment token without exposing it in shell history:
```bash
ssh <harness-host> "grep WORKER_ENROLLMENT_TOKEN <deployed-harness-env-file>"
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
| Blender on PATH or configured | ✓ | ✓ (`OEB_BLENDER_EXECUTABLE` if needed) |
| `artifact_store_root` writable | configured external project drive | configured external project drive |
| `rumps` (macOS only) | required for menu bar | n/a |

Pending: `pyproject.toml` for clean `pip install -e .` instead of bare
`requirements.txt`.

## Environment Smoke Test

For a complete staging check:

1. Submit a prompt with `OEB_HARNESS_URL=http://oeb-studio.docker-pi`.
2. Confirm the response includes a `job_id`, `review_url`, and `trace_url`.
3. Start or verify an eligible worker polling the same staging URL.
4. Confirm the job moves from `pending` to `complete`.
5. Confirm the worker registered PNG, GLB, and manifest artifacts.

The 2026-07-16 smoke test used the prompt `Build a army tank.` and produced
job-scoped artifacts under the configured worker `output_root`, plus copied
artifact records under the worker `artifact_store_root`.

## Gaming PC Linux Worker Bring-up

Target shape: boot Linux from the external SSD, mount the durable production
drive at a stable local path, run Ollama locally on the PC, and register the
worker against the selected harness environment.

Planned drive: **SanDisk Professional PRO-G40 Portable SSD, 2 TB**. It should
be connected directly to the workstation over Thunderbolt 3/4 when available;
USB-C alone is not enough to guarantee Thunderbolt speed. Expected performance:
about 2,700 MB/s read and 1,900 MB/s write over Thunderbolt 3, or roughly
900-1,050 MB/s over USB 3.2 Gen 2.

Use a stable Linux mount path regardless of the drive label. The concrete value
belongs in host vars or local env, not this committed plan:

```text
<linux-project-mount>
```

Filesystem choice:

- **NTFS** for the planned shared Windows/Linux workstation role. This is the
  default recommendation for project assets, model files, Blender outputs,
  scratch files, and portability between Windows and Linux.
- **exFAT** only if macOS portability is more important than Linux metadata and
  permissions.
- **ext4** only for Linux-only workflows.

Linux caveat: if the worker virtualenv or source checkout lives on NTFS, confirm
execute permissions and file ownership after mounting. The safest first run is
to keep the repo/venv on the Linux system disk and use the PRO-G40 for durable
large data: `OEB_OUTPUT_ROOT`, `OEB_ARTIFACT_STORE_ROOT`, Ollama models,
assets, textures, renders, and scratch files.

Install prerequisites:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip blender curl git ntfs-3g
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:32b
```

Mount/create the durable roots:

```bash
sudo mkdir -p "<linux-project-output-root>"
sudo chown -R "$USER:$USER" "<linux-project-mount>"
mkdir -p "<linux-artifact-store-root>"
mkdir -p "<linux-ollama-models-root>"
mkdir -p "<linux-scratch-root>"
```

Set Ollama model storage to the PRO-G40 when model size becomes material:

```bash
export OLLAMA_MODELS="<linux-ollama-models-root>"
ollama pull qwen2.5-coder:32b
```

Set worker environment in a gitignored local file:

```bash
cd "<repo-root>/oeb-studio-harness/worker"
cat > .env.local <<'EOF'
export OEB_HARNESS_URL="http://oeb-studio.docker-pi"
export OEB_ENROLLMENT_TOKEN="<worker enrollment token>"
export OEB_OUTPUT_ROOT="<linux-project-output-root>"
export OEB_ARTIFACT_STORE_ROOT="<linux-artifact-store-root>"
export OEB_WORKSPACE_ROOT="<repo-root>"
export OEB_BLENDER_EXECUTABLE="blender"
export OLLAMA_MODELS="<linux-ollama-models-root>"
EOF
```

Create the worker virtualenv and start the foreground smoke run:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
scripts/start-gaming-pc-worker.sh
```

Smoke checks before submitting a render:

```bash
curl -i "$OEB_HARNESS_URL/ready"
ollama list | grep qwen2.5-coder
blender --background --version
findmnt "<linux-project-mount>"
PYTHONPATH=. .venv/bin/python - <<'PY'
from pathlib import Path
from agent.config import load_config
cfg = load_config("config-examples/gaming-pc.yml")
print(cfg.harness_url)
print(cfg.output_root)
print(Path(cfg.workspace_root, "tools/primitive_asset_builder.py").exists())
PY
```

The first render smoke should use the same environment as the worker:

```bash
cd "<repo-root>"
OEB_HARNESS_URL="http://oeb-studio.docker-pi" \
API_ADMIN_TOKEN="<deployed harness admin token>" \
python3 tools/studio_chat.py "Build a army tank."
```

## MacBook Air Worker Bring-up

Target machine: Intel MacBook Air 8,2, dual-core Core i5, 8 GB RAM, about
65 GB free internal storage. Treat it as a lightweight worker, not a final
render machine. Do not commit serial numbers, hardware UUIDs, provisioning IDs,
or other device identifiers.

Recommended role:

- `blender.preview_render`
- `blender.command_line`
- primitive asset build smoke tests
- queue capacity for small jobs

Avoid advertising LLM capabilities until a small model is tested under thermal
load. If it does run Ollama, keep models on the external project drive.

External project drive shape:

```text
<mac-project-output-root>
<mac-artifact-store-root>
```

First run:

```bash
cd "<repo-root>/oeb-studio-harness/worker"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

export OEB_HARNESS_URL="http://oeb-studio.docker-pi"
export OEB_ENROLLMENT_TOKEN="<worker enrollment token>"
export OEB_OUTPUT_ROOT="<mac-project-output-root>"
export OEB_ARTIFACT_STORE_ROOT="<mac-artifact-store-root>"
export OEB_WORKSPACE_ROOT="<repo-root>"
export OEB_BLENDER_EXECUTABLE="blender"

PYTHONPATH=. .venv/bin/python -u -m agent.main config-examples/macbook-air.yml
```

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

## Worker role naming

Use boring, role-based names for managed worker devices. The hostname,
inventory name, worker id, service name suffix, and log identity should match
unless there is a specific operational reason to separate them.

Preferred pattern:

| Class | Name pattern | Intended role |
|---|---|---|
| PC render worker | `render-pc-01`, `render-pc-02`, ... | Linux Blender/LLM/render workers |
| Mac render worker | `render-mac-01`, `render-mac-02`, ... | macOS preview/build/LLM workers |

Inventory shape:

```yaml
render_workers:
  children:
    render_pcs:
      hosts:
        render-pc-01:
        render-pc-02:
    render_macs:
      hosts:
        render-mac-01:
        render-mac-02:
```

Host vars can preserve human-friendly names and hardware history without
making those names part of the operational identity:

```yaml
oeb_worker_id: render-pc-01
friendly_name: gamecenter22
hardware_role: render_worker
worker_class: pc
```

This keeps the infrastructure name stable as the fleet grows while still
recording what the box is in human terms.

## Worker machines

| Machine | Worker ID | Notable capabilities | Status |
|---|---|---|---|
| Mac mini (M-series) | `render-mac-01` | llm.*, vision.*, blender.preview | Running; rename from `mac-mini` planned |
| MacBook Air (Intel) | `render-mac-02` | blender.preview, blender.command_line | Planned |
| First PC tower | `render-pc-01` | blender.final_render, gpu.cycles_render, gpu.texture_bake, llm.* | Running Linux worker; GTX 1660 SUPER verified |
| Additional PC tower | `render-pc-02` | blender.final_render, gpu.cycles_render, gpu.texture_bake | Planned Linux worker |

## Open work

- [x] Mac mini worker installed and running — DONE 2026-07-14
- [x] First project created in harness — DONE 2026-07-14
- [x] First job submitted and claimed end-to-end — DONE 2026-07-14
- [x] `script_file` + `cwd` support in BlenderCLIAdapter — DONE 2026-07-14
- [x] `output_root` per-worker config + `{output_root}` substitution — DONE 2026-07-14
- [x] First pipeline render script dispatched via harness — DONE 2026-07-14
- [x] Renders writing to configured external project output root — DONE 2026-07-14
- [x] PostgreSQL port 5432 exposed for direct SQL client access — DONE 2026-07-14
- [x] Staging docker-pi chat-to-render smoke test — DONE 2026-07-16
- [ ] Add MacBook Air as lightweight preview/build worker
- [x] Bring up `render-pc-01` Linux worker from external SSD —
  DONE 2026-07-18; Ubuntu Server 26.04, NVIDIA 595.71.05, CUDA 13.2,
  GTX 1660 SUPER 6 GB
- [x] Prove `render-pc-01` can complete GPU Cycles jobs from the harness —
  DONE 2026-07-18; JB100 smoke and seven-view final render completed with
  uploaded PNG artifacts
- [ ] Add `render-pc-02` as second Linux render worker
- [ ] Rename existing worker identities to the `render-{pc,mac}-NN` convention
- [ ] Add `pyproject.toml` for clean `pip install -e .`
- [x] Add `oeb-studio.docker-pi` to `traefik_domains` in host vars —
  DONE 2026-07-16
- [ ] Wire worker into the agent bus once AGENT-BUS-PLAN.md is actioned
- [ ] Gate `gpu.cycles_render` advertising on a Blender CUDA probe, not only
  `nvidia-smi`
