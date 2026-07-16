from app.services.studio_chat import normalize_spec, slugify_asset_id


def test_slug_preserves_capital_letter_shape():
    prompt = "Build a spaceship that looks like the capital letter V."

    assert slugify_asset_id(prompt) == "ship_capital_letter_v_A"


def test_slug_preserves_shaped_like_modifier():
    prompt = "Build a spaceship shaped like a crescent."

    assert slugify_asset_id(prompt) == "ship_crescent_shaped_A"


def test_slug_uses_domain_prefixes_for_known_kinds():
    assert slugify_asset_id("Build a small rover with two antennae.") == (
        "vehicle_small_rover_two_antennae_A"
    )
    assert slugify_asset_id("Build a motorcycle.") == "vehicle_motorcycle_A"
    assert slugify_asset_id(
        "Build a compact sci-fi garage with workbench, tool wall, lift platform, and one small rover."
    ) == "location_compact_sci_fi_garage_A"


def test_normalize_spec_repairs_truncated_shape_slug():
    prompt = "Build a spaceship that looks like the capital letter V."
    spec = normalize_spec(prompt, {
        "canonical_id": "asset_spaceship_that_looks_like_A",
        "name": "Letter Ship",
        "style": "compact sci-fi",
        "components": ["wedge hull"],
    })

    assert spec["canonical_id"] == "ship_capital_letter_v_A"
    assert spec["kind"] == "vehicle"
    assert spec["creative_request"] == prompt
    assert spec["build_method"] == "blender_primitives"
    assert spec["deliverables"] == ["glb", "preview_render", "review_page"]


def test_normalize_spec_replaces_generic_components():
    spec = normalize_spec("Build a compact rover.", {
        "canonical_id": "vehicle_compact_rover_A",
        "name": "Rover",
        "style": "compact",
        "components": ["cube", "cylinder"],
    })

    assert "wedge nose" in spec["components"]


def test_normalize_spec_repairs_motorcycle_kind_and_slug():
    prompt = "Build a motorcycle."
    spec = normalize_spec(prompt, {
        "canonical_id": "asset_motorcycle_A",
        "name": "Motorcycle",
        "style": "modern metallic",
        "components": [],
    })

    assert spec["canonical_id"] == "vehicle_motorcycle_A"
    assert spec["kind"] == "vehicle"
    assert spec["components"] == [
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
