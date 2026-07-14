# Studio Production Pipeline Harness — Ansible + Docker Implementation Spec

Recorded 2026-07-13. Source: `studio-production-pipeline-harness-ansible-spec.json`.
Status: **proposed** (written as implementation handoff for an LLM or developer).

Companion: [STUDIO-HARNESS-VISION.md](STUDIO-HARNESS-VISION.md)

## Purpose

Specify an Ansible-managed Docker deployment for a Raspberry Pi 4 control plane
that accepts production requests, routes work to workers, preserves project
state, and coordinates a reproducible 3D studio pipeline.

## Non-Goals

- Run large language models on the Raspberry Pi
- Run Blender rendering or simulation workloads on the Raspberry Pi
- Store large binary assets inside PostgreSQL
- Require the gaming PC to remain powered on
- Replace Blender, Godot, USD, or existing creative tools

## Deployment Target

**Device:** Raspberry Pi 4, 8 GB RAM, arm64

**OS:** 64-bit Raspberry Pi OS Lite or compatible Debian-based ARM64

**Network:**
- Wired Gigabit Ethernet preferred
- Reserved DHCP lease or static local address
- Local DNS: `studio-orchestrator.local`
- Local network only by default

**Storage (all on USB 3 SSD — never microSD):**

| Path | Purpose |
|---|---|
| `/srv/studio-harness` | Mount root |
| `/srv/studio-harness/postgres` | Database |
| `/srv/studio-harness/metadata` | Artifact metadata |
| `/srv/studio-harness/backups` | Database backups |

**Hardware recommendations:** Official Pi power supply, active cooling,
small UPS when operationally critical.

## Architecture

**Pattern:** Always-on control plane with replaceable capability-advertising workers.

**Control plane responsibilities (Pi):**
API endpoint, authentication, project registry, asset registry, canon and production
metadata, worker registration, worker heartbeats, capability discovery, job creation,
resource-aware job routing, job leases, retry/fallback policy, approval workflow,
audit history, backup scheduling, health monitoring.

**Workers:**

| Worker | Availability | Capabilities |
|---|---|---|
| Mac mini workstation | Interactive, usually available; must stay usable as desktop | Local LLM, VLM, Blender interactive, preview render, scene review, asset approval, script development, image preprocessing |
| Windows gaming PC | Opportunistic, not always powered on | GPU rendering, Cycles final render, texture baking, simulation, video processing, large-model inference, batch export |
| Future worker nodes | Dynamic | Any capability declared through worker registration protocol |

**Request flow:**

```
User submits request (web or desktop client)
  → Harness records request + retrieves project context
  → Router classifies task + identifies required capabilities
  → Harness selects cheapest competent available worker
  → Worker claims job (renewable lease)
  → Worker downloads/accesses inputs
  → Worker executes registered adapter
  → Worker uploads outputs + logs + metrics + completion
  → Harness validates outputs
  → Preview/structured result enters human review (when required)
  → Approved result becomes new project or asset version
```

## Ansible Role

**Role name:** `studio_harness_orchestrator`

**Context:** Add to existing local device management Ansible project.

**Supported hosts:** Debian-family ARM64; primary target: Raspberry Pi 4 (8 GB)

**Dependencies:** Docker Engine role, Docker Compose plugin role, host firewall role,
optional local CA/reverse-proxy role, optional SSD mount/filesystem role.

**Responsibilities:**
- Validate ARM64 architecture and minimum memory
- Validate persistent SSD mount
- Create service user and groups
- Create directory hierarchy
- Deploy Docker Compose project
- Deploy environment files and Docker secrets
- Deploy application configuration
- Initialize PostgreSQL database and extensions
- Run database migrations
- Configure health checks, firewall rules, backup scripts, systemd timers, log rotation
- Start and verify services
- Expose deployment facts to rest of Ansible project

**Suggested role structure:**

