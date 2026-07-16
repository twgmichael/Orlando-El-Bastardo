from app.services import studio_chat
from app.services.studio_chat import (
    build_studio_chat_trace,
    derive_spec_from_scene_plan,
    enrich_scene_plan_details,
    normalize_spec,
    repair_scene_plan_prompt,
    scene_plan_prompt,
    slugify_asset_id,
)


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
    assert slugify_asset_id("Build a plane.") == "vehicle_plane_A"
    assert slugify_asset_id(
        "Build a compact sci-fi garage with workbench, tool wall, lift platform, and one small rover."
    ) == "location_compact_sci_fi_garage_A"
    assert slugify_asset_id("Build a bike rack.") == "prop_bike_rack_A"
    assert slugify_asset_id("Build a dining room table with rounded corners.") == (
        "prop_dining_room_table_rounded_A"
    )


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
        "low vehicle frame",
        "engine block",
        "single saddle seat",
        "handlebars",
    ]


def test_normalize_spec_keeps_bike_rack_as_prop():
    prompt = "Build a bike rack."
    spec = normalize_spec(prompt, {
        "canonical_id": "asset_bike_rack_A",
        "name": "Bike Rack",
        "style": "metal",
        "components": [],
    })

    assert spec["canonical_id"] == "prop_bike_rack_A"
    assert spec["kind"] == "prop"
    assert spec["components"] == ["primary structure", "secondary feature", "detail element"]


def test_normalize_spec_repairs_plane_surface_misread():
    prompt = "Build a plane."
    spec = normalize_spec(prompt, {
        "canonical_id": "asset_plane_A",
        "name": "Simple Plane",
        "style": "minimalistic",
        "components": [
            "wide_plane_center_floor_facing_plane_2",
            "wide_target_plane_center_floor_facing_plane_1",
        ],
    })

    assert spec["canonical_id"] == "vehicle_plane_A"
    assert spec["kind"] == "vehicle"
    assert spec["components"] == [
        "long aircraft fuselage",
        "front nose cone",
        "left wing",
        "right wing",
        "tail fin",
        "rear engine",
    ]


def test_scene_plan_prompt_declares_oeb_orientation_standard():
    prompt = scene_plan_prompt("build an airplane")

    assert "+X is front" in prompt
    assert "-X is rear/back" in prompt
    assert "-Y is left" in prompt
    assert "+Y is right" in prompt
    assert "+Z is up" in prompt
    assert "-Z is down" in prompt


def test_scene_plan_prompt_declares_detail_schema_fields():
    prompt = scene_plan_prompt("build a dining room table with rounded corners")

    assert '"shape"' in prompt
    assert '"required_features"' in prompt
    assert '"source_phrases"' in prompt
    assert '"materials"' in prompt
    assert '"style_details"' in prompt
    assert '"parts"' in prompt
    assert 'shape.corner_style="rounded"' in prompt


def test_repair_prompt_declares_oeb_orientation_standard():
    prompt = repair_scene_plan_prompt("build an airplane", {"objects": []}, [])

    assert "+X is front" in prompt
    assert "-X is rear/back" in prompt
    assert "-Y is left" in prompt
    assert "+Y is right" in prompt
    assert "+Z is up" in prompt
    assert "-Z is down" in prompt


def test_repair_prompt_requires_rounded_corner_pass_through():
    prompt = repair_scene_plan_prompt("build a table with rounded corners", {"objects": []}, [])

    assert "rounded corners" in prompt
    assert 'shape.corner_style="rounded"' in prompt
    assert '"rounded_corners"' in prompt


def test_enrich_scene_plan_details_preserves_rounded_corner_modifier():
    scene_plan = {
        "scene_type": "table",
        "style": "simple",
        "objects": [
            {
                "id": "table_1",
                "label": "dining table",
                "category": "surface",
                "count": 1,
                "placement": "center",
                "mounting": "self",
            }
        ],
        "relationships": [],
    }

    enriched, warnings = enrich_scene_plan_details(
        "build a dining room table with rounded corners",
        scene_plan,
    )
    table = enriched["objects"][0]

    assert warnings == []
    assert table["shape"]["corner_style"] == "rounded"
    assert "rounded_corners" in table["required_features"]
    assert "rounded corners" in table["source_phrases"]


def test_derived_spec_components_include_structured_detail_fields():
    scene_plan = {
        "scene_type": "table",
        "style": "simple",
        "objects": [
            {
                "id": "table_1",
                "label": "dining table",
                "category": "surface",
                "count": 1,
                "placement": "center",
                "mounting": "self",
                "shape": {"corner_style": "rounded"},
                "required_features": ["rounded_corners"],
                "source_phrases": ["rounded corners"],
            }
        ],
        "relationships": [],
    }

    spec = derive_spec_from_scene_plan("build a dining room table with rounded corners", scene_plan)

    assert spec.kind == "prop"
    assert spec.repaired_scene_plan.objects[0].shape == {"corner_style": "rounded"}
    assert "rounded_corners" in spec.repaired_scene_plan.objects[0].required_features
    assert spec.components == [
        "dining_table_center_self_rounded_rounded_corners_rounded_corners"
    ]


def test_simple_prompt_still_runs_llm_scene_and_repair(monkeypatch):
    class Config:
        ollama_url = "http://local-llm"
        model = "test-model"

    calls = []

    def fake_ollama_generate(config, prompt):
        calls.append(prompt)
        scene_plan = {
            "scene_type": "army_tank",
            "style": "armored military vehicle",
            "objects": [
                {
                    "id": "tank_hull",
                    "label": "tank hull",
                    "category": "vehicle",
                    "count": 1,
                    "size": "large",
                    "placement": "center",
                    "mounting": "floor",
                    "orientation": {},
                },
                {
                    "id": "main_cannon",
                    "label": "main cannon",
                    "category": "structure",
                    "count": 1,
                    "size": "long",
                    "placement": "front",
                    "mounting": "surface",
                    "orientation": {"faces": "front"},
                },
            ],
            "relationships": [],
        }
        return {
            "prompt": prompt,
            "raw_response": studio_chat.json.dumps(scene_plan),
            "parsed_response": scene_plan,
        }

    monkeypatch.setattr(studio_chat, "ollama_generate", fake_ollama_generate)

    trace = build_studio_chat_trace("build an army tank", Config())

    assert len(calls) == 2
    assert calls[0] == trace["scene_plan_prompt"]
    assert calls[1] == trace["repair_prompt"]
    assert trace["scene_plan_prompt"].startswith(
        "You are the production-designer intake assistant"
    )
    assert trace["repair_prompt"].startswith("You are repairing an asset/location graph")
    assert trace["spec"].components == [
        "large_tank_hull_center_floor",
        "long_main_cannon_front_surface_facing_front",
    ]
