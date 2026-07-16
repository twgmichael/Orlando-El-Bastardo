import importlib.util
import sys
import types
from pathlib import Path

import pytest


def load_builder_module():
    sys.modules.setdefault("bpy", types.SimpleNamespace())
    sys.modules.setdefault("mathutils", types.SimpleNamespace(Vector=lambda value: value))
    spec = importlib.util.spec_from_file_location(
        "primitive_asset_builder_for_test",
        Path("/tools/primitive_asset_builder.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scene_objects_are_the_preferred_builder_contract():
    builder = load_builder_module()
    spec = {
        "canonical_id": "vehicle_motorcycle_A",
        "name": "Motorcycle",
        "kind": "vehicle",
        "style": "modern metallic",
        "components": ["front wheel", "rear wheel", "handlebars"],
        "repaired_scene_plan": {
            "objects": [
                {
                    "id": "front_wheel",
                    "label": "front wheel",
                    "category": "vehicle",
                    "count": 1,
                    "placement": "front",
                    "mounting": "floor",
                    "orientation": {},
                }
            ],
            "relationships": [],
        },
    }

    items = builder.layout_items_for_spec(spec)

    assert items == [{
        "source": "scene_object",
        "value": spec["repaired_scene_plan"]["objects"][0],
    }]


def test_builder_no_longer_exposes_concept_specific_routes():
    builder = load_builder_module()

    assert not hasattr(builder, "wants_vehicle")
    assert not hasattr(builder, "wants_aircraft")
    assert not hasattr(builder, "wants_motorcycle")
    assert not hasattr(builder, "make_motorcycle_scene")
    assert not hasattr(builder, "make_fighter_scene")
    assert not hasattr(builder, "make_office_scene")
    assert not hasattr(builder, "make_park_scene")
    assert not hasattr(builder, "make_station_scene")


def test_two_wheeled_vehicle_parts_use_generic_categories():
    builder = load_builder_module()

    assert builder.category_for_name("front wheel", None) == "ring"
    assert builder.category_for_name("handlebars", None) == "vehicle_controls"
    assert builder.category_for_name("single saddle seat", None) == "vehicle_seat"
    assert builder.category_for_name("engine block", None) == "vehicle_engine"
    assert builder.component_position("front wheel", 0) == (1.25, 0, 0.35)
    assert builder.component_position("handlebars", 5) == (1.05, 0, 1.15)


def test_orientation_standard_is_explicit_builder_contract():
    builder = load_builder_module()

    assert builder.orientation_standard({"kind": "vehicle"}) == {
        "front_axis": "+X",
        "rear_axis": "-X",
        "left_axis": "-Y",
        "right_axis": "+Y",
        "up_axis": "+Z",
        "down_axis": "-Z",
        "origin_policy": "vehicle_centerline_midpoint",
        "documentation": "docs/planning/ASSET-LOCATION-ORIENTATION-STANDARD.md",
    }


def test_axis_placement_uses_oeb_local_axes():
    builder = load_builder_module()

    assert builder.axis_position_for_placement("front") == (1.0, 0, 0.35)
    assert builder.axis_position_for_placement("rear") == (-1.0, 0, 0.35)
    assert builder.axis_position_for_placement("left") == (0, -1.0, 0.35)
    assert builder.axis_position_for_placement("right") == (0, 1.0, 0.35)
    assert builder.axis_position_for_placement("top") == (0, 0, 1.0)
    assert builder.axis_position_for_placement("bottom") == (0, 0, -1.0)


def test_aircraft_parts_use_generic_categories():
    builder = load_builder_module()

    assert builder.category_for_name("long aircraft fuselage", None) == "vehicle_fuselage"
    assert builder.category_for_name("left wing", None) == "vehicle_wing"
    assert builder.category_for_name("front nose cone", None) == "vehicle_nose"
    assert builder.category_for_name("tail fin", None) == "vehicle_tail"
    assert builder.category_for_name("rear engine", None) == "vehicle_engine"
    assert builder.component_position("left wing", 0) == (-0.05, -0.95, 0.58)
    assert builder.component_position("right wing", 0) == (-0.05, 0.95, 0.58)
    assert builder.component_position("front nose cone", 1) == (1.45, 0, 0.72)


def test_builder_prefers_structured_scene_plan_over_flat_components():
    builder = load_builder_module()
    spec = {
        "canonical_id": "vehicle_plane_A",
        "name": "Plane",
        "kind": "vehicle",
        "style": "minimalistic",
        "components": ["long aircraft fuselage", "left wing"],
        "repaired_scene_plan": {
            "objects": [
                {
                    "id": "plane_1",
                    "label": "plane",
                    "category": "vehicle",
                    "size": "large",
                    "placement": "center",
                    "mounting": "surface",
                }
            ],
            "relationships": [],
        },
    }

    items = builder.layout_items_for_spec(spec)

    assert items == [{
        "source": "scene_object",
        "value": spec["repaired_scene_plan"]["objects"][0],
    }]


def test_builder_falls_back_to_components_without_scene_objects():
    builder = load_builder_module()

    assert builder.layout_items_for_spec({
        "canonical_id": "vehicle_plane_A",
        "kind": "vehicle",
        "components": ["long aircraft fuselage", "left wing"],
    }) == [
        {"source": "component", "value": "long aircraft fuselage"},
        {"source": "component", "value": "left wing"},
    ]


def test_builder_fails_fast_without_scene_objects_or_components():
    builder = load_builder_module()

    with pytest.raises(ValueError, match="scene objects or non-empty components"):
        builder.components_for_layout({"canonical_id": "vehicle_plane_A", "kind": "vehicle"})


def test_scene_object_preserves_structured_render_hints():
    builder = load_builder_module()
    obj = {
        "id": "ship_wings",
        "label": "wing",
        "category": "structure",
        "count": 2,
        "size": "medium",
        "placement": "front",
        "mounting": "floor",
        "orientation": {"faces": "wing_front"},
    }

    assert builder.scene_object_category(obj) == "vehicle_wing"
    assert builder.scene_object_count(obj) == 2
    assert builder.scene_object_position(obj, 1, "vehicle_wing") == (-0.05, 0.95, 0.58)


def test_scene_object_tokens_include_structured_detail_fields():
    builder = load_builder_module()
    obj = {
        "id": "table_1",
        "label": "dining table",
        "category": "surface",
        "shape": {"corner_style": "rounded", "edge_profile": "soft_beveled"},
        "required_features": ["rounded_corners"],
        "source_phrases": ["rounded corners"],
        "materials": {"primary": "wood"},
        "style_details": ["thin legs"],
    }

    tokens = builder.scene_object_tokens(obj)

    assert "rounded" in tokens
    assert "corners" in tokens
    assert "soft" in tokens
    assert "beveled" in tokens
    assert "wood" in tokens
    assert "thin" in tokens
    assert "legs" in tokens


def test_structured_rounded_corner_table_builds_rounded_corner_parts(monkeypatch):
    builder = load_builder_module()
    created = []

    def fake_cube(name, location, scale, mat):
        created.append(("cube", name, location, scale))
        return types.SimpleNamespace(name=name)

    def fake_cylinder(name, location, radius, depth, mat, rotation=(0, 0, 0)):
        created.append(("cylinder", name, location, radius, depth))
        return types.SimpleNamespace(name=name)

    monkeypatch.setattr(builder, "cube", fake_cube)
    monkeypatch.setattr(builder, "cylinder", fake_cylinder)

    obj = {
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
    mats = {"wood": object(), "metal": object(), "neutral": object()}

    builder.primitive_for_scene_object(obj, 0, mats)

    rounded_corner_names = [entry[1] for entry in created if "rounded_corner" in entry[1]]
    assert rounded_corner_names == [
        "table_1_rounded_corner_1",
        "table_1_rounded_corner_2",
        "table_1_rounded_corner_3",
        "table_1_rounded_corner_4",
    ]


def test_vehicle_wing_count_offsets_across_left_right_axis():
    builder = load_builder_module()

    left, right = [
        builder.offset_position_for_category((-0.05, 0, 0.58), copy_idx, 2, "vehicle_wing")
        for copy_idx in range(2)
    ]

    assert left == (-0.05, -0.95, 0.58)
    assert right == (-0.05, 0.95, 0.58)


def test_location_shell_uses_kind_not_fuzzy_text():
    builder = load_builder_module()

    assert builder.uses_location_shell({"kind": "location"})
    assert builder.uses_location_shell({"kind": "set"})
    assert not builder.uses_location_shell({"kind": "vehicle", "name": "office rover"})


def test_assets_do_not_get_environment_shells():
    builder = load_builder_module()

    assert builder.layout_shell_descriptors({"kind": "vehicle"}) == []
    assert builder.layout_shell_descriptors({"kind": "prop"}) == []
    assert builder.layout_shell_descriptors({"kind": "asset"}) == []


def test_locations_keep_environment_shells():
    builder = load_builder_module()

    assert builder.layout_shell_descriptors({"kind": "location"}) == [
        ("layout_floor", (0, 0, -0.08), (6.2, 3.8, 0.1), "neutral"),
        ("layout_back_wall", (-3.1, 0, 1.0), (0.08, 3.8, 2.05), "light"),
    ]


def test_canonical_camera_views_match_oeb_axes():
    builder = load_builder_module()
    views = builder.canonical_camera_views()

    assert views["front"]["location"] == (6.4, 0, 0.45)
    assert views["rear"]["location"] == (-6.4, 0, 0.45)
    assert views["left"]["location"] == (0, -6.4, 0.45)
    assert views["right"]["location"] == (0, 6.4, 0.45)
    assert views["top"]["location"] == (0, 0, 6.4)
    assert views["bottom"]["location"] == (0, 0, -6.4)