```
studio_harness_orchestrator/
  defaults/main.yml
  vars/Debian.yml
  tasks/
    main.yml
    validate.yml
    user.yml
    directories.yml
    secrets.yml
    compose.yml
    database.yml
    firewall.yml
    backups.yml
    healthcheck.yml
  templates/
    compose.yml.j2
    harness.env.j2
    harness-config.yml.j2
    backup-postgres.sh.j2
    studio-harness-backup.service.j2
    studio-harness-backup.timer.j2
  handlers/
    restart studio harness
  files/
    database initialization scripts (if not managed by migrations)
  molecule/
    ARM64-compatible test scenario
    General Docker test scenario (CI)
```

**Key variables:**

| Variable | Value |
|---|---|
| `studio_harness_root` | `/srv/studio-harness` |
| `studio_harness_compose_project` | `studio-harness` |
| `studio_harness_api_port` | `8080` |
| `studio_harness_bind_address` | `0.0.0.0` |
| `studio_harness_postgres_version` | `17` |
| `studio_harness_postgres_memory_limit` | `2g` |
| `studio_harness_enable_redis` | `false` |
| `studio_harness_enable_reverse_proxy` | `true` |
| `studio_harness_backup_retention_days` | `14` |
| `studio_harness_worker_heartbeat_seconds` | `20` |
| `studio_harness_worker_timeout_seconds` | `75` |
| `studio_harness_job_lease_seconds` | `120` |
| `studio_harness_local_network_cidr` | `CONFIGURE_IN_INVENTORY` |
| `studio_harness_timezone` | `America/New_York` |

**Secrets (Ansible Vault + Docker secrets; never plaintext in Compose, Git, or inventory):**
- PostgreSQL superuser password
- Harness database password
- Application signing secret
- Worker enrollment token
- API administrator bootstrap token
- Optional TLS private key

## Docker Stack

### Required Services

**postgres**
- Official PostgreSQL arm64 image, version 17
- Persistent; enable JSONB, pg_trgm; evaluate pgvector later
- Do not store large media binaries

**harness-api**
- FastAPI/Python or ASP.NET Core
- Required features: OpenAPI schema, DB migrations, token auth, worker registration,
  heartbeat endpoint, job APIs, lease APIs, asset registry APIs, project context APIs,
  audit events, health/readiness endpoints

**harness-ui**
- Lightweight browser dashboard: projects, assets, workers, queues, logs, approvals, previews
- May be bundled into harness-api for initial release

**reverse-proxy**
- Caddy, Traefik, or Nginx for local HTTPS termination
- Optional for initial prototype

### Optional Services

**redis** (default: disabled) — add when PostgreSQL-backed queue is a measured bottleneck,
low-latency pub/sub is needed, or multiple API replicas share ephemeral state.
Must not store: project canon, approved SceneSpecs, asset records, job history, user approvals.

**minio** (default: deferred) — S3-compatible artifact storage if shared filesystem becomes limiting.
Deferred: Pi should not become primary repository for large render/video payloads without a storage plan.

### Networking

- Internal Docker network between services
- Publish API or reverse proxy only
- PostgreSQL stays internal unless explicit LAN database access is required

### Health Checks

PostgreSQL readiness, harness API liveness, harness API database readiness,
UI availability, disk free-space threshold, backup recency.

## Database

**Engine:** PostgreSQL

**Rationale:** Concurrent writes from several workers; JSONB for SceneSpec/ShotSpec/model
config/tool-call documents; transactional job leases; reliable audit history; complex asset
relationships; full-text/trigram search; optional vector search; advisory locks and notifications.

**Core entities:**

```
users, api_tokens, projects, project_facts, canon_entries,
assets, asset_versions, asset_components, materials, locations,
scenes, scene_versions, shots, shot_versions,
reference_sets, reference_images, visual_observations,
workers, worker_capabilities, worker_heartbeats,
jobs, job_requirements, job_attempts, job_leases,
tool_calls, validation_reports,
artifacts, artifact_checksums,
approvals, audit_events,
model_registry, adapter_registry
```

**Provenance values:** `observed`, `measured`, `inferred`, `canon`, `user_approved`

