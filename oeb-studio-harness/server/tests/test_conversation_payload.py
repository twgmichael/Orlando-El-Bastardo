from app.routers.conversations import _build_job_payload, _normalize_spec_for_request
from app.schemas.conversation import PrimitiveBuildSpec


def test_conversation_spec_normalization_repairs_missing_shape():
    prompt = "Build a spaceship that looks like the capital letter V."
    spec = PrimitiveBuildSpec(
        canonical_id="asset_spaceship_that_looks_like_A",
        name="Letter Ship",
        kind="asset",
        style="compact sci-fi",
        components=["wedge hull"],
    )

    normalized = _normalize_spec_for_request(prompt, spec)

    assert normalized.canonical_id == "ship_capital_letter_v_A"
    assert normalized.kind == "vehicle"


def test_conversation_spec_normalization_repairs_motorcycle_asset_slug():
    prompt = "Build a motorcycle."
    spec = PrimitiveBuildSpec(
        canonical_id="asset_motorcycle_A",
        name="Motorcycle",
        kind="asset",
        style="modern metallic",
        components=[],
    )

    normalized = _normalize_spec_for_request(prompt, spec)

    assert normalized.canonical_id == "vehicle_motorcycle_A"
    assert normalized.kind == "vehicle"
    assert normalized.components == [
        "front wheel",
        "rear wheel",
        "low motorcycle frame",
        "engine block",
        "fuel tank",
        "single saddle seat",
        "front fork",
        "handlebars",
        "rear exhaust pipe",
    ]


def test_job_payload_uses_job_scoped_output_paths():
    prompt = "Build a spaceship that looks like the capital letter V."
    spec = PrimitiveBuildSpec(
        canonical_id="ship_capital_letter_v_A",
        name="Letter Ship",
        kind="vehicle",
        style="compact sci-fi",
        components=["wedge hull"],
    )

    payload = _build_job_payload(prompt, spec)
    job_payload = payload["payload"]

    assert payload["title"] == "Build ship_capital_letter_v_A primitive vehicle"
    assert job_payload["output_path"] == (
        "{output_root}/jobs/{job_id}/renders/asset_previews/ship_capital_letter_v_A.png"
    )
    assert job_payload["artifact_paths"] == [
        "{output_root}/jobs/{job_id}/assets/vehicles/ship_capital_letter_v_A.glb",
        "{output_root}/jobs/{job_id}/renders/asset_previews/ship_capital_letter_v_A.png",
        "{output_root}/jobs/{job_id}/out/asset_builds/ship_capital_letter_v_A.json",
    ]
    assert job_payload["script_args"][2:] == [
        "--output",
        "{output_root}/jobs/{job_id}/assets/vehicles/ship_capital_letter_v_A.glb",
        "--preview-output",
        "{output_root}/jobs/{job_id}/renders/asset_previews/ship_capital_letter_v_A.png",
        "--manifest-output",
        "{output_root}/jobs/{job_id}/out/asset_builds/ship_capital_letter_v_A.json",
    ]
    assert job_payload["conversation"]["creative_request"] == prompt
    assert job_payload["conversation"]["spec"]["canonical_id"] == "ship_capital_letter_v_A"
