import pytest

from agent.adapters.blender import BlenderCLIAdapter
from agent.config import BlenderAdapterConfig


def test_blender_adapter_expands_output_workspace_and_job_placeholders():
    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender"),
        output_root="/render-output",
        workspace_root="/workspace",
    )

    assert adapter._resolve_path("{output_root}/jobs/{job_id}/preview.png", "job-123") == (
        "/render-output/jobs/job-123/preview.png"
    )
    assert adapter._resolve_path("{workspace_root}/tools/build.py", "job-123") == (
        "/workspace/tools/build.py"
    )


def test_blender_adapter_rejects_path_traversal_after_expansion():
    adapter = BlenderCLIAdapter(
        BlenderAdapterConfig(executable="blender"),
        output_root="/render-output",
        workspace_root="/workspace",
    )

    with pytest.raises(ValueError):
        adapter._resolve_runtime_path("{output_root}/../escape.png", "output_path")