**Binary storage policy:** Store paths, object keys, MIME types, dimensions,
checksums, and provenance in PostgreSQL. Store `.blend`, `.usd`, `.glb`,
textures, images, renders, audio, and video outside PostgreSQL.

## Asset Registry

First-class core service. Ensures models and tools reference stable reusable assets
rather than recreating them.

**Examples:** JourneyBlaster 5000 hull, detachable engine pods, cockpit bubble,
Barka SpaceLoungers, Frap Ray weapons, Red Dragon Inn furniture, starbase corridor
modules, doors, lighting rigs, camera rigs, materials, characters, skeletons, animations.

**Required fields:** Stable asset ID, human-readable name, asset type, current approved
version, source files, component hierarchy, dimensions and units, coordinate convention,
materials, behavioral capabilities, dependencies, reference images, canon links,
approval status, checksums.

## Worker Protocol

**Transport:** HTTPS JSON API for initial release; WebSocket or SSE may supplement polling later.

**Rule:** Each workstation runs a small local agent. The Pi must not control workstations
through ad hoc SSH commands.

**Registration payload example:**
```json
{
  "worker_id": "mac-mini",
  "platform": "macos-arm64",
  "agent_version": "0.1.0",
  "capabilities": [
    "llm.scene_spec",
    "llm.blender_python",
    "vision.image_analysis",
    "vision.render_comparison",
    "blender.interactive",
    "blender.preview_render"
  ],
  "resources": {
    "ram_gb": 32,
    "gpu_type": "Apple Silicon integrated",
    "available_storage_gb": 500
  }
}
```

**Heartbeat payload example:**
```json
{
  "worker_id": "gaming-pc",
  "status": "busy",
  "current_job_id": "render-1842",
  "cpu_load_percent": 38,
  "gpu_load_percent": 96,
  "free_ram_gb": 42,
  "free_vram_gb": 2,
  "timestamp": "ISO-8601"
}
```

**Lease behavior:**
1. Worker claims an eligible job
2. Harness grants a time-limited lease
3. Worker renews lease during execution
4. Harness marks attempt interrupted after lease expiration
5. Retry policy returns safe jobs to the queue
6. Non-idempotent jobs require checkpoint or manual review

**Worker agent responsibilities:**
Register capabilities → send heartbeats → request eligible jobs → claim and renew leases →
fetch job inputs → invoke only registered local adapters → capture stdout/stderr/metrics →
upload artifacts → submit checksums → report success/failure/cancellation/partial completion.

## Routing

**Principle:** Select the cheapest competent currently available worker.
Escalate only after validation failure, repeated unsuccessful attempts, or explicit policy.

**Initial router:** Rule-based conventional software.

**Task routing examples:**

| Task | Route |
|---|---|
| Move, rotate, resize, duplicate | Deterministic adapter or tiny function-calling model |
| Apply known material or library asset | Deterministic asset operation |
| Generate SceneSpec from established components | Local 7B–14B model |
| Write or repair Blender Python | Local 14B–30B coding model |
| Interpret drawings or compare renders | Local VLM + conventional computer vision |
| Resolve ambiguous new design or major story implications | Larger local model or optional frontier model |
| Render or export | Blender or media tool, not an LLM |

**Job policies:** `run_anywhere`, `wait_for_preferred_worker`, `preview_now_final_later`,
`local_only`, `manual_approval_required`

**Fallback example:** Final 4K JB5K turntable → preferred: gaming PC GPU render →
when unavailable: preview on Mac mini, final render queued until gaming PC returns.

## Model and Tool Registry

**Model record fields:** Model ID, provider, endpoint, capabilities, accepted media types,
context limit, cost class, speed class, privacy classification, priority, availability,
health status.

**Initial local model classes:**

