import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.client import HarnessClient
from agent.heartbeat import HeartbeatLoop
from agent.registry import AdapterRegistry
from agent.artifacts import artifact_info
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
            last_progress_frame_uploaded = 0
            while True:
                await asyncio.sleep(lease_seconds * LEASE_RENEW_THRESHOLD)
                try:
                    await self._client.renew_lease(job_id)
                    progress = self._scene_render_progress(job)
                    if progress:
                        await self._client.report_progress(job_id, progress)
                        last_progress_frame_uploaded = await self._upload_scene_progress_frame(
                            job,
                            progress,
                            last_progress_frame_uploaded,
                        )
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
        result_summary = result.output_summary or {}
        artifact_views = result_summary.get("artifact_views") or {}
        is_asset_review = result_summary.get("job_type") == "asset.review_render"
        is_scene_render = result_summary.get("job_type") == "scene.render" or payload.get("job_type") == "scene.render"
        requested_views = set((payload or {}).get("views") or result_summary.get("views") or [])
        for artifact_path in result.artifacts:
            try:
                artifact_file = Path(artifact_path)
                info = artifact_info(artifact_file)
                review_metadata = {}
                if is_asset_review:
                    review_metadata = {
                        "job_type": result_summary.get("job_type"),
                        "asset_id": result_summary.get("asset_id"),
                        "asset_path": result_summary.get("asset_path"),
                        "quality": result_summary.get("quality"),
                        "view": artifact_views.get(artifact_file.name),
                    }
                elif is_scene_render:
                    review_metadata = {
                        "job_type": "scene.render",
                        "scene_name": result_summary.get("scene_name") or payload.get("scene_name"),
                        "script_path": payload.get("script_path"),
                        "quality": result_summary.get("quality") or payload.get("quality"),
                        "phase": "complete",
                    }
                try:
                    reg = await self._client.upload_artifact_file(
                        job_id=job_id,
                        artifact_type=result.artifact_type or "output",
                        artifact_path=artifact_file,
                        review_metadata=review_metadata,
                        **info,
                    )
                except Exception:
                    if is_asset_review or is_scene_render:
                        label = "Scene render" if is_scene_render else "Review render"
                        reason = f"{label} artifact byte upload failed for {artifact_file.name}"
                        log.exception("%s; failing job %s", reason, job_id)
                        await self._client.fail_job(
                            job_id,
                            reason=reason,
                            log_output=result.log_output,
                        )
                        return
                    log.warning(
                        "Artifact byte upload failed for %s; falling back to metadata registration",
                        artifact_file,
                        exc_info=True,
                    )
                    reg = await self._client.register_artifact(
                        job_id=job_id,
                        artifact_type=result.artifact_type or "output",
                        storage_path=str(artifact_file),
                        review_metadata=review_metadata,
                        **info,
                    )
                uploaded.append(reg)
                log.info("Uploaded artifact %s for job %s", artifact_file.name, job_id)
            except Exception:
                log.exception("Failed to register artifact %s", artifact_path)
                if is_asset_review or is_scene_render:
                    await self._client.fail_job(
                        job_id,
                        reason=f"Render artifact registration failed for {artifact_path}",
                        log_output=result.log_output,
                    )
                    return

        output_summary = {
            "adapter": adapter.name,
            "artifacts": [a["id"] for a in uploaded],
            **result_summary,
        }
        if output_summary.get("job_type") == "asset.review_render":
            if requested_views:
                uploaded_views = {
                    (a.get("review_metadata") or {}).get("view") or artifact_views.get(a["filename"])
                    for a in uploaded
                    if a.get("provenance") == "uploaded"
                }
                missing_views = sorted(view for view in requested_views if view not in uploaded_views)
                output_summary["missing_views"] = missing_views
                output_summary["gallery_ready"] = not missing_views
                if missing_views:
                    await self._client.fail_job(
                        job_id,
                        reason=f"Review render missing uploaded views: {', '.join(missing_views)}",
                        log_output=result.log_output,
                    )
                    return

            public_base = (
                self._config.artifact_public_base_url
                or self._config.harness_url
                or self._client.base_url
            ).rstrip("/")
            asset_id = output_summary.get("asset_id")
            output_summary["gallery_url"] = f"{public_base}/review/assets/{asset_id}" if asset_id else None
            output_summary["artifact_urls"] = [
                {
                    "id": a["id"],
                    "filename": a["filename"],
                    "view": (a.get("review_metadata") or {}).get("view") or artifact_views.get(a["filename"]),
                    "url": a.get("public_url") or f"{public_base}/review/artifacts/{a['id']}",
                }
                for a in uploaded
            ]

        if is_scene_render:
            public_base = (
                self._config.artifact_public_base_url
                or self._config.harness_url
                or self._client.base_url
            ).rstrip("/")
            output_summary["scene_render_url"] = f"{public_base}/review/scene-renders/{job_id}"
            output_summary["artifact_urls"] = [
                {
                    "id": a["id"],
                    "filename": a["filename"],
                    "url": a.get("public_url") or f"{public_base}/review/artifacts/{a['id']}",
                }
                for a in uploaded
            ]

        completed_job = await self._client.complete_job(
            job_id,
            log_output=result.log_output,
            output_summary=output_summary,
        )
        log.info("Completed job %s with server status %s", job_id, completed_job.get("status"))

    def _resolve_payload_path(self, raw: str, job_id: str) -> Path:
        resolved = raw.replace("{output_root}", self._config.output_root)
        resolved = resolved.replace("{workspace_root}", self._config.workspace_root)
        resolved = resolved.replace("{job_id}", job_id)
        return Path(resolved)

    def _scene_render_progress(self, job: dict) -> dict | None:
        payload = job.get("payload") or {}
        if payload.get("job_type") != "scene.render":
            return None

        job_id = job["id"]
        frames_dir_raw = payload.get("frames_dir")
        if frames_dir_raw:
            frames_dir = self._resolve_payload_path(str(frames_dir_raw), job_id)
        elif payload.get("output_path"):
            output_path = self._resolve_payload_path(str(payload["output_path"]), job_id)
            frames_dir = output_path.with_name(f"{output_path.stem}_frames")
        else:
            return None

        frame_paths = sorted(frames_dir.glob("*.png")) if frames_dir.exists() else []
        frames_rendered = len(frame_paths)
        total_frames = payload.get("expected_frames")
        now = datetime.now(timezone.utc)
        created_at = self._parse_datetime(job.get("created_at")) or now
        elapsed_seconds = max(0.0, (now - created_at).total_seconds())
        latest_frame = frame_paths[-1] if frame_paths else None
        last_frame_at = None
        seconds_since_last_frame = None
        if latest_frame:
            last_frame_at_dt = datetime.fromtimestamp(latest_frame.stat().st_mtime, tz=timezone.utc)
            last_frame_at = last_frame_at_dt.isoformat()
            seconds_since_last_frame = max(0.0, (now - last_frame_at_dt).total_seconds())

        phase = "rendering_frames" if frames_rendered else "starting"
        output_path = self._resolve_payload_path(str(payload["output_path"]), job_id) if payload.get("output_path") else None
        if output_path and output_path.exists():
            phase = "encoding_video" if frames_rendered else "starting"

        seconds_per_frame = elapsed_seconds / frames_rendered if frames_rendered else None
        eta_seconds = None
        message = None
        estimate_source = "current_render" if seconds_per_frame else "insufficient_data"
        if seconds_per_frame and total_frames:
            remaining_frames = max(0, int(total_frames) - frames_rendered)
            eta_seconds = round(remaining_frames * seconds_per_frame)
        elif not frames_rendered:
            initial = payload.get("initial_progress") if isinstance(payload.get("initial_progress"), dict) else {}
            eta_seconds = initial.get("eta_seconds")
            estimate_source = initial.get("estimate_source") or estimate_source
            message = initial.get("message")
        warning = None
        start_warning_seconds = int(payload.get("progress_start_warning_seconds") or 300)
        stale_frame_seconds = int(payload.get("progress_stale_frame_seconds") or 300)
        if not frames_rendered and elapsed_seconds >= start_warning_seconds:
            warning = (
                "No rendered frames yet; this may be a long final-render startup, "
                "or the job may be stalled before frame output begins."
            )
        elif seconds_since_last_frame is not None and seconds_since_last_frame >= stale_frame_seconds:
            warning = "No new frame has landed recently; render progress may be stalled."

        progress = {
            "phase": phase,
            "quality": payload.get("quality"),
            "frames_rendered": frames_rendered,
            "frames_dir": str(frames_dir),
            "elapsed_seconds": round(elapsed_seconds, 1),
            "seconds_per_frame": round(seconds_per_frame, 3) if seconds_per_frame else None,
            "eta_seconds": eta_seconds,
            "estimate_source": estimate_source,
            "last_frame_at": last_frame_at,
            "seconds_since_last_frame": round(seconds_since_last_frame, 1) if seconds_since_last_frame is not None else None,
            "latest_frame_path": str(latest_frame) if latest_frame else None,
            "message": message,
            "warning": warning,
        }
        if total_frames:
            progress["total_frames"] = int(total_frames)
            progress["percent"] = min(100, round(frames_rendered * 100 / int(total_frames), 1))
        else:
            progress["total_frames"] = None
            progress["percent"] = None
        return progress

    def _parse_datetime(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    async def _upload_scene_progress_frame(
        self,
        job: dict,
        progress: dict,
        last_uploaded_frame: int,
    ) -> int:
        payload = job.get("payload") or {}
        if payload.get("job_type") != "scene.render":
            return last_uploaded_frame
        frames_rendered = int(progress.get("frames_rendered") or 0)
        latest_frame_path = progress.get("latest_frame_path")
        if not frames_rendered or not latest_frame_path:
            return last_uploaded_frame

        interval = int(payload.get("progress_frame_interval") or 24)
        should_upload = frames_rendered == 1 or frames_rendered - last_uploaded_frame >= interval
        if not should_upload:
            return last_uploaded_frame

        frame_path = Path(latest_frame_path)
        if not frame_path.exists():
            return last_uploaded_frame

        try:
            info = artifact_info(frame_path)
            await self._client.upload_artifact_file(
                job_id=job["id"],
                artifact_type="scene.progress_frame",
                artifact_path=frame_path,
                review_metadata={
                    "job_type": "scene.render",
                    "scene_name": payload.get("scene_name"),
                    "script_path": payload.get("script_path"),
                    "quality": payload.get("quality"),
                    "frame": frames_rendered,
                    "total_frames": progress.get("total_frames"),
                    "percent": progress.get("percent"),
                    "phase": progress.get("phase"),
                },
                **info,
            )
            return frames_rendered
        except Exception:
            log.warning(
                "Scene progress-frame upload failed for job %s frame %s",
                job.get("id"),
                frames_rendered,
                exc_info=True,
            )
            return last_uploaded_frame
