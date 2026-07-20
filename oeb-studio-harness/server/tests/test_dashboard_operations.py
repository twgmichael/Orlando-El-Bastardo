from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.dashboard import _worker_display_id, templates
from agent import main as worker_main


def _job(title: str, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="job-123",
        title=title,
        status=status,
        policy="run_anywhere",
        assigned_worker_id="render-pc-01",
        priority=0,
        updated_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 7, 20, 11, 0, tzinfo=timezone.utc),
        payload={},
    )


def test_worker_display_id_includes_ip_address_from_resources():
    worker = SimpleNamespace(id="render-pc-01", resources={"ip_address": "203.0.113.42"})

    assert _worker_display_id(worker) == "render-pc-01 (203.0.113.42)"


def test_worker_display_id_falls_back_to_worker_id_without_ip():
    worker = SimpleNamespace(id="render-mac-01", resources={})

    assert _worker_display_id(worker) == "render-mac-01"


def test_dashboard_renders_recent_failed_jobs_section():
    html = templates.env.get_template("dashboard.html").render(
        workers=[],
        caps_by_worker={},
        active_jobs=[],
        failed_jobs=[_job("Final scene render failed", "failed")],
        completed_jobs=[],
        completed_label="last 24 hours",
        completed_page=0,
        has_older_completed=False,
        has_next_completed_page=False,
        job_counts={"failed": 1},
        audit_events=[],
        audit_page=0,
        has_next_audit_page=False,
    )

    assert "Failed Jobs" in html
    assert "Final scene render failed" in html
    assert "No failed jobs in the last 24 hours." not in html


def test_dashboard_worker_table_uses_worker_display_id():
    worker = SimpleNamespace(
        id="render-pc-01",
        resources={"ip_address": "203.0.113.42"},
        platform="linux",
        status="online",
        update_state="idle",
        update_target_git_sha=None,
        agent_version="0.1.0",
        git_sha=None,
        current_job_id=None,
        last_heartbeat_at=None,
    )
    html = templates.env.get_template("dashboard.html").render(
        workers=[worker],
        caps_by_worker={},
        active_jobs=[],
        failed_jobs=[],
        completed_jobs=[],
        completed_label="last 24 hours",
        completed_page=0,
        has_older_completed=False,
        has_next_completed_page=False,
        job_counts={},
        audit_events=[],
        audit_page=0,
        has_next_audit_page=False,
    )

    assert "render-pc-01 (203.0.113.42)" in html


def test_registration_resources_preserves_configured_ip(monkeypatch):
    monkeypatch.setattr(worker_main.socket, "gethostname", lambda: "render-pc-01")

    resources = worker_main._registration_resources(
        {"ip_address": "203.0.113.42"},
        "http://oeb-studio.docker-pi",
    )

    assert resources["ip_address"] == "203.0.113.42"
    assert resources["hostname"] == "render-pc-01"


def test_registration_resources_adds_detected_ip(monkeypatch):
    monkeypatch.setattr(worker_main.socket, "gethostname", lambda: "render-pc-01")
    monkeypatch.setattr(worker_main, "_detect_primary_ip", lambda _url: "203.0.113.43")

    resources = worker_main._registration_resources({}, "http://oeb-studio.docker-pi")

    assert resources["ip_address"] == "203.0.113.43"
    assert resources["hostname"] == "render-pc-01"
