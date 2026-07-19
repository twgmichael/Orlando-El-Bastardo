import pytest
from types import SimpleNamespace

from app.services import asset_review


@pytest.mark.anyio
async def test_resolves_known_friendly_asset_names():
    assert (await asset_review.resolve_review_asset(None, asset_query="Ventradi Cruiser")).asset_id == "ventradi_cruiser"
    assert (await asset_review.resolve_review_asset(None, asset_query="JB45")).asset_id == "jb5k"
    assert (await asset_review.resolve_review_asset(None, asset_query="JB100")).asset_id == "prop_jb100_A"
    assert (await asset_review.resolve_review_asset(None, asset_query="Ellispso Flyer")).asset_id == "ellipso_flyer_mk1"


@pytest.mark.anyio
async def test_resolves_explicit_path_without_known_registry():
    resolved = await asset_review.resolve_review_asset(
        None,
        asset_path="assets/ships/new_ship.glb",
    )

    assert resolved.asset_id == "new_ship"
    assert resolved.asset_path == "assets/ships/new_ship.glb"


def test_review_readiness_requires_uploaded_artifacts_for_all_requested_views():
    job = SimpleNamespace(
        payload={
            "job_type": "asset.review_render",
            "asset_id": "jb5k",
            "views": ["front", "back", "action"],
        }
    )
    artifacts = [
        SimpleNamespace(
            filename="jb5k_front.png",
            mime_type="image/png",
            provenance="uploaded",
            review_metadata={"view": "front"},
        ),
        SimpleNamespace(
            filename="jb5k_back.png",
            mime_type="image/png",
            provenance="backfilled",
            review_metadata={"view": "back"},
        ),
        SimpleNamespace(
            filename="jb5k_action.png",
            mime_type="image/png",
            provenance="uploaded",
            review_metadata={"view": "action"},
        ),
    ]

    assert asset_review.missing_uploaded_views(job, artifacts) == ["back"]


def test_db_seeded_review_asset_paths_are_workspace_relative():
    asset = SimpleNamespace(file_path="ships/jb100.glb")

    assert asset_review._asset_path_for_db_asset(asset) == "assets/ships/jb100.glb"


@pytest.mark.anyio
async def test_final_review_render_can_require_gpu_cycles():
    db = SimpleNamespace(
        add=lambda value: None,
        flush=lambda: None,
    )

    async def flush():
        return None

    db.flush = flush
    job = await asset_review.create_asset_review_render_job(
        db,
        asset=asset_review.ReviewAsset(
            asset_id="prop_jb100_A",
            asset_path="assets/ships/jb100.glb",
            name="JourneyBlaster 100",
        ),
        quality="final",
        require_gpu_cycles=True,
    )

    assert job.required_capabilities == ["blender.final_render", "gpu.cycles_render"]
    assert job.payload["require_gpu_cycles"] is True
