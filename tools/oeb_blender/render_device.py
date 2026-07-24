from __future__ import annotations

import json
import os


def configure_render_device_from_env(scene=None) -> dict:
    require_gpu = os.environ.get("OEB_FORCE_CYCLES_GPU", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    raw_backends = os.environ.get("OEB_CYCLES_BACKENDS", "OPTIX,CUDA")
    preferred_backends = tuple(
        backend.strip().upper()
        for backend in raw_backends.split(",")
        if backend.strip()
    ) or ("OPTIX", "CUDA")
    return configure_render_device(
        scene=scene,
        require_gpu=require_gpu,
        preferred_backends=preferred_backends,
    )


def configure_render_device(
    scene=None,
    require_gpu: bool = False,
    preferred_backends: tuple[str, ...] = ("OPTIX", "CUDA"),
) -> dict:
    import bpy

    scene = scene or bpy.context.scene
    summary = {
        "gpu_required": bool(require_gpu),
        "engine_before": scene.render.engine,
        "engine": scene.render.engine,
        "cycles_device": None,
        "compute_device_type": None,
        "gpu_enabled": False,
        "devices": [],
        "warnings": [],
    }

    if require_gpu:
        scene.render.engine = "CYCLES"
    elif scene.render.engine != "CYCLES":
        summary["message"] = "Cycles GPU configuration skipped for non-Cycles render."
        _print_summary(summary)
        return summary

    if scene.render.engine != "CYCLES":
        summary["message"] = "Cycles GPU configuration skipped because Cycles is unavailable."
        if require_gpu:
            _print_summary(summary)
            raise RuntimeError("GPU render required but Cycles render engine is unavailable")
        _print_summary(summary)
        return summary

    prefs = bpy.context.preferences.addons["cycles"].preferences
    supported_backends = _supported_compute_backends(prefs)
    summary["supported_backends"] = supported_backends

    for backend in preferred_backends:
        if backend not in supported_backends:
            summary["warnings"].append(f"{backend} backend is not supported by this Blender build")
            continue
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
        except Exception as exc:
            summary["warnings"].append(f"{backend} discovery failed: {exc}")
            continue

        devices = _device_summaries(prefs.devices)
        gpu_device_names = []
        for device in prefs.devices:
            should_use = device.type == backend
            device.use = should_use
            if should_use:
                gpu_device_names.append(device.name)
        devices = _device_summaries(prefs.devices)

        summary.update({
            "engine": scene.render.engine,
            "cycles_device": "GPU" if gpu_device_names else "CPU",
            "compute_device_type": backend,
            "gpu_enabled": bool(gpu_device_names),
            "devices": devices,
            "selected_devices": gpu_device_names,
        })
        if gpu_device_names:
            scene.cycles.device = "GPU"
            _print_summary(summary)
            return summary

    prefs.compute_device_type = "NONE"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "CPU"
    scene.cycles.device = "CPU"
    summary.update({
        "engine": scene.render.engine,
        "cycles_device": "CPU",
        "compute_device_type": "NONE",
        "gpu_enabled": False,
        "devices": _device_summaries(prefs.devices),
    })
    _print_summary(summary)
    if require_gpu:
        raise RuntimeError("GPU render required but Blender discovered no CUDA/OptiX device")
    return summary


def _supported_compute_backends(prefs) -> list[str]:
    try:
        enum_prop = prefs.bl_rna.properties["compute_device_type"]
    except Exception:
        return []
    return [item.identifier for item in enum_prop.enum_items]


def _device_summaries(devices) -> list[dict]:
    return [
        {
            "name": device.name,
            "type": device.type,
            "use": bool(device.use),
        }
        for device in devices
    ]


def _print_summary(summary: dict) -> None:
    print("OEB_RENDER_DEVICE " + json.dumps(summary, sort_keys=True))
