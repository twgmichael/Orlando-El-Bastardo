from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.worker import WorkerHeartbeatResponse, WorkerUpdateRequest
from app.services.worker_updates import worker_can_claim_jobs


@pytest.mark.parametrize("state", ["idle", "complete", None])
def test_worker_can_claim_jobs_when_not_draining(state):
    worker = SimpleNamespace(update_state=state)

    assert worker_can_claim_jobs(worker)


@pytest.mark.parametrize("state", ["draining", "ready_to_update", "applying", "force_requested", "failed"])
def test_worker_cannot_claim_jobs_during_update_states(state):
    worker = SimpleNamespace(update_state=state)

    assert not worker_can_claim_jobs(worker)


def test_missing_worker_cannot_claim_jobs():
    assert not worker_can_claim_jobs(None)


@pytest.mark.parametrize("mode", ["drain_then_update", "update_if_idle", "force_update"])
def test_worker_update_request_accepts_supported_modes(mode):
    request = WorkerUpdateRequest(mode=mode, target_git_sha="abc1234")

    assert request.mode == mode
    assert request.target_git_sha == "abc1234"


def test_worker_update_request_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        WorkerUpdateRequest(mode="restart_now")


def test_worker_heartbeat_response_carries_update_instruction():
    response = WorkerHeartbeatResponse(
        acknowledged=True,
        server_time="2026-07-19T22:00:00Z",
        update_state="ready_to_update",
        update_mode="drain_then_update",
        update_target_git_sha="abc1234",
    )

    assert response.update_state == "ready_to_update"
    assert response.update_mode == "drain_then_update"
    assert response.update_target_git_sha == "abc1234"
