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

ASSET_REVIEW_JOB_TYPE = "asset.review_render"
ASSET_REVIEW_VIEWS = ("top", "bottom", "left", "right", "front", "back", "action")

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
        if quality not in {"preview", "final"}:
            return AdapterResult(success=False, error="asset.review_render quality must be preview or final")

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
            target_dir = out if out.suffix == "" else out.parent
            target_dir.mkdir(parents=True, exist_ok=True)

        cmd = [self._cfg.executable, "--background"]
        if payload.get("factory_startup"):
            cmd.append("--factory-startup")
        cmd += ["--python", str(script)]
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