| Class | Candidate | Uses |
|---|---|---|
| Coding + tool orchestration | Qwen coder model (size matched to available memory) | SceneSpec generation, Blender Python, adapter repair, structured tool calls |
| Vision-language | Qwen VL or Gemma multimodal (size matched to available memory) | Drawing interpretation, image classification, visual grounding, reference reconciliation, render comparison |
| Small function router | Small function-calling model or deterministic parser | Simple transforms, known asset placement, parameter updates |

**Frontier model policy:** Optional exception worker for high ambiguity, difficult design
reasoning, architecture, or recovery. Must not be required for ordinary production operations.

## Vision Pipeline

**Purpose:** Convert images, sketches, orthographic views, diagrams, and preview renders
into structured evidence for downstream scene planning and revision.

**Stages:**
```
Image preprocessing
  → View and media classification
  → Conventional CV measurements
  → Vision-language interpretation
  → VisualObservation schema validation
  → Multi-image reconciliation
  → SceneSpec planning
  → Preview generation
  → Render-to-reference comparison
  → Approved revision generation
```

**Conventional tools:** OpenCV, edge detection, background removal, perspective correction,
image registration, silhouette extraction, color sampling, line detection, difference maps,
feature matching, segmentation, optional depth estimation.

**Structured output requirements:** Source image ID, view type and orientation, detected
objects and components, bounding boxes or normalized regions, symmetry, relative dimensions,
colors and materials, text labels, component relationships, confidence values, uncertainties,
provenance classification.

**Important constraint:** The system must distinguish observed or measured facts from
inferred geometry. Hidden surfaces and depth inferred from drawings require confidence
values and human approval.

## Production Schemas

**Required:** `DesignIntent`, `SceneSpec`, `ShotSpec`, `VisualObservation`,
`ToolCall`, `ValidationReport`, `ArtifactManifest`

**Pipeline:**
```
Conversation
  → DesignIntent
  → SceneSpec or ShotSpec
  → Schema validation
  → Deterministic exporter or adapter
  → Preview
  → Visual comparison
  → Revision proposal
  → Human approval
  → Versioned artifact
```

**Safety rule:** Models propose structured operations. The harness validates targets,
parameters, permissions, and checkpoints before execution.

## Initial Adapters

- Blender Python adapter
- Blender command-line render adapter
- Ollama model adapter
- OpenAI-compatible model endpoint adapter
- Image preprocessing adapter
- OpenCV analysis adapter
- Filesystem artifact adapter
- Shared SMB or NFS storage adapter
- Git project checkpoint adapter
- Future: Godot exporter, USD exporter

## Storage and Versioning

- **Authoritative metadata:** PostgreSQL
- **Large artifacts:** Shared filesystem initially; object storage if required
- **Version control:** Git for schemas/scripts/config/small text assets;
  Git LFS or external storage for suitable binaries; checksums for all production artifacts
- **Checkpoint policy:** Create reversible checkpoint before destructive operations;
  never overwrite sole approved asset version; record input versions, adapter version,
  model version, parameters, and output checksum.

## Security

**Scope:** Trusted local network.

**Requirements:** TLS where practical, worker enrollment tokens, per-worker API credentials,
role-based application permissions, firewall allowlist, no direct public PostgreSQL exposure,
no arbitrary shell execution through job payloads, adapter allowlist, path traversal
protection, file type and size validation, audit every tool call and approval, secret rotation support.

**Execution policy:** Worker agents execute registered adapters with validated arguments.
Raw model-generated shell commands must not run automatically.

## Backup and Recovery

**Database:** Daily `pg_dump`; retain at least 14 daily backups; copy to another physical
device; test restoration periodically.

**Configuration:** Keep Ansible role, Compose templates, migrations, and schemas in Git;
record deployed application and schema versions.

**Artifacts:** Back up approved source assets separately from generated previews;
use checksums to detect corruption.

**Failure behavior:**
- Database outage → pauses new job assignment
- Worker outage → expires leases, preserves job history
- Gaming PC outage → must not affect API or Mac workstation
- Mac workstation outage → must not destroy queued work or project state

## Observability

**Dashboard views:** Worker availability + capabilities, current jobs, queued jobs,
failed attempts, lease expiration, recent artifacts, pending approvals, disk usage,
backup status.

