import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import studio_chat as studio_chat_router
from app.schemas.studio_chat import (
    StudioChatBuildJobRequest,
    StudioChatBuildPipelineResult,
)
from app.services import studio_chat
from app.services.studio_chat import (
    _normalize_asset_intent_structure,
    compile_studio_chat_build_pipeline,
    pipeline_allows_job_submission,
    resolve_primitive_spec,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "studio_chat_llm_responses"


@pytest.mark.parametrize(
    "fixture_path",
    sorted(FIXTURE_ROOT.glob("*.json")),
    ids=lambda path: path.stem,
)
def test_real_response_fixture_behavior_classes(fixture_path):
    fixture = json.loads(fixture_path.read_text())

    result = compile_studio_chat_build_pipeline(
        fixture["creative_request"],
        fixture["raw_response"],
    )

    assert result.outcome == fixture["expected_outcome"]
    if expected_code := fixture.get("expected_diagnostic_code"):
        assert result.diagnostics[0].code == expected_code
    if expected_repairs := fixture.get("expected_repair_codes"):
        repair_codes = {repair["code"] for repair in result.ingestion_repairs}
        assert set(expected_repairs).issubset(repair_codes)


def test_unknown_fields_survive_ingestion_and_normalization():
    fixture = json.loads((FIXTURE_ROOT / "rich_unknown_fields.json").read_text())

    result = compile_studio_chat_build_pipeline(
        fixture["creative_request"],
        fixture["raw_response"],
    )

    assert result.outcome == "compiled"
    assert result.parsed_response["vendor_extension"] == {"keep_me": True}
    assert result.normalized_asset_intent["future_style"] == {"era": "retro"}
    assert result.normalized_asset_intent["objects"][0]["unknown_modifier"] == {
        "refraction_hint": 0.8
    }


def test_asset_intent_normalization_is_idempotent_and_preserves_extensions():
    original = {
        "title": "Test Assembly",
        "future_extension": {"preserve": ["all", "values"]},
        "objects": [
            {
                "id": "Blue Ball",
                "type": "ball",
                "color": "blue",
                "custom": {"meaning": "keep"},
            }
        ],
    }

    once = _normalize_asset_intent_structure(original, "Build a blue ball.")
    twice = _normalize_asset_intent_structure(once, "Build a blue ball.")

    assert twice == once
    assert once["future_extension"] == original["future_extension"]
    assert once["objects"][0]["custom"] == {"meaning": "keep"}


def test_non_finite_numeric_value_never_compiles():
    result = compile_studio_chat_build_pipeline(
        "Build a sphere.",
        (
            '{"action":"build_asset","build_job":{"asset_kind":"prop",'
            '"primitives":[{"id":"sphere","type":"sphere",'
            '"transform":{"scale":[NaN,1,1]}}]}}'
        ),
    )

    assert result.outcome == "invalid"
    assert result.diagnostics[0].code == "non_finite_numeric_value"
    assert pipeline_allows_job_submission(result) is False


def test_one_focused_repair_pass_can_compile(monkeypatch):
    calls = []

    def fake_post_json(url, payload, token=None, timeout=60):
        calls.append(payload)
        return {
            "message": {
                "role": "assistant",
                "content": (
                    '{"version":"0.1","asset_kind":"prop",'
                    '"canonical_id":"prop_blue_sphere_A","name":"Blue Sphere",'
                    '"primitives":[{"id":"main_sphere","type":"sphere","material":"blue"}]}'
                ),
            },
            "done": True,
        }

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)
    result = compile_studio_chat_build_pipeline(
        "Build a blue sphere.",
        (
            '{"action":"build_asset","build_job":{"asset_kind":"prop",'
            '"primitives":[{"id":"shape","type":"imaginary","material":"blue"}]}}'
        ),
        ollama_url="http://ollama.test",
        model="local-test-model",
    )

    assert result.outcome == "compiled"
    assert result.repair_attempt_count == 1
    assert len(calls) == 1
    assert pipeline_allows_job_submission(result) is True


