import logging
from typing import Optional
from pathlib import Path
import json
import httpx

log = logging.getLogger(__name__)


def _normalize_base_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    if not url:
        raise ValueError("Harness base URL is empty; set harness_url or OEB_HARNESS_URL")
    return url


class HarnessClient:
    def __init__(self, base_url: str, worker_token: str = "", enrollment_token: str = ""):
        self._base = _normalize_base_url(base_url)
        self._worker_token = worker_token
        self._enrollment_token = enrollment_token

    @property
    def base_url(self) -> str:
        return self._base

    def _worker_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._worker_token}"}

    def _enrollment_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._enrollment_token}"}

    def set_worker_token(self, token: str) -> None:
        self._worker_token = token

    async def register(
        self,
        worker_id: str,
        platform: str,
        agent_version: str,
        git_sha: str | None,
        capabilities: list[str],
        resources: dict,
    ) -> str:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/workers/register",
                json={
                    "worker_id": worker_id,
                    "platform": platform,
                    "agent_version": agent_version,
                    "git_sha": git_sha,
                    "capabilities": capabilities,
                    "resources": resources,
                },
                headers=self._enrollment_headers(),
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["worker_token"]

    async def heartbeat(
        self,
        worker_id: str,
        status: str,
        current_job_id: Optional[str] = None,
        git_sha: Optional[str] = None,
        update_state: Optional[str] = None,
        update_last_error: Optional[str] = None,
        cpu_load_percent: Optional[float] = None,
        gpu_load_percent: Optional[float] = None,
        free_ram_gb: Optional[float] = None,
        free_vram_gb: Optional[float] = None,
    ) -> None:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/workers/{worker_id}/heartbeat",
                json={
                    "status": status,
                    "current_job_id": current_job_id,
                    "git_sha": git_sha,
                    "update_state": update_state,
                    "update_last_error": update_last_error,
                    "cpu_load_percent": cpu_load_percent,
                    "gpu_load_percent": gpu_load_percent,
                    "free_ram_gb": free_ram_gb,
                    "free_vram_gb": free_vram_gb,
                },
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def get_eligible_jobs(self) -> list[dict]:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.get(
                f"{self._base}/api/v1/jobs/eligible",
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def claim_job(self, job_id: str) -> dict:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/claim",
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def renew_lease(self, job_id: str) -> dict:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/renew-lease",
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def report_progress(self, job_id: str, progress: dict) -> dict:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/progress",
                json={"progress": progress},
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def complete_job(
        self,
        job_id: str,
        log_output: Optional[str] = None,
        output_summary: Optional[dict] = None,
    ) -> dict:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/complete",
                json={"log_output": log_output, "output_summary": output_summary},
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def fail_job(
        self,
        job_id: str,
        reason: str,
        log_output: Optional[str] = None,
    ) -> None:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/fail",
                json={"reason": reason, "log_output": log_output},
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()

    async def register_artifact(
        self,
        job_id: str,
        artifact_type: str,
        filename: str,
        storage_path: str,
        public_url: Optional[str] = None,
        size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        checksum_sha256: Optional[str] = None,
        review_metadata: Optional[dict] = None,
        attempt_id: Optional[str] = None,
    ) -> dict:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/artifacts",
                json={
                    "artifact_type": artifact_type,
                    "filename": filename,
                    "storage_path": storage_path,
                    "public_url": public_url,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                    "checksum_sha256": checksum_sha256,
                    "review_metadata": review_metadata or {},
                    "attempt_id": attempt_id,
                },
                headers=self._worker_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def upload_artifact_file(
        self,
        job_id: str,
        artifact_path: Path,
        artifact_type: str,
        filename: str,
        size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        checksum_sha256: Optional[str] = None,
        review_metadata: Optional[dict] = None,
        provenance: str = "uploaded",
    ) -> dict:
        params = {
            "artifact_type": artifact_type,
            "filename": filename,
            "provenance": provenance,
        }
        if mime_type:
            params["mime_type"] = mime_type
        if checksum_sha256:
            params["checksum_sha256"] = checksum_sha256
        if review_metadata:
            params["review_metadata_json"] = json.dumps(review_metadata, separators=(",", ":"))

        async with httpx.AsyncClient(verify=False) as c:
            r = await c.post(
                f"{self._base}/api/v1/jobs/{job_id}/artifact-files",
                params=params,
                content=artifact_path.read_bytes(),
                headers=self._worker_headers(),
                timeout=120,
            )
            r.raise_for_status()
            return r.json()
