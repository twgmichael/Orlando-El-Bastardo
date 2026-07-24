import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from agent.config import load_config, normalize_harness_url
from agent.client import HarnessClient
from agent.heartbeat import HeartbeatLoop
from agent.job_runner import JobRunner
from agent.registry import AdapterRegistry
from agent.adapters.ollama import OllamaAdapter
from agent.adapters.blender import BlenderCLIAdapter
from agent.updater import WorkerUpdateExecutor
from agent.capabilities import discover_worker_capabilities

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TOKEN_FILE_ENV = "OEB_WORKER_TOKEN_FILE"
HARNESS_URL_ENV = "OEB_HARNESS_URL"
ENROLLMENT_TOKEN_ENV = "OEB_ENROLLMENT_TOKEN"


def _token_path(cfg) -> Path:
    return Path(os.path.expanduser(cfg.token_file))


def _load_token(cfg) -> str:
    p = _token_path(cfg)
    if p.exists():
        return p.read_text().strip()
    return ""


def _save_token(cfg, token: str) -> None:
    p = _token_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token)
    p.chmod(0o600)
    log.info("Worker token saved to %s", p)


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _detect_primary_ip(harness_url: str) -> str:
    parsed = urlparse(normalize_harness_url(harness_url))
    host = parsed.hostname or "8.8.8.8"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, port))
            ip_address = sock.getsockname()[0]
            if ip_address and not ip_address.startswith("127."):
                return ip_address
    except OSError:
        pass

    try:
        ip_address = socket.gethostbyname(socket.gethostname())
        return "" if ip_address.startswith("127.") else ip_address
    except OSError:
        return ""


def _registration_resources(resources: dict, harness_url: str) -> dict:
    enriched = dict(resources or {})
    enriched.setdefault("hostname", socket.gethostname())
    if not any(enriched.get(key) for key in ("ip_address", "primary_ip", "host_ip")):
        if ip_address := _detect_primary_ip(harness_url):
            enriched["ip_address"] = ip_address
    return enriched


async def run(config_path: str) -> None:
    cfg = load_config(config_path)

    # Env overrides
    if url := os.environ.get(HARNESS_URL_ENV):
        cfg.harness_url = normalize_harness_url(url)
    if token := os.environ.get(ENROLLMENT_TOKEN_ENV):
        cfg.enrollment_token = token

    if not cfg.harness_url:
        log.error("harness_url not set (config or OEB_HARNESS_URL env var)")
        sys.exit(1)

    verified_capabilities, capability_resources = discover_worker_capabilities(cfg)
    cfg.capabilities = verified_capabilities
    registration_resources = _registration_resources(capability_resources, cfg.harness_url)
    worker_token = _load_token(cfg)
    git_sha = _git_sha()
    client = HarnessClient(
        base_url=cfg.harness_url,
        worker_token=worker_token,
        enrollment_token=cfg.enrollment_token,
    )

    # Register (always re-registers to refresh capabilities; gets a new token).
    # Retries until the server is reachable so the agent survives a cold start
    # where the harness comes up after the worker.
    if cfg.enrollment_token:
        retry_delay = 5
        while True:
            try:
                log.info("Registering worker %s with harness...", cfg.worker_id)
                worker_token = await client.register(
                    worker_id=cfg.worker_id,
                    platform=cfg.platform,
                    agent_version=cfg.agent_version,
                    git_sha=git_sha or None,
                    capabilities=cfg.capabilities,
                    resources=registration_resources,
                )
                client.set_worker_token(worker_token)
                _save_token(cfg, worker_token)
                log.info("Registration complete for worker %s", cfg.worker_id)
                break
            except Exception as exc:
                log.warning("Registration failed (%s) — retrying in %ds", exc, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
    elif not worker_token:
        log.error("No worker token and no enrollment token — cannot authenticate")
        sys.exit(1)

    # Build adapter registry
    registry = AdapterRegistry()
    registry.register(OllamaAdapter(cfg.adapters.ollama))
    registry.register(BlenderCLIAdapter(
        cfg.adapters.blender,
        output_root=cfg.output_root,
        workspace_root=cfg.workspace_root,
    ))

    updater = WorkerUpdateExecutor(cfg)
    update_task: asyncio.Task | None = None

    async def _run_update(target_git_sha: str | None) -> None:
        nonlocal git_sha
        heartbeat.set_update_state("applying")
        result = await updater.apply(target_git_sha=target_git_sha)
        if result.git_sha:
            git_sha = result.git_sha
            heartbeat.set_git_sha(git_sha)
        if result.success:
            heartbeat.set_update_state("complete")
            log.info("Worker update complete: %s", result.message)
        else:
            heartbeat.set_update_state("failed", result.error or "Worker update failed")
            log.error("Worker update failed: %s", result.error)

    def _on_update_instruction(instruction: dict) -> None:
        nonlocal update_task
        if updater.is_running or (update_task and not update_task.done()):
            return
        target_git_sha = instruction.get("update_target_git_sha")
        update_state = instruction.get("update_state")
        log.info("Starting worker self-update from state=%s target=%s", update_state, target_git_sha)
        update_task = asyncio.create_task(_run_update(target_git_sha))

    heartbeat = HeartbeatLoop(
        client,
        cfg.worker_id,
        cfg.heartbeat_interval_seconds,
        git_sha=git_sha or None,
        on_update_instruction=_on_update_instruction,
    )
    runner = JobRunner(client, heartbeat, registry, cfg)

    log.info(
        "Worker %s online | capabilities: %s",
        cfg.worker_id,
        ", ".join(cfg.capabilities),
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(*_):
        log.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    hb_task = asyncio.create_task(heartbeat.run())
    run_task = asyncio.create_task(runner.run())

    await stop_event.wait()

    tasks = [hb_task, run_task]
    if update_task and not update_task.done():
        tasks.append(update_task)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("Worker %s shut down cleanly", cfg.worker_id)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <config.yml>")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    main()
