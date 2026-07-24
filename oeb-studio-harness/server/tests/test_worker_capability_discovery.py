from agent.adapters.blender import BlenderCLIAdapter
from agent.capabilities import discover_worker_capabilities
from agent.config import BlenderAdapterConfig, WorkerConfig


def test_discovery_removes_gpu_capability_when_nvidia_probe_fails(tmp_path, monkeypatch):
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="linux-x64",
        capabilities=["blender.final_render", "gpu.cycles_render", "gpu.texture_bake"],
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr("agent.capabilities.probe_blender_executable", lambda _executable: {"ok": True})
    monkeypatch.setattr("agent.capabilities.probe_nvidia_smi", lambda: {"ok": False, "error": "NVML mismatch"})
    monkeypatch.setattr("agent.capabilities.probe_blender_gpu_devices", lambda _executable: {"ok": True})

    capabilities, resources = discover_worker_capabilities(cfg)

    assert "blender.final_render" in capabilities
    assert "gpu.cycles_render" not in capabilities
    assert "gpu.texture_bake" not in capabilities
    assert resources["desired_capabilities"] == [
        "blender.final_render",
        "gpu.cycles_render",
        "gpu.texture_bake",
    ]
    assert resources["degraded_capabilities"]["gpu.cycles_render"] == "NVML mismatch"
    assert resources["degraded_capabilities"]["gpu.texture_bake"] == "NVML mismatch"


def test_discovery_keeps_gpu_capability_when_runtime_probes_pass(tmp_path, monkeypatch):
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="linux-x64",
        capabilities=["blender.final_render", "gpu.cycles_render"],
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr("agent.capabilities.probe_blender_executable", lambda _executable: {"ok": True})
    monkeypatch.setattr("agent.capabilities.probe_nvidia_smi", lambda: {"ok": True, "gpus": ["GTX 1660 SUPER"]})
    monkeypatch.setattr(
        "agent.capabilities.probe_blender_gpu_devices",
        lambda _executable: {"ok": True, "selected_backends": ["CUDA"]},
    )

    capabilities, resources = discover_worker_capabilities(cfg)

    assert "gpu.cycles_render" in capabilities
    assert resources["degraded_capabilities"] == {}


def test_discovery_degrades_only_cycles_when_blender_gpu_probe_fails(tmp_path, monkeypatch):
    cfg = WorkerConfig(
        worker_id="render-test-01",
        platform="linux-x64",
        capabilities=["blender.final_render", "gpu.cycles_render", "gpu.texture_bake"],
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr("agent.capabilities.probe_blender_executable", lambda _executable: {"ok": True})
    monkeypatch.setattr("agent.capabilities.probe_nvidia_smi", lambda: {"ok": True, "gpus": ["GTX 1660 SUPER"]})
    monkeypatch.setattr(
        "agent.capabilities.probe_blender_gpu_devices",
        lambda _executable: {"ok": False, "error": "No CUDA devices"},
    )

    capabilities, resources = discover_worker_capabilities(cfg)

    assert "gpu.cycles_render" not in capabilities
    assert "gpu.texture_bake" in capabilities
    assert resources["degraded_capabilities"] == {"gpu.cycles_render": "No CUDA devices"}


def test_blender_adapter_requires_runtime_gpu_metadata_for_gpu_jobs():
    adapter = BlenderCLIAdapter(BlenderAdapterConfig(), workspace_root="/workspace")
    payload = {"_required_capabilities": ["gpu.cycles_render"]}

    assert adapter._gpu_contract_error(payload, None)
    assert adapter._gpu_contract_error(payload, {"engine": "CYCLES", "cycles_device": "CPU", "gpu_enabled": False})
    assert adapter._gpu_contract_error(payload, {"engine": "BLENDER_EEVEE_NEXT", "gpu_enabled": False})
    assert adapter._gpu_contract_error(
        payload,
        {"engine": "CYCLES", "cycles_device": "GPU", "gpu_enabled": True},
    ) is None


def test_blender_adapter_sets_gpu_environment_for_gpu_jobs():
    adapter = BlenderCLIAdapter(BlenderAdapterConfig(), workspace_root="/workspace")

    env = adapter._render_env({"_required_capabilities": ["gpu.cycles_render"]})

    assert env["OEB_FORCE_CYCLES_GPU"] == "1"
    assert env["OEB_CYCLES_BACKENDS"] == "OPTIX,CUDA"
    assert "/workspace/tools" in env["PYTHONPATH"]
