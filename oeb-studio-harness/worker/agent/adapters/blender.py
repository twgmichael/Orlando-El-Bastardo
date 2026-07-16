import logging
import re
import shlex
import subprocess
from pathlib import Path
from agent.adapters.base import Adapter, AdapterResult
from agent.config import BlenderAdapterConfig

log = logging.getLogger(__name__)

BLENDER_CAPABILITIES = {
    "blender.preview_render",
    "blender.final_render",
    "blender.command_line",
}

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
        blend_file = payload.get("blend_file")
        script_file = payload.get("script_file")

        if blend_file and script_file:
            return AdapterResult(success=False, error="payload must specify blend_file or script_file, not both")
        if blend_file:
            return self._execute_blend(payload, job.get("id", ""))
        if script_file:
            return self._execute_script(payload, job.get("id", ""))
        return AdapterResult(success=False, error="payload requires blend_file or script_file")

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

        log_output, returncode = self._run(cmd)
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
            out.parent.mkdir(parents=True, exist_ok=True)

        cmd = [self._cfg.executable, "--background", "--python", str(script)]
        script_args = payload.get("script_args")
        if script_args:
            cmd += ["--"] + [self._resolve_path(str(a), job_id=job_id) for a in script_args]

        log_output, returncode = self._run(cmd, cwd=cwd)
        if returncode != 0:
            return AdapterResult(success=False, error=f"Blender exited {returncode}", log_output=log_output)

        rendered: list[Path] = []
        artifact_paths = payload.get("artifact_paths") or []
        if artifact_paths:
            for artifact_path in artifact_paths:
                resolved = self._resolve_runtime_path(str(artifact_path), "artifact_path", cwd=cwd, job_id=job_id)
                if resolved.exists():
                    rendered.append(resolved)
        elif out:
            rendered = sorted(out.parent.glob(f"{out.stem}*")) or ([out] if out.exists() else [])

        is_preview = payload.get("_preview", False)
        return AdapterResult(
            success=True,
            log_output=log_output,
            artifacts=rendered,
            artifact_type=payload.get("artifact_type") or ("preview_render" if is_preview else "final_render"),
            output_summary={"script_file": str(script), "frames_rendered": len(rendered)},
        )

    def _run(self, cmd: list[str], cwd: str | None = None) -> tuple[str, int]:
        log.info("Running Blender: %s", shlex.join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._cfg.timeout_seconds, cwd=cwd)
            return proc.stdout + proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "Blender render timed out", -1
        except FileNotFoundError:
            return f"Blender executable not found: {self._cfg.executable!r}", -1
