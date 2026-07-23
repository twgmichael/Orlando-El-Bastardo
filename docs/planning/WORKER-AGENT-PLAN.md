---
title: Worker Agent Plan
created: 2026-07-14T18:00:35-04:00
updated: 2026-07-21T00:00:00-04:00
doc_type: plan
production_area: operations
department: pipeline
status: active
canonical: true
canonical_for: worker_agent
wiki: true
wiki_group: Planning
wiki_page: Worker-Agent-Plan-Development
wiki_order: 90
---
# Worker agent plan — cross-platform harness workers + macOS menu bar

Recorded 2026-07-14. Updated 2026-07-21 (worker install/update plan revised:
Mac-like packaged installer, built-in updater, no chatbot SSH access to
personal render Macs, and `render-pc-01` remains the only full-SSH development
test worker).
Status: **RUNNING** — control plane at `http://oeb-studio.docker-pi`;
`render-mac-01` worker registered; pipeline render scripts dispatched end-to-end;
renders writing to OEB-PROJECT external drive. The worker must be launched
against the same harness environment as the queued job.
First Linux PC render worker is running and has completed real GPU/CUDA review
renders through the harness; additional workers remain planned.
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
- `gpu.cycles_render` (Linux GPU render workers)
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

- `config-examples/render-mac-01.yml` — `qwen2.5-coder:14b`, artifact store at
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
cp config-examples/render-mac-01.yml my-config.yml   # or gaming-pc.yml

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

## Render PC monitor kiosk

Linux render PCs can run a local warning/status kiosk on the attached monitor.
The first deployed instance is `render-pc-01`.

- Starts at boot before desktop login through `oeb-render-kiosk.service`.
- Runs a minimal Xorg/Openbox session and the non-snap `surf` browser.
- Serves a local page from `127.0.0.1:8765`; nothing is exposed on the LAN.
- Displays `OEB Studio - <worker-id>`, `Safe to turn off screen.`, and
  `DO NOT TURN OFF PC.`.
- Shows harness worker status, worker service state, current running job when
  assigned, and NVIDIA GPU temperature/utilization/VRAM.
- Scans the worker's local output root and cycles through the five newest
  local render images.
- Disables X sleep/DPMS blanking while periodically drawing a black overlay
  for burn-in relief.

This kiosk is managed from `project-pi-admin` in the `oeb_render_worker` role
so future `render-pc-02`, `render-pc-03`, ... machines can inherit the same
warning/status display.

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

Current launch target:

```bash
cd "<repo-root>/oeb-studio-harness/worker"
source .env.local
export PYTHONPATH=.
.venv/bin/python oeb_menu_bar.py config-examples/render-mac-01.yml
```

Use `.venv/bin/python` or `python3`; do not rely on a bare `python` shim on
this Mac. The menu bar app is the preferred Mac mini entry point. The
`start-local-worker.sh` screen launcher remains useful for headless local
worker runs.

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

## Worker Deployment And Update Plan

Updated 2026-07-21 after reviewing the current install/update path for adding
a MacBook Pro and MacBook Air as `render-mac` workers, while also keeping the
same operational model viable for future `render-pc` Windows/Linux devices.

### Discovery

The current worker is functionally cross-platform, but deployment is still
developer-shaped:

- A worker install assumes a repo checkout, manually created `.venv`, edited
  YAML config, local environment variables, and direct command-line launch.
- macOS has a useful menu bar app, but it still runs from the Python checkout
  instead of behaving like a normal installed Mac app.
- The harness already has an active-job-safe update control plane: workers
  report version/git SHA, can drain before update, and are kept out of the
  eligible pool while update states are active.
- The worker already has a self-update executor with post-update probes, but
  its command model is intentionally broad.
- The checked-in `apply-worker-update.sh` path uses `git fetch` and
  `git reset --hard`, optionally followed by service restart. That is useful
  for a development test worker, but too sharp as the default maintenance path
  for personal Macs or routine render PCs.

The main problem is not the worker runtime. The problem is the operator
experience and trust boundary: adding laptops should not require giving
chatbots or routine automation direct SSH access to those machines.

### Research And Discussion

The safer shape is a pull-based worker application:

- The harness coordinates intent: drain, update requested, target version,
  health expectations, and dashboard status.
- The worker device owns local privileged actions: install, verify, restart,
  and rollback.
- Updates are release artifacts, not arbitrary remote shell commands.
- SSH/Ansible remains reserved for initial infrastructure provisioning,
  OS/package/GPU driver work, and emergency repair.

Platform expectations:

- macOS should feel like a normal Mac app: signed/notarized `.pkg` or `.dmg`,
  `OEB Worker.app`, menu bar status, LaunchAgent startup, Keychain-backed
  secrets, and an in-app setup/update surface.
- Windows should use a signed installer (`.msi` or `.exe`), a Windows Service
  or tray app, Credential Manager for secrets, and the same updater protocol.
- Linux render PCs should use a package (`.deb` first, `.rpm` later if needed),
  a systemd service, journald logs, and the existing kiosk/status surface.

The current git-based update path remains valuable, but only as a development
backend for `render-pc-01`. It lets us test, break, inspect, and recover one
device with full SSH access without normalizing that power across the fleet.

### Recommendations

1. Package the worker as an installed application, not a checked-out Python
   script.
