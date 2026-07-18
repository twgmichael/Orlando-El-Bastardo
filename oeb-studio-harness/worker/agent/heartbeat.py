import asyncio
import logging
from typing import Optional, Callable
from agent.client import HarnessClient

log = logging.getLogger(__name__)


class HeartbeatLoop:
    def __init__(
        self,
        client: HarnessClient,
        worker_id: str,
        interval: int = 20,
        on_busy: Optional[Callable[[str, str], None]] = None,
        on_idle: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self._client = client
        self._worker_id = worker_id
        self._interval = interval
        self._current_job_id: Optional[str] = None
        self._status: str = "online"
        self._on_busy = on_busy
        self._on_idle = on_idle
        self._on_error = on_error

    def set_busy(self, job_id: str, job_title: str = "") -> None:
        self._current_job_id = job_id
        self._status = "busy"
        if self._on_busy:
            self._on_busy(job_id, job_title)

    def set_idle(self) -> None:
        self._current_job_id = None
        self._status = "online"
        if self._on_idle:
            self._on_idle()

    async def run(self) -> None:
        failures = 0
        while True:
            try:
                await self._client.heartbeat(
                    worker_id=self._worker_id,
                    status=self._status,
                    current_job_id=self._current_job_id,
                )
                failures = 0
            except Exception:
                failures += 1
                log.warning("Heartbeat failed", exc_info=True)
                if self._on_error and failures >= 2:
                    self._on_error(f"Heartbeat failed ({failures}x)")
            await asyncio.sleep(self._interval)