**Logging:** Structured JSON app logs, per-job execution logs, model request/response
metadata, tool-call history, validation failures, authentication events.

**Metrics:** Job wait time, job execution time, success/retry rate, worker availability,
queue depth, database size, artifact throughput, model usage by capability,
fallback/escalation counts.

## Implementation Phases

### Phase 1 — Control Plane Foundation
Ansible role, Docker Compose deployment, PostgreSQL, harness API, database migrations,
worker registration, heartbeat tracking, PostgreSQL-backed job queue, job leases,
basic dashboard, backup timer.

### Phase 2 — Mac and Windows Workers
Cross-platform worker agent, Mac mini registration, gaming PC registration, capability
advertisement, Ollama adapter, Blender command-line adapter, artifact upload and checksum
flow, preview-now and final-later job policy.

### Phase 3 — Asset and Production Schemas
Asset registry, SceneSpec, ShotSpec, ToolCall schema, validation service,
Git checkpoint adapter, approval workflow.

### Phase 4 — Vision Workflow
Reference-set ingestion, image preprocessing, VLM adapter, VisualObservation schema,
multi-view reconciliation, preview comparison, revision proposals.

### Phase 5 — Scale and Refinement
Optional Redis (by measured need), optional object storage, WebSocket or event streaming,
Godot and USD exporters, additional worker types, semantic search, advanced scheduling
and quotas.

## Minimum Viable Product

**User story:** A user submits a request from the Mac mini. The Pi records it, routes a
preview task to the Mac or a final render task to the gaming PC when available, preserves
job state when workers disappear, and presents the resulting artifact for approval.

**Required demonstration:**
1. Deploy the stack to the Pi through Ansible
2. Register the Mac worker
3. Register and later disconnect the gaming PC worker
4. Submit a Blender preview job
5. Complete the preview on the Mac
6. Submit a GPU-preferred final render job
7. Keep it queued while the gaming PC is offline
8. Automatically assign it after the gaming PC registers
9. Store logs, artifact metadata, checksums, and approval state
10. Restore PostgreSQL from a generated backup

## Acceptance Criteria

- Ansible role is idempotent
- All required containers run on ARM64
- PostgreSQL data survives container replacement
- No database data is written to microSD
- Mac and Windows agents can register and advertise different capabilities
- Unavailable workers are marked offline after missed heartbeats
- Jobs use renewable leases
- Interrupted safe jobs can be retried
- Gaming PC absence does not block ordinary Mac work
- Job policies support preview-now and final-later
- Models cannot execute arbitrary shell commands
- Every production artifact has provenance and a checksum
- Approved asset versions are immutable
- Daily backups are created and externally copyable
- The project can operate without a frontier model for routine work

## Open Decisions (at spec time)

- FastAPI/Python vs ASP.NET Core for the harness API
- Caddy vs Traefik vs Nginx for local HTTPS
- Shared SMB/NFS storage vs object storage for initial artifacts
- Worker polling vs WebSocket/SSE delivery
- Exact local vision model and coding model selections
- Whether existing device management project already provides Docker, firewall, CA, and SSD-mount roles
- Repository layout for server, worker agent, schemas, and Ansible role
- Authentication model for multiple future users

## Implementation Guidance

**Priority order:** Reliable orchestration → schema validation → worker availability
handling → asset provenance → reversible execution → model flexibility → UI polish.

**Avoid:**
- Premature autonomous-agent complexity
- Redis before a measured need
- Embedding large files in PostgreSQL
- Direct SSH orchestration
- Hard-coded model names
- Hard-coded assumptions that the gaming PC is online
- Letting model prose become production state without validation
- Silently treating inferred visual details as canon

**First build instruction:** Implement Phase 1 as a small, testable control-plane service
with PostgreSQL-backed worker registration, heartbeats, capability matching, jobs,
attempts, leases, audit records, and an Ansible role that deploys the Docker stack
idempotently to ARM64.
