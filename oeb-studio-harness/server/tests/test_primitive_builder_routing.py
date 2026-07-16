import importlib.util
import sys
import types
from pathlib import Path


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


def test_motorcycle_routes_to_vehicle_and_motorcycle_builder():
    builder = load_builder_module()
    spec = {
        "canonical_id": "vehicle_motorcycle_A",
        "name": "Motorcycle",
        "kind": "vehicle",
        "style": "modern metallic",
        "components": ["front wheel", "rear wheel", "handlebars"],
    }

    assert builder.wants_vehicle(spec)
    assert builder.wants_motorcycle(spec)


def test_motorcycle_detection_does_not_catch_generic_bike_rack():
    builder = load_builder_module()
    spec = {
        "canonical_id": "prop_bike_rack_A",
        "name": "Bike Rack",
        "kind": "prop",
        "style": "metal",
        "components": ["rack rails"],
    }

    assert not builder.wants_motorcycle(spec)
