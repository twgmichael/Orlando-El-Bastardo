import uuid
from pathlib import Path
from types import SimpleNamespace

from app.routers import review


def test_artifact_path_resolves_worker_mount_tail_to_server_artifacts_root(tmp_path, monkeypatch):
    job_id = uuid.uuid4()
    artifact_dir = tmp_path / str(job_id)
    artifact_dir.mkdir()
    expected = artifact_dir / "ventradi_cruiser_front.png"
    expected.write_bytes(b"png")

    monkeypatch.setattr(
        review,
        "get_settings",
        lambda: SimpleNamespace(
            artifacts_root=str(tmp_path),
            artifact_worker_path_prefix="",
            artifact_server_path_prefix="",
        ),
    )
    artifact = SimpleNamespace(
        job_id=job_id,
        filename="ventradi_cruiser_front.png",
        storage_path=(
            "/mnt/oeb-project/OEB-PRODUCTION/oeb-studio-harness/artifacts/"
            f"{job_id}/ventradi_cruiser_front.png"
        ),
    )

    assert review._artifact_file_path(artifact) == expected


def test_artifact_path_uses_explicit_worker_to_server_prefix_mapping(tmp_path, monkeypatch):
    job_id = uuid.uuid4()
    server_root = tmp_path / "server-artifacts"
    artifact_dir = server_root / str(job_id)
    artifact_dir.mkdir(parents=True)
    expected = artifact_dir / "ventradi_cruiser_action.png"
    expected.write_bytes(b"png")

    monkeypatch.setattr(
        review,
        "get_settings",
        lambda: SimpleNamespace(
            artifacts_root=str(tmp_path / "fallback"),
            artifact_worker_path_prefix="/worker/artifacts",
            artifact_server_path_prefix=str(server_root),
        ),
    )
    artifact = SimpleNamespace(
        job_id=job_id,
        filename="ventradi_cruiser_action.png",
        storage_path=f"/worker/artifacts/{job_id}/ventradi_cruiser_action.png",
    )

    assert review._artifact_file_path(artifact) == expected
