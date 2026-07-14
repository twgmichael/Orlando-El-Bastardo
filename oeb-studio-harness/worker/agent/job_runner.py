import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.client import HarnessClient
from agent.heartbeat import HeartbeatLoop
from agent.registry import AdapterRegistry
from agent.artifacts import copy_to_store, artifact_info
from agent.config import WorkerConfig

log = logging.getLogger(__name__)

# Renew the lease when less than this fraction of the lease window remains
LEASE_RENEW_THRESHOLD = 0.4


class JobRunner:
    def __init__(
        self,
        client: HarnessClient,
        heartbeat: HeartbeatLoop,
        registry: AdapterRegistry,
        config: WorkerConfig,
    ):
        self._client = client
        self._heartbeat = heartbeat
        self._registry = registry
        self._config = config

    async def run(self) -> None:
        while True:
            try:
                await self._poll_and_execute()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Error in job runner poll")
            await asyncio.sleep(self._config.poll_interval_seconds)

    async def _poll_and_execute(self) -> None:
        jobs = await self._client.get_eligible_jobs()
        if not jobs:
            return

        job = jobs[0]
        job_id = job["id"]

        try:
            claim = await self._client.claim_job(job_id)
        except Exception:
            log.debug("Failed to claim job %s (likely claimed by another worker)", job_id)
            return

        lease = claim["lease"]
        lease_expires = datetime.fromisoformat(lease["expires_at"])

        self._heartbeat.set_busy(job_id, job.get("title", ""))
        log.info("Claimed job %s: %s", job_id, job["title"])

        try:
            await self._execute(job, lease_expires)
        finally:
            self._heartbeat.set_idle()

    async def _execute(self, job: dict, lease_expires: datetime) -> None:
        job_id = job["id"]
        payload = job.get("payload", {})

        # Find adapter
        adapter = self._registry.find_adapter(job)
        if not adapter:
            await self._client.fail_job(
                job_id,
                reason=f"No adapter registered for job capabilities: {job.get('required_capabilities')}",
            )
            return

        log.info("Running adapter %s for job %s", adapter.name, job_id)

        # Run adapter with concurrent lease renewal
        log_lines: list[str] = []
        result = None

        async def renew_loop():
            lease_seconds = self._config.heartbeat_interval_seconds * 2
            while True:
                await asyncio.sleep(lease_seconds * LEASE_RENEW_THRESHOLD)
                try:
                    await self._client.renew_lease(job_id)
                    log.debug("Renewed lease for job %s", job_id)
                except Exception:
                    log.warning("Lease renewal failed for job %s", job_id, exc_info=True)

        renew_task = asyncio.create_task(renew_loop())
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, adapter.execute, job
            )
        except Exception as exc:
            log.exception("Adapter raised exception for job %s", job_id)
            await self._client.fail_job(job_id, reason=str(exc))
            return
        finally:
            renew_task.cancel()

        if not result.success:
            await self._client.fail_job(
                job_id,
                reason=result.error or "Adapter reported failure",
                log_output=result.log_output,
            )
            return

        # Upload artifacts
        uploaded: list[dict] = []
        for artifact_path in result.artifacts:
            try:
                stored = copy_to_store(
                    Path(artifact_path),
                    self._config.artifact_store_root,
                    job_id,
                )
                info = artifact_info(stored)
                reg = await self._client.register_artifact(
                    job_id=job_id,
                    artifact_type=result.artifact_type or "output",
                    storage_path=str(stored),
                    **info,
                )
                uploaded.append(reg)
                log.info("Registered artifact %s for job %s", stored.name, job_id)
            except Exception:
                log.exception("Failed to register artifact %s", artifact_path)

        await self._client.complete_job(
            job_id,
            log_output=result.log_output,
            output_summary={
                "adapter": adapter.name,
                "artifacts": [a["id"] for a in uploaded],
                **(result.output_summary or {}),
            },
        )
        log.info("Completed job %s", job_id)
