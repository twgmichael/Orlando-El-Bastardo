from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.routers.workers import (
    WORKER_UPDATE_ERROR_MAX_LENGTH,
    _heartbeat_error_is_stale,
    _worker_update_error,
    _worker_update_target_matches,
)
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


def test_worker_update_error_is_truncated_for_storage():
    error = _worker_update_error("x" * 2000)

    assert len(error) == WORKER_UPDATE_ERROR_MAX_LENGTH
    assert error.endswith("...")


@pytest.mark.parametrize("pending_state", ["draining", "ready_to_update", "force_requested"])
def test_worker_update_ignores_stale_heartbeat_errors_for_new_requests(pending_state):
    assert _heartbeat_error_is_stale(pending_state, "failed")


def test_worker_update_accepts_errors_after_apply_begins():
    assert not _heartbeat_error_is_stale("applying", "failed")


def test_worker_update_target_matches_with_no_target():
    assert _worker_update_target_matches(None, "993d21304e04")


def test_worker_update_target_matches_short_reported_sha_against_full_target():
    # Regression: the worker agent reports a short SHA, admins pass a full
    # SHA to tools/update_worker.py. A successful update must not report
    # "failed" just because the two strings differ in length.
    assert _worker_update_target_matches(
        "993d21304e049f1f17844250b8e57de80117e755", "993d21304e04"
    )


def test_worker_update_target_matches_exact_full_shas():
    sha = "993d21304e049f1f17844250b8e57de80117e755"
    assert _worker_update_target_matches(sha, sha)


def test_worker_update_target_matches_rejects_different_sha():
    assert not _worker_update_target_matches(
        "993d21304e049f1f17844250b8e57de80117e755", "fb2f11783ae9"
    )


def test_worker_update_target_matches_rejects_missing_reported_sha():
    assert not _worker_update_target_matches("993d21304e049f1f17844250b8e57de80117e755", None)
