import asyncio
import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent.config import WorkerConfig

log = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    success: bool
    git_sha: str | None
    message: str = ""
    error: str | None = None
    probes: dict | None = None


def _format_command_part(value: str, substitutions: dict[str, str]) -> str:
    for key, replacement in substitutions.items():
        value = value.replace("{" + key + "}", replacement)
    return value


def _command_argv(raw: str | list[str], substitutions: dict[str, str] | None = None) -> list[str]:
    substitutions = substitutions or {}
    if isinstance(raw, str):
        return shlex.split(_format_command_part(raw, substitutions))
    return [_format_command_part(str(part), substitutions) for part in raw]


def current_git_sha(workspace_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


class WorkerUpdateExecutor:
    def __init__(self, config: WorkerConfig):
        self._config = config
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def apply(self, target_git_sha: str | None = None) -> UpdateResult:
        if self._lock.locked():
            return UpdateResult(
                success=False,
                git_sha=current_git_sha(self._config.workspace_root) or None,
                error="Worker update is already applying",
            )

        async with self._lock:
            return await asyncio.to_thread(self._apply_sync, target_git_sha)

    def _apply_sync(self, target_git_sha: str | None) -> UpdateResult:
        workspace = Path(self._config.workspace_root)
        try:
            self._run_configured_commands(
                self._config.update_commands,
                self._config.update_command_timeout_seconds,
                target_git_sha=target_git_sha,
            )
            git_sha = current_git_sha(str(workspace)) or None
            probes = self._run_post_update_probes(target_git_sha=target_git_sha, git_sha=git_sha)
        except Exception as exc:
            log.exception("Worker self-update failed")
            return UpdateResult(
                success=False,
                git_sha=current_git_sha(str(workspace)) or None,
                error=str(exc),
            )

        failed = [name for name, result in probes.items() if not result.get("ok")]
        if failed:
            return UpdateResult(
                success=False,
                git_sha=git_sha,
                error=f"Post-update probes failed: {', '.join(failed)}",
                probes=probes,
            )
        return UpdateResult(
            success=True,
            git_sha=git_sha,
            message="Worker update applied and post-update probes passed",
            probes=probes,
        )

    def _command_substitutions(self, target_git_sha: str | None = None) -> dict[str, str]:
        return {
            "target_git_sha": target_git_sha or "",
            "workspace_root": self._config.workspace_root,
        }

    def _run_configured_commands(
        self,
        commands: list[str | list[str]],
        timeout_seconds: int,
        target_git_sha: str | None = None,
    ) -> None:
        substitutions = self._command_substitutions(target_git_sha)
        for raw in commands:
            argv = _command_argv(raw, substitutions)
            if not argv:
                continue
            log.info("Running worker update command: %s", shlex.join(argv))
            result = subprocess.run(
                argv,
                cwd=self._config.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            if result.returncode != 0:
                output = (result.stdout + result.stderr).strip()
                raise RuntimeError(
                    f"Update command failed ({result.returncode}): {shlex.join(argv)}"
                    + (f"\n{output[-1000:]}" if output else "")
                )

    def _run_post_update_probes(self, target_git_sha: str | None, git_sha: str | None) -> dict:
        probes = {
            "workspace_root": self._probe_workspace_root(),
            "git_sha": self._probe_git_sha(target_git_sha, git_sha),
            "capabilities": self._probe_capabilities(),
        }
        if self._has_capability_prefix("blender."):
            probes["blender"] = self._probe_blender()
        if self._has_capability_prefix("gpu."):
            probes["gpu"] = self._probe_gpu()
        probes.update(self._run_custom_probe_commands(target_git_sha=target_git_sha))
        return probes

    def _has_capability_prefix(self, prefix: str) -> bool:
        return any(str(cap).startswith(prefix) for cap in self._config.capabilities)

    def _probe_workspace_root(self) -> dict:
        path = Path(self._config.workspace_root)
        ok = path.exists() and path.is_dir()
        return {"ok": ok, "path": str(path)}

    def _probe_git_sha(self, target_git_sha: str | None, git_sha: str | None) -> dict:
        if not target_git_sha:
            return {"ok": bool(git_sha), "git_sha": git_sha, "target_git_sha": None}
        ok = bool(git_sha) and (
            git_sha.startswith(target_git_sha) or target_git_sha.startswith(git_sha)
        )
        return {"ok": ok, "git_sha": git_sha, "target_git_sha": target_git_sha}

    def _probe_capabilities(self) -> dict:
        capabilities = [str(cap) for cap in self._config.capabilities]
        return {"ok": bool(capabilities), "capabilities": capabilities}

    def _probe_blender(self) -> dict:
        executable = self._config.adapters.blender.executable
        path = shutil.which(executable) or (executable if Path(executable).exists() else "")
        if not path:
            return {"ok": False, "executable": executable, "error": "Blender executable not found"}
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=self._config.update_probe_timeout_seconds,
            )
        except Exception as exc:
            return {"ok": False, "executable": executable, "error": str(exc)}
        return {
            "ok": result.returncode == 0,
            "executable": executable,
            "version": (result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else "",
            "returncode": result.returncode,
        }

    def _probe_gpu(self) -> dict:
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return {"ok": False, "error": "nvidia-smi not found"}
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=self._config.update_probe_timeout_seconds,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": result.returncode == 0 and bool(result.stdout.strip()),
            "gpus": [line.strip() for line in result.stdout.splitlines() if line.strip()],
            "returncode": result.returncode,
            "error": result.stderr.strip() or None,
        }

    def _run_custom_probe_commands(self, target_git_sha: str | None = None) -> dict:
        results = {}
        substitutions = self._command_substitutions(target_git_sha)
        for index, raw in enumerate(self._config.update_probe_commands, start=1):
            name = f"custom_probe_{index}"
            argv = _command_argv(raw, substitutions)
            if not argv:
                results[name] = {"ok": True, "skipped": True}
                continue
            try:
                result = subprocess.run(
                    argv,
                    cwd=self._config.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=self._config.update_probe_timeout_seconds,
                )
            except Exception as exc:
                results[name] = {"ok": False, "command": argv, "error": str(exc)}
                continue
            results[name] = {
                "ok": result.returncode == 0,
                "command": argv,
                "returncode": result.returncode,
                "output": (result.stdout + result.stderr).strip()[-1000:],
            }
        return results
