import json
import re
import shutil
import subprocess

from agent.config import WorkerConfig


GPU_CAPABILITY = "gpu.cycles_render"
BLENDER_CAPABILITY_PREFIX = "blender."
GPU_PROBE_MARKER = "OEB_GPU_PROBE "


def discover_worker_capabilities(cfg: WorkerConfig) -> tuple[list[str], dict]:
    desired = list(dict.fromkeys(cfg.capabilities))
    degraded: dict[str, str] = {}
    probes: dict[str, dict] = {}

    verified = desired[:]
    blender_caps = [cap for cap in desired if cap.startswith(BLENDER_CAPABILITY_PREFIX)]
    if blender_caps:
        blender_probe = probe_blender_executable(cfg.adapters.blender.executable)
        probes["blender"] = blender_probe
        if not blender_probe.get("ok"):
            for cap in blender_caps:
                degraded[cap] = str(blender_probe.get("error") or "Blender executable probe failed")
            verified = [cap for cap in verified if not cap.startswith(BLENDER_CAPABILITY_PREFIX)]

    if GPU_CAPABILITY in desired:
        nvidia_probe = probe_nvidia_smi()
        blender_gpu_probe = (
            probe_blender_gpu_devices(cfg.adapters.blender.executable)
            if probes.get("blender", {}).get("ok", True)
            else {"ok": False, "error": "Blender executable probe failed"}
        )
        probes["nvidia_smi"] = nvidia_probe
        probes["blender_gpu"] = blender_gpu_probe
        if not nvidia_probe.get("ok"):
            degraded[GPU_CAPABILITY] = str(nvidia_probe.get("error") or "nvidia-smi probe failed")
        elif not blender_gpu_probe.get("ok"):
            degraded[GPU_CAPABILITY] = str(blender_gpu_probe.get("error") or "Blender GPU discovery failed")

    if GPU_CAPABILITY in degraded:
        verified = [cap for cap in verified if cap != GPU_CAPABILITY]

    resources = {
        **(cfg.resources or {}),
        "desired_capabilities": desired,
        "verified_capabilities": verified,
        "degraded_capabilities": degraded,
        "capability_probe": probes,
    }
    return verified, resources


def probe_blender_executable(executable: str) -> dict:
    path = shutil.which(executable) or executable
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return {"ok": False, "executable": executable, "path": path, "error": str(exc)}
    output = (result.stdout or result.stderr or "").splitlines()
    return {
        "ok": result.returncode == 0,
        "executable": executable,
        "path": path,
        "version": output[0] if output else "",
        "returncode": result.returncode,
        "error": result.stderr.strip() or None,
    }


def probe_nvidia_smi() -> dict:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"ok": False, "error": "nvidia-smi not found"}
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return {"ok": False, "executable": executable, "error": str(exc)}
    gpus = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {
        "ok": result.returncode == 0 and bool(gpus),
        "executable": executable,
        "gpus": gpus,
        "returncode": result.returncode,
        "error": result.stderr.strip() or None,
    }


def probe_blender_gpu_devices(executable: str) -> dict:
    probe = r'''
import json
import bpy

prefs = bpy.context.preferences.addons["cycles"].preferences
try:
    enum_prop = prefs.bl_rna.properties["compute_device_type"]
    supported = [item.identifier for item in enum_prop.enum_items]
except Exception:
    supported = []
summaries = []
for backend in ("OPTIX", "CUDA"):
    if backend not in supported:
        summaries.append({"backend": backend, "ok": False, "error": "unsupported"})
        continue
    try:
        prefs.compute_device_type = backend
        prefs.get_devices()
        devices = [{"name": d.name, "type": d.type, "use": bool(d.use)} for d in prefs.devices]
        gpu_devices = [d for d in devices if d["type"] == backend]
        summaries.append({"backend": backend, "ok": bool(gpu_devices), "devices": devices})
    except Exception as exc:
        summaries.append({"backend": backend, "ok": False, "error": str(exc)})
print("OEB_GPU_PROBE " + json.dumps({"supported_backends": supported, "backends": summaries}, sort_keys=True))
'''
    try:
        result = subprocess.run(
            [executable, "--background", "--factory-startup", "--python-expr", probe],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return {"ok": False, "executable": executable, "error": str(exc)}

    output = result.stdout + result.stderr
    parsed = _parse_probe_json(output)
    if not parsed:
        return {
            "ok": False,
            "executable": executable,
            "returncode": result.returncode,
            "error": "Blender GPU probe did not return device metadata",
            "log_tail": "\n".join(output.splitlines()[-20:]),
        }

    working = [backend for backend in parsed.get("backends", []) if backend.get("ok")]
    parsed.update({
        "ok": result.returncode == 0 and bool(working),
        "executable": executable,
        "returncode": result.returncode,
        "selected_backends": [backend["backend"] for backend in working],
        "error": None if working else "No CUDA/OptiX GPU devices discovered by Blender",
    })
    return parsed


def _parse_probe_json(output: str) -> dict | None:
    pattern = re.compile(rf"^{re.escape(GPU_PROBE_MARKER)}(.+)$", re.MULTILINE)
    match = pattern.search(output or "")
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
