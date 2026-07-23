import logging
import re
import shlex
import subprocess
import time
from pathlib import Path
from agent.adapters.base import Adapter, AdapterResult
from agent.config import BlenderAdapterConfig

log = logging.getLogger(__name__)

BLENDER_CAPABILITIES = {
    "blender.preview_render",
    "blender.final_render",
    "blender.command_line",
}

ASSET_REVIEW_JOB_TYPE = "asset.review_render"
ASSET_REVIEW_VIEWS = ("top", "bottom", "left", "right", "front", "back", "action")
LOG_TAIL_LINES = 80

_PATH_TRAVERSAL = re.compile(r"\.\.")


def _safe_path(raw: str, label: str) -> Path:
    if _PATH_TRAVERSAL.search(raw):
        raise ValueError(f"{label} contains path traversal: {raw!r}")
    return Path(raw)


class BlenderCLIAdapter(Adapter):
    name = "blender"

    def __init__(self, cfg: BlenderAdapterConfig, output_root: str = "", workspace_root: str = "."):
        self._cfg = cfg
        self._output_root = output_root
        self._workspace_root = workspace_root

    def can_handle(self, job: dict) -> bool:
        caps = set(job.get("required_capabilities") or [])
        return bool(caps & BLENDER_CAPABILITIES)

    def _resolve_path(self, raw: str, job_id: str = "") -> str:
        if self._output_root:
            raw = raw.replace("{output_root}", self._output_root)
        else:
            raw = raw.replace("{output_root}/", "").replace("{output_root}", "")
        raw = raw.replace("{workspace_root}", self._workspace_root)
        raw = raw.replace("{job_id}", job_id)
        return raw

    def _resolve_existing_path(self, raw: str, label: str, cwd: str | None = None, job_id: str = "") -> Path:
        resolved = _safe_path(self._resolve_path(raw, job_id=job_id), label)
        if cwd and not resolved.is_absolute():
            cwd_path = _safe_path(self._resolve_path(cwd, job_id=job_id), "cwd")
            if not cwd_path.is_absolute():
                cwd_path = cwd_path.resolve()
            return cwd_path / resolved
        return resolved

    def _resolve_runtime_path(self, raw: str, label: str, cwd: str | None = None, job_id: str = "") -> Path:
        resolved = _safe_path(self._resolve_path(raw, job_id=job_id), label)
        if cwd and not resolved.is_absolute():
            cwd_path = _safe_path(self._resolve_path(cwd, job_id=job_id), "cwd")
            if not cwd_path.is_absolute():
                cwd_path = cwd_path.resolve()
            return cwd_path / resolved
        return resolved

    def execute(self, job: dict) -> AdapterResult:
        payload = job.get("payload", {})
        if payload.get("job_type") == ASSET_REVIEW_JOB_TYPE:
            return self._execute_asset_review(payload, job.get("id", ""))

        blend_file = payload.get("blend_file")
        script_file = payload.get("script_file")

        if blend_file and script_file:
            return AdapterResult(success=False, error="payload must specify blend_file or script_file, not both")
        if blend_file:
            return self._execute_blend(payload, job.get("id", ""))
        if script_file:
            return self._execute_script(payload, job.get("id", ""))
        return AdapterResult(success=False, error="payload requires blend_file or script_file")

    def _execute_asset_review(self, payload: dict, job_id: str = "") -> AdapterResult:
        asset_path = payload.get("asset_path")
        asset_id = payload.get("asset_id")
        if not asset_path:
            return AdapterResult(success=False, error="asset.review_render payload requires asset_path")
        if not asset_id:
            return AdapterResult(success=False, error="asset.review_render payload requires asset_id")

        quality = payload.get("quality") or "preview"
        if quality not in {"draft", "preview", "final"}:
            return AdapterResult(success=False, error="asset.review_render quality must be draft, preview, or final")

        raw_views = payload.get("views") or ASSET_REVIEW_VIEWS
        if isinstance(raw_views, str):
            views = [v.strip() for v in raw_views.split(",") if v.strip()]
        else:
            views = [str(v).strip() for v in raw_views if str(v).strip()]
        invalid_views = [v for v in views if v not in ASSET_REVIEW_VIEWS]
        if invalid_views:
            return AdapterResult(success=False, error=f"Unknown asset review views: {invalid_views}")

        script_file = payload.get("script_file") or "{workspace_root}/tools/render_asset_review.py"
        cwd = payload.get("cwd") or "{workspace_root}"
        output_path = payload.get("output_path") or "{output_root}/oeb-studio-harness/review-renders/{job_id}"
        artifact_prefix = payload.get("artifact_prefix") or payload.get("output_namespace") or asset_id

        render_payload = {
            **payload,
            "script_file": script_file,
            "cwd": cwd,
            "output_path": output_path,
            "factory_startup": True,
            "artifact_type": "asset.review_render",
            "script_args": [
                "--asset", asset_path,
                "--asset-id", asset_id,
                "--views", ",".join(views),
                "--quality", quality,
                "--output-dir", output_path,
                "--artifact-prefix", artifact_prefix,
            ],
            "artifact_paths": [
                f"{output_path}/{artifact_prefix}_{view}.png"
                for view in views
            ],
        }
        for option in ("width", "height", "samples", "engine"):
            if payload.get(option) is not None:
                render_payload["script_args"].extend([f"--{option.replace('_', '-')}", str(payload[option])])

        result = self._execute_script(render_payload, job_id=job_id)
        if result.output_summary is None:
            result.output_summary = {}
        result.output_summary.update({
            "job_type": ASSET_REVIEW_JOB_TYPE,
            "asset_id": asset_id,
            "asset_path": asset_path,
            "views": views,
            "quality": quality,
            "artifact_prefix": artifact_prefix,
            "artifact_views": {
                f"{artifact_prefix}_{view}.png": view
                for view in views
            },
        })
        return result

    def _execute_blend(self, payload: dict, job_id: str = "") -> AdapterResult:
        blend_file = payload.get("blend_file")
        output_path = payload.get("output_path")
        if not output_path:
            return AdapterResult(success=False, error="payload requires output_path with blend_file")

        try:
            blend = self._resolve_existing_path(blend_file, "blend_file", job_id=job_id)
            out = self._resolve_runtime_path(output_path, "output_path", job_id=job_id)
        except ValueError as exc:
            return AdapterResult(success=False, error=str(exc))

        if not blend.exists():
            return AdapterResult(success=False, error=f"blend_file not found: {blend}")

        out.parent.mkdir(parents=True, exist_ok=True)

        start_frame = payload.get("start_frame")
        end_frame = payload.get("end_frame")
        single_frame = payload.get("frame")
        engine = payload.get("engine", "CYCLES")
        samples = payload.get("samples")
        resolution_x = payload.get("resolution_x")
        resolution_y = payload.get("resolution_y")
        render_format = payload.get("format", "PNG")

        cmd = [self._cfg.executable, "--background", str(blend)]

        if engine:
            cmd += ["--engine", engine]

        overrides: list[str] = []
        if samples:
            overrides.append(f"bpy.context.scene.cycles.samples = {int(samples)}")
        if resolution_x:
            overrides.append(f"bpy.context.scene.render.resolution_x = {int(resolution_x)}")
        if resolution_y:
            overrides.append(f"bpy.context.scene.render.resolution_y = {int(resolution_y)}")
        if overrides:
            cmd += ["--python-expr", "; ".join(["import bpy"] + overrides)]

        cmd += ["--render-output", str(out), "--render-format", render_format]

        if single_frame is not None:
            cmd += ["--render-frame", str(int(single_frame))]
        elif start_frame is not None and end_frame is not None:
            cmd += ["--frame-start", str(int(start_frame)), "--frame-end", str(int(end_frame)), "--render-anim"]
        else:
            cmd += ["--render-frame", "1"]

        timeout_seconds = self._payload_timeout_seconds(payload)
        log_output, returncode = self._run(cmd, timeout_seconds=timeout_seconds)
        if returncode != 0:
            return AdapterResult(success=False, error=f"Blender exited {returncode}", log_output=log_output)

        rendered = sorted(out.parent.glob(f"{out.stem}*")) or ([out] if out.exists() else [])
        is_preview = payload.get("_preview", False)
        return AdapterResult(
            success=True,
            log_output=log_output,
            artifacts=rendered,
            artifact_type="preview_render" if is_preview else "final_render",
            output_summary={"blend_file": str(blend), "engine": engine, "frames_rendered": len(rendered)},
        )

    def _execute_script(self, payload: dict, job_id: str = "") -> AdapterResult:
        script_file = payload.get("script_file")
        output_path = payload.get("output_path")
        cwd = self._resolve_path(payload.get("cwd"), job_id=job_id) if payload.get("cwd") else None

        try:
            script = self._resolve_existing_path(script_file, "script_file", cwd=cwd, job_id=job_id)
            out = self._resolve_runtime_path(output_path, "output_path", cwd=cwd, job_id=job_id) if output_path else None
        except ValueError as exc:
            return AdapterResult(success=False, error=str(exc))

        if not script.exists():
            return AdapterResult(success=False, error=f"script_file not found: {script}")

        if out:
            target_dir = out if out.suffix == "" else out.parent
            target_dir.mkdir(parents=True, exist_ok=True)

        cmd = [self._cfg.executable, "--background"]
        if payload.get("factory_startup"):
            cmd.append("--factory-startup")
        cmd += ["--python", str(script)]
        script_args = payload.get("script_args")
        if script_args:
            cmd += ["--"] + [self._resolve_path(str(a), job_id=job_id) for a in script_args]

        started = time.monotonic()
        timeout_seconds = self._payload_timeout_seconds(payload)
        log_output, returncode = self._run(cmd, cwd=cwd, timeout_seconds=timeout_seconds)
        elapsed_seconds = time.monotonic() - started
        if returncode != 0:
            return AdapterResult(
                success=False,
                error=f"Blender exited {returncode}",
                log_output=log_output,
                output_summary=self._script_failure_summary(
                    payload=payload,
                    job_id=job_id,
                    script=script,
                    out=out,
                    cmd=cmd,
                    cwd=cwd,
                    returncode=returncode,
                    timeout_seconds=timeout_seconds,
                    elapsed_seconds=elapsed_seconds,
                    log_output=log_output,
                ),
            )

        rendered: list[Path] = []
        artifact_paths = payload.get("artifact_paths") or []
        if artifact_paths:
            missing_artifacts: list[Path] = []
            for artifact_path in artifact_paths:
                resolved = self._resolve_runtime_path(str(artifact_path), "artifact_path", cwd=cwd, job_id=job_id)
                if resolved.exists():
                    rendered.append(resolved)
                else:
                    missing_artifacts.append(resolved)
            if missing_artifacts:
                summary = {
                    "script_file": str(script),
                    "frames_rendered": len(rendered),
                    "expected_artifacts": [str(path) for path in rendered + missing_artifacts],
                    "missing_artifacts": [str(path) for path in missing_artifacts],
                    "command": shlex.join(cmd),
                    "cwd": cwd,
                    "log_tail": self._log_tail(log_output),
                }
                return AdapterResult(
                    success=False,
                    error=f"Script completed without expected artifacts: {', '.join(path.name for path in missing_artifacts)}",
                    log_output=log_output,
                    output_summary=summary,
                )
        elif out:
            rendered = sorted(out.parent.glob(f"{out.stem}*")) or ([out] if out.exists() else [])

        is_preview = payload.get("_preview", False)
        output_summary = {"script_file": str(script), "frames_rendered": len(rendered)}
        if payload.get("job_type") == "scene.render":
            frame_count = 0
            if out:
                frames_dir = self._resolve_runtime_path(
                    str(payload.get("frames_dir") or out.with_name(f"{out.stem}_frames")),
                    "frames_dir",
                    cwd=cwd,
                    job_id=job_id,
                )
                if frames_dir.exists():
                    frame_count = len(list(frames_dir.glob("*.png")))
            seconds_per_frame = elapsed_seconds / frame_count if frame_count else None
            output_summary.update({
                "job_type": "scene.render",
                "scene_name": payload.get("scene_name"),
                "script_path": payload.get("script_path"),
                "quality": payload.get("quality"),
                "mode": payload.get("mode"),
                "output_path": str(out) if out else None,
                "frame_count": frame_count,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "seconds_per_frame": round(seconds_per_frame, 3) if seconds_per_frame else None,
                "blender_timeout_seconds": timeout_seconds,
                "blender_timeout_source": "payload" if payload.get("blender_timeout_seconds") else "adapter_default",
                "timing": {
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "frames": frame_count,
                    "seconds_per_frame": round(seconds_per_frame, 3) if seconds_per_frame else None,
                    "quality": payload.get("quality"),
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                },
                "progress": {
                    "phase": "complete",
                    "quality": payload.get("quality"),
                    "frames_rendered": frame_count,
                    "total_frames": payload.get("expected_frames"),
                    "percent": 100 if frame_count and payload.get("expected_frames") and frame_count >= int(payload["expected_frames"]) else None,
                    "seconds_per_frame": round(seconds_per_frame, 3) if seconds_per_frame else None,
                    "eta_seconds": 0,
                    "estimate_source": "current_render" if seconds_per_frame else "insufficient_data",
                },
            })
        return AdapterResult(
            success=True,
            log_output=log_output,
            artifacts=rendered,
            artifact_type=payload.get("artifact_type") or ("preview_render" if is_preview else "final_render"),
            output_summary=output_summary,
        )

    def _script_failure_summary(
        self,
        payload: dict,
        job_id: str,
        script: Path,
        out: Path | None,
        cmd: list[str],
        cwd: str | None,
        returncode: int,
        timeout_seconds: int,
        elapsed_seconds: float,
        log_output: str,
    ) -> dict:
        summary = {
            "script_file": str(script),
            "exit_code": returncode,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "blender_timeout_seconds": timeout_seconds,
            "blender_timeout_source": "payload" if payload.get("blender_timeout_seconds") else "adapter_default",
            "command": shlex.join(cmd),
            "cwd": cwd,
            "log_tail": self._log_tail(log_output),
        }
        if payload.get("job_type") == "scene.render":
            frames_dir = None
            if out:
                frames_dir = self._resolve_runtime_path(
                    str(payload.get("frames_dir") or out.with_name(f"{out.stem}_frames")),
                    "frames_dir",
                    cwd=cwd,
                    job_id=job_id,
                )
            frame_paths = sorted(frames_dir.glob("*.png")) if frames_dir and frames_dir.exists() else []
            latest_frame = frame_paths[-1] if frame_paths else None
            summary.update({
                "job_type": "scene.render",
                "scene_name": payload.get("scene_name"),
                "script_path": payload.get("script_path"),
                "quality": payload.get("quality"),
                "mode": payload.get("mode"),
                "output_path": str(out) if out else None,
                "frames_dir": str(frames_dir) if frames_dir else None,
                "frames_rendered": len(frame_paths),
                "latest_frame_path": str(latest_frame) if latest_frame else None,
                "expected_frames": payload.get("expected_frames"),
                "progress": {
                    "phase": "failed",
                    "quality": payload.get("quality"),
                    "frames_rendered": len(frame_paths),
                    "total_frames": payload.get("expected_frames"),
                    "percent": (
                        min(100, round(len(frame_paths) * 100 / int(payload["expected_frames"]), 1))
                        if frame_paths and payload.get("expected_frames")
                        else None
                    ),
                    "eta_seconds": None,
                    "estimate_source": "failed",
                    "warning": f"Blender exited {returncode}",
                },
            })
        return summary

    def _log_tail(self, log_output: str) -> str:
        lines = (log_output or "").splitlines()
        return "\n".join(lines[-LOG_TAIL_LINES:])

    def _payload_timeout_seconds(self, payload: dict) -> int:
        raw_timeout = payload.get("blender_timeout_seconds")
        if raw_timeout is None:
            return self._cfg.timeout_seconds
        try:
            timeout_seconds = int(raw_timeout)
        except (TypeError, ValueError):
            return self._cfg.timeout_seconds
        return timeout_seconds if timeout_seconds > 0 else self._cfg.timeout_seconds

    def _run(self, cmd: list[str], cwd: str | None = None, timeout_seconds: int | None = None) -> tuple[str, int]:
        effective_timeout = timeout_seconds or self._cfg.timeout_seconds
        log.info("Running Blender with timeout %ss: %s", effective_timeout, shlex.join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=effective_timeout, cwd=cwd)
            return proc.stdout + proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            partial = (stdout + stderr).strip()
            timeout_line = f"Blender render timed out after {effective_timeout}s"
            return f"{partial}\n{timeout_line}" if partial else timeout_line, -1
        except FileNotFoundError:
            return f"Blender executable not found: {self._cfg.executable!r}", -1