def test_repair_exhaustion_is_structured_and_cannot_submit(monkeypatch):
    calls = []

    def fake_post_json(url, payload, token=None, timeout=60):
        calls.append(payload)
        return {
            "message": {
                "role": "assistant",
                "content": '{"version":"0.1","primitives":[{"type":"imaginary"}]}',
            },
            "done": True,
        }

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)
    result = compile_studio_chat_build_pipeline(
        "Build a blue sphere.",
        (
            '{"action":"build_asset","build_job":{"asset_kind":"prop",'
            '"primitives":[{"id":"shape","type":"imaginary","material":"blue"}]}}'
        ),
        ollama_url="http://ollama.test",
        model="local-test-model",
        resolver_retries=1,
    )

    assert len(calls) == 2
    assert result.outcome == "needs_repair"
    assert result.diagnostics[0].code == "repair_exhausted"
    assert result.repair_attempt_count == 2
    assert pipeline_allows_job_submission(result) is False


def test_second_repair_is_limited_to_explicitly_recoverable_class(monkeypatch):
    calls = []

    def fake_post_json(url, payload, token=None, timeout=60):
        calls.append(payload)
        if len(calls) < 2:
            content = '{"version":"0.1","primitives":[]}'
        else:
            content = (
                '{"version":"0.1","asset_kind":"prop","canonical_id":"prop_cube_A",'
                '"name":"Cube","primitives":[{"id":"cube","type":"cube"}]}'
            )
        return {"message": {"role": "assistant", "content": content}, "done": True}

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)
    result = resolve_primitive_spec(
        "http://ollama.test",
        "local-test-model",
        "Build a cube.",
        '{"action":"build_asset"}',
        max_retries=2,
    )

    assert result["ok"] is True
    assert len(calls) == 2


def test_second_repair_is_denied_for_nonrecoverable_validation_class(monkeypatch):
    calls = []

    def fake_post_json(url, payload, token=None, timeout=60):
        calls.append(payload)
        return {
            "message": {
                "role": "assistant",
                "content": (
                    '{"version":"0.1","version":"0.2",'
                    '"primitives":[{"type":"cube"}]}'
                ),
            },
            "done": True,
        }

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)
    result = resolve_primitive_spec(
        "http://ollama.test",
        "local-test-model",
        "Build a cube.",
        '{"action":"build_asset"}',
        max_retries=2,
    )

    assert result["ok"] is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    "outcome",
    ["needs_repair", "needs_clarification", "unsupported", "invalid"],
)
def test_submission_gate_rejects_every_noncompiled_outcome(outcome):
    result = StudioChatBuildPipelineResult(
        outcome=outcome,
        trace_id="fixture-trace",
        raw_response="{}",
    )

    assert pipeline_allows_job_submission(result) is False


class _RejectingDatabase:
    def __init__(self):
        self.commit_count = 0
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commit_count += 1


def test_build_endpoint_returns_structured_diagnostic_without_job(monkeypatch):
    pipeline = StudioChatBuildPipelineResult(
        outcome="invalid",
        trace_id="integration-trace",
        raw_response="not json",
        diagnostics=[
            {
                "stage": "ingestion",
                "outcome": "invalid",
                "code": "assistant_json_invalid",
                "reason": "Invalid JSON.",
            }
        ],
    )
    monkeypatch.setattr(
        studio_chat_router,
        "compile_studio_chat_build_pipeline",
        lambda *args, **kwargs: pipeline,
    )
    database = _RejectingDatabase()

    async def invoke():
        return await studio_chat_router.create_studio_chat_build_job(
            StudioChatBuildJobRequest(
                creative_request="Build a cube.",
                assistant_response="not json",
            ),
            thread_id=None,
            db=database,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(invoke())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["outcome"] == "invalid"
    assert exc_info.value.detail["trace_id"] == "integration-trace"
    assert database.added == []
    assert database.commit_count == 1
