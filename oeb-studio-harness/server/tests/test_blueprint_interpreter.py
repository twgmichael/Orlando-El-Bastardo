import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest


def _find_tool_path(filename: str) -> Path:
    """Locate a tools/<filename> script across run environments.

    Same resolution order as test_primitive_builder_routing.py's
    _find_primitive_builder_path: env override, the Docker container's
    read-only /tools mount, then walking up from this file to find a
    sibling tools/ directory (bare host checkout, any nesting depth).
    """
    env_override = os.environ.get("OEB_TOOLS_DIR")
    candidates = []
    if env_override:
        candidates.append(Path(env_override) / filename)
    candidates.append(Path("/tools") / filename)
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "tools" / filename)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not locate tools/{filename}. Set OEB_TOOLS_DIR to its "
        "containing directory if running outside the repo checkout or "
        "the oeb-studio-harness-local Docker stack."
    )


def load_interpreter_module():
    sys.modules.setdefault("bpy", types.SimpleNamespace())
    sys.modules.setdefault("mathutils", types.SimpleNamespace(Vector=lambda value: value))
    # oeb_blender.primitives is a real import (not loaded via file-location
    # trick), so it needs tools/ on sys.path -- the module under test does
    # this itself via sys.path.insert, but that only runs once it's
    # imported, so make sure it's importable before exec_module runs too.
    tools_dir = str(_find_tool_path("blueprint_interpreter.py").parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    spec = importlib.util.spec_from_file_location(
        "blueprint_interpreter_for_test",
        _find_tool_path("blueprint_interpreter.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeObj(types.SimpleNamespace):
    pass


def test_build_primitive_dispatches_cube(monkeypatch):
    interpreter = load_interpreter_module()
    captured = {}

    def fake_cube(name, location, scale, mat):
        captured.update(name=name, location=location, scale=scale, mat=mat)
        return FakeObj(rotation_euler=None)

    monkeypatch.setattr(interpreter, "cube", fake_cube)
    monkeypatch.setattr(interpreter, "material", lambda name, color: f"mat:{color}")

    obj = interpreter.build_primitive(
        {
            "id": "body",
            "type": "cube",
            "transform": {"location": [1, 2, 3], "rotation": [0, 0, 0.5], "scale": [2, 2, 2]},
            "material": {"color": [0.1, 0.2, 0.3, 1.0]},
        },
        {},
    )

    assert captured["name"] == "body"
    assert captured["location"] == (1.0, 2.0, 3.0)
    assert captured["scale"] == (2.0, 2.0, 2.0)
    assert obj.rotation_euler == (0.0, 0.0, 0.5)


def test_build_primitive_dispatches_cylinder_uses_scale_as_radius_depth(monkeypatch):
    interpreter = load_interpreter_module()
    captured = {}

    def fake_cylinder(name, location, radius, depth, mat, rotation=(0, 0, 0)):
        captured.update(name=name, radius=radius, depth=depth, rotation=rotation)
        return FakeObj()

    monkeypatch.setattr(interpreter, "cylinder", fake_cylinder)
    monkeypatch.setattr(interpreter, "material", lambda name, color: f"mat:{color}")

    interpreter.build_primitive(
        {
            "id": "post",
            "type": "cylinder",
            "transform": {"location": [0, 0, 0], "scale": [0.3, 0.3, 1.5]},
        },
        {},
    )

    assert captured["radius"] == 0.3
    assert captured["depth"] == 1.5


def test_build_primitive_unknown_type_raises():
    interpreter = load_interpreter_module()
    with pytest.raises(ValueError, match="Unknown primitive type"):
        interpreter.build_primitive({"id": "x", "type": "dodecahedron"}, {})


def test_material_for_caches_by_color():
    interpreter = load_interpreter_module()
    created = []

    def fake_material(name, color):
        created.append((name, color))
        return f"mat:{color}"

    interpreter.material = fake_material

    cache = {}
    mat_a = interpreter._material_for({"color": [1, 0, 0, 1]}, cache)
    mat_b = interpreter._material_for({"color": [1, 0, 0, 1]}, cache)
    mat_c = interpreter._material_for({"color": [0, 1, 0, 1]}, cache)

    assert mat_a is mat_b
    assert mat_a != mat_c
    assert len(created) == 2


def test_apply_operation_dispatches_to_registered_op(monkeypatch):
    interpreter = load_interpreter_module()
    calls = []
    monkeypatch.setitem(interpreter.OPERATIONS, "bevel", lambda obj, params: calls.append((obj, params)))

    fake_obj = FakeObj()
    interpreter.apply_operation(
        {"op": "bevel", "target": "body", "params": {"width": 0.1}},
        {"body": fake_obj},
    )

    assert calls == [(fake_obj, {"width": 0.1})]


def test_apply_operation_unknown_op_raises():
    interpreter = load_interpreter_module()
    with pytest.raises(ValueError, match="Unknown operation"):
        interpreter.apply_operation({"op": "extrude", "target": "body"}, {"body": FakeObj()})


def test_apply_operation_unknown_target_raises():
    interpreter = load_interpreter_module()
    with pytest.raises(ValueError, match="unknown target"):
        interpreter.apply_operation({"op": "bevel", "target": "missing"}, {})


def test_build_blueprint_wires_primitives_operations_and_root(monkeypatch):
    interpreter = load_interpreter_module()
    created_objects = {}

    def fake_cube(name, location, scale, mat):
        obj = FakeObj(name=name, rotation_euler=(0, 0, 0), parent=None)
        created_objects[name] = obj
        return obj

    op_calls = []
    roots = []

    def fake_parent_to_root(canonical_id, objects):
        root = FakeObj(name=canonical_id, is_root=True)
        roots.append((canonical_id, list(objects)))
        return root

    monkeypatch.setattr(interpreter, "clear_scene", lambda: None)
    monkeypatch.setattr(interpreter, "cube", fake_cube)
    monkeypatch.setattr(interpreter, "material", lambda name, color: f"mat:{color}")
    monkeypatch.setitem(interpreter.OPERATIONS, "bevel", lambda obj, params: op_calls.append((obj.name, params)))
    monkeypatch.setattr(interpreter, "parent_to_root", fake_parent_to_root)

    blueprint = {
        "canonical_id": "prop_test_A",
        "primitives": [
            {"id": "body", "type": "cube", "transform": {"scale": [1, 1, 1]}},
        ],
        "operations": [
            {"op": "bevel", "target": "body", "params": {"width": 0.05}},
        ],
    }

    root, applied_ops = interpreter.build_blueprint(blueprint)

    assert root.name == "prop_test_A"
    assert op_calls == [("body", {"width": 0.05})]
    assert applied_ops == [{"op": "bevel", "target": "body"}]
    assert roots == [("prop_test_A", [created_objects["body"]])]
