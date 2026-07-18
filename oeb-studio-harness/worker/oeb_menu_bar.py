"""
OEB Worker menu bar app.

Runs the harness worker agent in a background thread and surfaces its
state in the macOS menu bar via rumps.

Usage:
    OEB_HARNESS_URL=https://harness.local OEB_ENROLLMENT_TOKEN=<tok> \
    python oeb_menu_bar.py config-examples/mac-mini.yml
"""

import asyncio
import logging
import os
import queue
import sys
import threading
import webbrowser
from pathlib import Path

import rumps

# Icons live alongside this file in icons/
_HERE = Path(__file__).parent
_ICON_IDLE = str(_HERE / "icons" / "icon-idle.png")
_ICON_BUSY = str(_HERE / "icons" / "icon-busy.png")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


class OEBWorkerApp(rumps.App):
    def __init__(self, harness_url: str):
        super().__init__("", icon=_ICON_IDLE, template=True, quit_button=None)
        self._harness_url = harness_url
        self._state_queue: queue.Queue = queue.Queue()

        self._status_item = rumps.MenuItem("Starting worker...")
        self._open_item = rumps.MenuItem("Open Dashboard", callback=self._open_dashboard)
        self._quit_item = rumps.MenuItem("Quit", callback=self._quit)

        self.menu = [
            self._status_item,
            None,
            self._open_item,
            None,
            self._quit_item,
        ]

        rumps.Timer(self._poll_state, 1).start()

    # --- callbacks from worker thread (thread-safe) ---

    def notify_busy(self, job_id: str, job_title: str) -> None:
        self._state_queue.put(("busy", job_id, job_title))

    def notify_idle(self) -> None:
        self._state_queue.put(("idle",))

    def notify_status(self, message: str) -> None:
        self._state_queue.put(("status", message))

    def notify_error(self, message: str) -> None:
        self._state_queue.put(("error", message))

    # --- rumps timer: drain queue on main thread ---

    def _poll_state(self, _timer) -> None:
        try:
            while True:
                msg = self._state_queue.get_nowait()
                if msg[0] == "busy":
                    _, job_id, job_title = msg
                    self.icon = _ICON_BUSY
                    label = job_title or job_id
                    self._status_item.title = f"Running: {label}"
                elif msg[0] == "idle":
                    self.icon = _ICON_IDLE
                    self._status_item.title = "Idle"
                elif msg[0] == "status":
                    _, message = msg
                    self.icon = _ICON_IDLE
                    self._status_item.title = message
                elif msg[0] == "error":
                    _, message = msg
                    self.icon = _ICON_BUSY
                    self._status_item.title = f"Worker issue: {message}"
        except queue.Empty:
            pass

    def _open_dashboard(self, _sender) -> None:
        webbrowser.open(self._harness_url)

    def _quit(self, _sender) -> None:
        rumps.quit_application()


def _run_worker(config_path: str, app: OEBWorkerApp) -> None:
    from agent.config import load_config, normalize_harness_url
    from agent.client import HarnessClient
    from agent.heartbeat import HeartbeatLoop
    from agent.job_runner import JobRunner
    from agent.registry import AdapterRegistry
    from agent.adapters.ollama import OllamaAdapter
    from agent.adapters.blender import BlenderCLIAdapter
    from agent.main import _load_token, _save_token

    async def run():
        cfg = load_config(config_path)

        if url := os.environ.get("OEB_HARNESS_URL"):
            cfg.harness_url = normalize_harness_url(url)
        if token := os.environ.get("OEB_ENROLLMENT_TOKEN"):
            cfg.enrollment_token = token

        worker_token = _load_token(cfg)
        client = HarnessClient(
            base_url=cfg.harness_url,
            worker_token=worker_token,
            enrollment_token=cfg.enrollment_token,
        )

        if cfg.enrollment_token:
            import asyncio as _asyncio
            retry_delay = 5
            while True:
                try:
                    app.notify_status(f"Registering {cfg.worker_id}...")
                    worker_token = await client.register(
                        worker_id=cfg.worker_id,
                        platform=cfg.platform,
                        agent_version=cfg.agent_version,
                        capabilities=cfg.capabilities,
                        resources=cfg.resources,
                    )
                    client.set_worker_token(worker_token)
                    _save_token(cfg, worker_token)
                    app.notify_status(f"{cfg.worker_id} online")
                    break
                except Exception as exc:
                    app.notify_error(f"registration failed: {exc}")
                    logging.warning("Registration failed (%s) — retrying in %ds", exc, retry_delay)
                    await _asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
        elif not worker_token:
            app.notify_error("missing worker token/enrollment token")
            return

        registry = AdapterRegistry()
        registry.register(OllamaAdapter(cfg.adapters.ollama))
        registry.register(BlenderCLIAdapter(
            cfg.adapters.blender,
            output_root=cfg.output_root,
            workspace_root=cfg.workspace_root,
        ))

        heartbeat = HeartbeatLoop(
            client,
            cfg.worker_id,
            cfg.heartbeat_interval_seconds,
            on_busy=app.notify_busy,
            on_idle=app.notify_idle,
            on_error=app.notify_error,
        )
        runner = JobRunner(client, heartbeat, registry, cfg)

        hb_task = asyncio.create_task(heartbeat.run())
        run_task = asyncio.create_task(runner.run())
        await asyncio.gather(hb_task, run_task)

    try:
        asyncio.run(run())
    except Exception as exc:
        logging.exception("Worker thread stopped")
        app.notify_error(f"stopped: {exc}")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <config.yml>")
        sys.exit(1)

    config_path = sys.argv[1]
    from agent.config import normalize_harness_url

    harness_url = normalize_harness_url(os.environ.get("OEB_HARNESS_URL", "http://localhost"))

    app = OEBWorkerApp(harness_url=harness_url)

    worker_thread = threading.Thread(
        target=_run_worker,
        args=(config_path, app),
        daemon=True,
        name="oeb-worker",
    )
    worker_thread.start()

    app.run()


if __name__ == "__main__":
    main()
