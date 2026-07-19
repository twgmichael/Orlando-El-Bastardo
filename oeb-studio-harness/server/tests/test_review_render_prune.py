from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest

from app.services import artifact_prune


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.deleted = []
        self.added = []

    async def execute(self, _query):
        return _FakeResult(self.rows)

    async def delete(self, value):
        self.deleted.append(value)

    def add(self, value):
        self.added.append(value)


def _artifact(path, *, job_id=None, created_at=None, mime_type="image/png"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        job_id=job_id or uuid.uuid4(),
        filename=path.name,
        storage_path=str(path),
        mime_type=mime_type,
        created_at=created_at or datetime.now(timezone.utc) - timedelta(days=8),
    )


@pytest.mark.anyio
async def test_prune_deletes_old_unprotected_review_render_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        artifact_prune,
        "get_settings",
        lambda: SimpleNamespace(
            artifacts_root=str(tmp_path),
            artifact_worker_path_prefix="",
            artifact_server_path_prefix="",
            review_render_retention_days=7,
        ),
    )
    monkeypatch.setattr(
        artifact_prune,
        "_latest_completed_review_job_ids_by_active_asset",
        lambda _db: _async_value(set()),
    )
    file_path = tmp_path / "old_action.png"
    file_path.write_bytes(b"old preview")
    artifact = _artifact(file_path)
    db = _FakeDb([(artifact, SimpleNamespace())])

    result = await artifact_prune.prune_old_review_render_artifacts(
        db,
        now=datetime.now(timezone.utc),
    )

    assert result.artifacts_deleted == 1
    assert result.files_deleted == 1
    assert not file_path.exists()
    assert db.deleted == [artifact]


@pytest.mark.anyio
async def test_prune_keeps_latest_active_asset_render_files(tmp_path, monkeypatch):
    protected_job_id = uuid.uuid4()
    monkeypatch.setattr(
        artifact_prune,
        "get_settings",
        lambda: SimpleNamespace(
            artifacts_root=str(tmp_path),
            artifact_worker_path_prefix="",
            artifact_server_path_prefix="",
            review_render_retention_days=7,
        ),
    )
    monkeypatch.setattr(
        artifact_prune,
        "_latest_completed_review_job_ids_by_active_asset",
        lambda _db: _async_value({protected_job_id}),
    )
    file_path = tmp_path / "latest_action.png"
    file_path.write_bytes(b"active gallery")
    artifact = _artifact(file_path, job_id=protected_job_id)
    db = _FakeDb([(artifact, SimpleNamespace())])

    result = await artifact_prune.prune_old_review_render_artifacts(
        db,
        now=datetime.now(timezone.utc),
    )

    assert result.artifacts_deleted == 0
    assert result.files_deleted == 0
    assert file_path.exists()
    assert db.deleted == []


async def _async_value(value):
    return value