2. Add a first-run setup wizard:
   - harness URL
   - enrollment code
   - worker profile (`render-mac`, `render-pc`, `preview-only`,
     `final-render`, etc.)
   - durable output/artifact location
   - local probes for Blender, storage, GPU where applicable, and harness
     reachability
3. Store secrets in the platform-native secret store:
   - macOS Keychain
   - Windows Credential Manager
   - Linux keyring or root-readable service credential file
4. Replace routine arbitrary update commands with signed update bundles:
   - manifest
   - version/build id
   - platform/architecture
   - worker class
   - checksums
   - signature
5. Keep the harness update route, but make it an update coordinator:
   - request drain/update
   - expose state
   - verify heartbeat, version, capabilities, Blender, and GPU health
   - keep failed/updating workers out of the claimable pool
6. Support two channels:
   - `stable` for MacBook Pro, MacBook Air, Mac mini, and future routine PCs
   - `dev` for `render-pc-01` only, where git/SSH/manual reset paths are
     allowed

### Decisions

- Do not grant chatbots direct SSH access to the MacBook Pro, MacBook Air, or
  future routine render PCs.
- `render-pc-01` is the only full-SSH development test worker where mistakes,
  manual git resets, and service-level experiments are allowed.
- Normal worker updates will be pull-based from the worker device, after
  harness-coordinated drain.
- Routine stable-channel updates will use signed release bundles rather than
  arbitrary configured shell commands.
- The existing command-based `WorkerUpdateExecutor` and
  `apply-worker-update.sh` path may remain as the dev-channel backend until
  the packaged updater replaces it.
- macOS packaging is the first implementation target because the immediate
  new devices are a MacBook Pro and MacBook Air.
- The installation process must validate durable output storage and refuse
  unsafe temporary output roots, preserving the existing worker safety rule.

### Implementation Sequence

1. Add worker packaging metadata (`pyproject.toml`) so the worker can install
   cleanly without manual `requirements.txt`/`PYTHONPATH` handling.
2. Split runtime paths into platform-appropriate config, data, log, and secret
   locations.
3. Add a small worker supervisor responsible for start/stop/restart/update,
   separate from job execution.
4. Build the macOS packaged app:
   - bundled Python/runtime dependencies
   - `OEB Worker.app`
   - LaunchAgent
   - setup wizard
   - menu bar status
   - update UI/status
5. Add signed update bundle generation and verification.
6. Extend heartbeat/update reporting with installed package version, update
   channel, installer state, and last probe summary.
7. Port the same installer/updater contract to Linux systemd packages and
   Windows service/tray packages.
8. Keep `render-pc-01` on the dev git/SSH update path until the stable package
   flow has passed real render-worker smoke tests.

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
| Mac mini (M-series) | `render-mac-01` | llm.*, vision.*, blender.preview | Running |
| MacBook Air (Intel) | `render-mac-02` | blender.preview, blender.command_line | Planned |
| MacBook Pro | `render-mac-03` | blender.preview, blender.command_line, possible llm.* after thermal/model test | Planned; wait for packaged Mac installer path |
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
- [ ] Add MacBook Pro as `render-mac-03` after the Mac installer/update path
  is ready
- [x] Bring up `render-pc-01` Linux worker from external SSD —
  DONE 2026-07-18; Ubuntu Server 26.04, NVIDIA 595.71.05, CUDA 13.2,
  GTX 1660 SUPER 6 GB
- [x] Prove `render-pc-01` can complete GPU Cycles jobs from the harness —
  DONE 2026-07-18; JB100 smoke and seven-view final render completed with
  uploaded PNG artifacts
- [ ] Add `render-pc-02` as second Linux render worker
- [x] Rename existing Mac mini worker identity to `render-mac-01` —
  DONE 2026-07-19
- [x] Restore the OEB macOS menu bar worker under `render-mac-01` —
  DONE 2026-07-19
- [ ] Add `pyproject.toml` for clean `pip install -e .`
- [ ] Build Mac-like worker installer and setup wizard for `render-mac`
  devices
- [ ] Add signed stable-channel worker update bundles and local verification
- [ ] Keep `render-pc-01` as the only dev-channel worker with full SSH/git
  update access
- [x] Add `oeb-studio.docker-pi` to `traefik_domains` in host vars —
  DONE 2026-07-16
- [ ] Wire worker into the agent bus once AGENT-BUS-PLAN.md is actioned
- [ ] Gate `gpu.cycles_render` advertising on a Blender CUDA probe, not only
  `nvidia-smi`

## 2026-07-19 Status Snapshot

Live staging workers:

| Worker | Platform | Status | Proof |
|---|---|---|---|
| `render-mac-01` | macOS ARM64 | Online | Menu bar worker restored; LLM/vision/preview capabilities registered |
| `render-pc-01` | Linux x64 | Online | JB100 GPU smoke and seven-view final render completed with uploaded artifacts |

Important operational findings:

- The Mac mini worker identity is now `render-mac-01`; stale `mac-mini`
  harness DB records were migrated and removed from the staging worker list.
- Worker token files should be worker-specific. The Mac token lives at
  `~/.oeb-harness-worker-token-render-mac-01`.
- The official Blender Linux binary is required for NVIDIA CUDA/OptiX on
  `render-pc-01`; the Ubuntu package did not expose the needed GPU devices.
- Final review renders that must use the PC GPU should request
  `gpu.cycles_render`.
