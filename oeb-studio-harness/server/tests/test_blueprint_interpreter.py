import importlib.util
import json
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
    # Vector/Quaternion are only exercised for real in _look_at_rotation,
    # which every test here monkeypatches around (same pattern as
    # bevel/mirror/array) rather than mocking mathutils's real vector
    # math -- these bare placeholders just need to make the module import.
    sys.modules.setdefault(
        "mathutils", types.SimpleNamespace(Vector=lambda value: value, Quaternion=lambda *a: None)
    )
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


def test_build_primitive_dispatches_empty(monkeypatch):
    interpreter = load_interpreter_module()
    captured = {}

    def fake_empty(name, location):
        captured.update(name=name, location=location)
        return FakeObj(rotation_euler=None)

    monkeypatch.setattr(interpreter, "empty", fake_empty)
    monkeypatch.setattr(interpreter, "material", lambda name, color: f"mat:{color}")

    obj = interpreter.build_primitive(
        {"id": "mark_entry", "type": "empty", "transform": {"location": [1, 2, 3]}},
        {},
    )

    assert captured["name"] == "mark_entry"
    assert captured["location"] == (1.0, 2.0, 3.0)
    assert obj.rotation_euler == (0.0, 0.0, 0.0)


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
    monkeypatch.setitem(
        interpreter.OPERATIONS, "bevel", lambda obj, params, ctx: calls.append((obj, params, ctx))
    )

    fake_obj = FakeObj()
    interpreter.apply_operation(
        {"op": "bevel", "target": "body", "params": {"width": 0.1}},
        {"body": fake_obj},
        {"frame_start": 1, "frame_end": 10},
    )

    assert calls == [(fake_obj, {"width": 0.1}, {"frame_start": 1, "frame_end": 10})]


def test_apply_operation_unknown_op_raises():
    interpreter = load_interpreter_module()
    with pytest.raises(ValueError, match="Unknown operation"):
        interpreter.apply_operation({"op": "extrude", "target": "body"}, {"body": FakeObj()}, {})


def test_apply_operation_unknown_target_raises():
    interpreter = load_interpreter_module()
    with pytest.raises(ValueError, match="unknown target"):
        interpreter.apply_operation({"op": "bevel", "target": "missing"}, {}, {})


def test_apply_camera_keyframe_dispatches_via_reserved_camera_id(monkeypatch):
    interpreter = load_interpreter_module()
    calls = []
    monkeypatch.setitem(
        interpreter.OPERATIONS,
        "set_camera_keyframe",
        lambda obj, params, ctx: calls.append((obj, params, ctx)),
    )

    fake_camera = FakeObj()
    interpreter.apply_operation(
        {"op": "set_camera_keyframe", "target": "camera", "params": {"frame": 1}},
        {"camera": fake_camera},
        {"frame_start": 1, "frame_end": 193},
    )

    assert calls == [(fake_camera, {"frame": 1}, {"frame_start": 1, "frame_end": 193})]


def test_validate_frame_rejects_out_of_range():
    interpreter = load_interpreter_module()
    ctx = {"frame_start": 1, "frame_end": 100}
    assert interpreter._validate_frame(50, ctx) == 50
    with pytest.raises(ValueError, match="outside this Blueprint's frame_range"):
        interpreter._validate_frame(101, ctx)


def test_apply_frame_range_rejects_end_before_start(monkeypatch):
    interpreter = load_interpreter_module()
    monkeypatch.setattr(
        interpreter,
        "bpy",
        types.SimpleNamespace(context=types.SimpleNamespace(scene=types.SimpleNamespace(render=types.SimpleNamespace()))),
    )
    with pytest.raises(ValueError, match="frame_range.end"):
        interpreter._apply_frame_range({"frame_range": {"start": 10, "end": 5}})


def test_apply_frame_range_rejects_non_positive_fps(monkeypatch):
    interpreter = load_interpreter_module()
    monkeypatch.setattr(
        interpreter,
        "bpy",
        types.SimpleNamespace(context=types.SimpleNamespace(scene=types.SimpleNamespace(render=types.SimpleNamespace()))),
    )
    with pytest.raises(ValueError, match="fps must be positive"):
        interpreter._apply_frame_range({"frame_range": {"start": 1, "end": 10, "fps": 0}})


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

    fake_ctx = {"frame_start": 1, "frame_end": 250, "fps": 24.0}

    def fake_ensure_camera(objects_by_id):
        camera = FakeObj(name="camera")
        objects_by_id["camera"] = camera
        return camera

    monkeypatch.setattr(interpreter, "clear_scene", lambda: None)
    monkeypatch.setattr(interpreter, "_apply_frame_range", lambda blueprint: fake_ctx)
    monkeypatch.setattr(interpreter.bpy, "data", types.SimpleNamespace(actions=[], objects=[]), raising=False)
    monkeypatch.setattr(interpreter, "_ensure_camera", fake_ensure_camera)
    monkeypatch.setattr(interpreter, "_add_preview_light", lambda: None)
    monkeypatch.setattr(interpreter, "_setup_default_preview_camera", lambda camera_obj: None)
    monkeypatch.setattr(interpreter, "cube", fake_cube)
    monkeypatch.setattr(interpreter, "material", lambda name, color: f"mat:{color}")
    monkeypatch.setitem(
        interpreter.OPERATIONS, "bevel", lambda obj, params, ctx: op_calls.append((obj.name, params, ctx))
    )
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

    root, applied_ops, ctx, variant = interpreter.build_blueprint(blueprint)

    assert root.name == "prop_test_A"
    assert op_calls == [("body", {"width": 0.05}, fake_ctx)]
    assert applied_ops == [{"op": "bevel", "target": "body"}]
    assert ctx == fake_ctx
    assert variant is None
    # Camera is registered for operation targeting but excluded from what
    # gets parented under the asset root -- it's a scene-level sibling,
    # not asset geometry (see build_blueprint's comment).
    assert roots == [("prop_test_A", [created_objects["body"]])]


def _fake_import_bpy(gltf_calls, objects_by_name):
    return types.SimpleNamespace(
        ops=types.SimpleNamespace(
            import_scene=types.SimpleNamespace(
                gltf=lambda filepath: gltf_calls.append(filepath)
            )
        ),
        data=types.SimpleNamespace(objects=types.SimpleNamespace(get=objects_by_name.get)),
    )


def test_build_import_primitive_resolves_and_applies_transform(monkeypatch, tmp_path):
    interpreter = load_interpreter_module()
    gltf_calls = []
    node_obj = FakeObj(name="set_bar_small_A", location=(0, 0, 0), rotation_euler=(0, 0, 0), scale=(1, 1, 1))
    monkeypatch.setattr(interpreter, "bpy", _fake_import_bpy(gltf_calls, {"set_bar_small_A": node_obj}))

    glb_path = tmp_path / "sets" / "bar_scene_scifi.glb"
    glb_path.parent.mkdir(parents=True)
    glb_path.write_bytes(b"")  # only existence is checked

    import_ctx = {
        "config": {"assets": {"set_bar_small_A": {"file": "sets/bar_scene_scifi.glb", "node": "set_bar_small_A"}}},
        "asset_root": tmp_path,
        "imported_files": set(),
    }

    obj = interpreter.build_import_primitive(
        {"id": "logo", "type": "import", "canonical_id": "set_bar_small_A",
         "transform": {"location": [1, 2, 3]}},
        import_ctx,
    )

    assert gltf_calls == [str(glb_path)]
    assert obj is node_obj
    assert obj.name == "logo"  # renamed from the source node name to the Blueprint's local id
    assert obj.location == (1.0, 2.0, 3.0)
    assert obj.rotation_euler == (0.0, 0.0, 0.0)  # default, not specified
    assert obj.scale == (1.0, 1.0, 1.0)


def test_build_import_primitive_dedupes_same_glb(monkeypatch, tmp_path):
    interpreter = load_interpreter_module()
    gltf_calls = []
    objects_by_name = {
        "prop_bar_counter_A": FakeObj(name="prop_bar_counter_A", location=(0, 0, 0), rotation_euler=(0, 0, 0), scale=(1, 1, 1)),
        "prop_stool_A": FakeObj(name="prop_stool_A", location=(0, 0, 0), rotation_euler=(0, 0, 0), scale=(1, 1, 1)),
    }
    monkeypatch.setattr(interpreter, "bpy", _fake_import_bpy(gltf_calls, objects_by_name))

    glb_path = tmp_path / "sets" / "bar_scene_scifi.glb"
    glb_path.parent.mkdir(parents=True)
    glb_path.write_bytes(b"")

    import_ctx = {
        "config": {"assets": {
            "prop_bar_counter_A": {"file": "sets/bar_scene_scifi.glb", "node": "prop_bar_counter_A"},
            "prop_stool_A": {"file": "sets/bar_scene_scifi.glb", "node": "prop_stool_A"},
        }},
        "asset_root": tmp_path,
        "imported_files": set(),
    }

    interpreter.build_import_primitive({"id": "counter", "type": "import", "canonical_id": "prop_bar_counter_A"}, import_ctx)
    interpreter.build_import_primitive({"id": "stool", "type": "import", "canonical_id": "prop_stool_A"}, import_ctx)

    # Same source file referenced by two import primitives -- imported once.
    assert gltf_calls == [str(glb_path)]


def test_build_import_primitive_unknown_canonical_id_raises():
    interpreter = load_interpreter_module()
    import_ctx = {"config": {"assets": {}}, "asset_root": Path("/tmp"), "imported_files": set()}
    with pytest.raises(ValueError, match="not found in oeb.config.json"):
        interpreter.build_import_primitive({"id": "x", "type": "import", "canonical_id": "missing_A"}, import_ctx)


def test_build_import_primitive_missing_file_raises(tmp_path, monkeypatch):
    interpreter = load_interpreter_module()
    monkeypatch.setattr(interpreter, "bpy", _fake_import_bpy([], {}))
    import_ctx = {
        "config": {"assets": {"x_A": {"file": "does/not/exist.glb", "node": "x_A"}}},
        "asset_root": tmp_path,
        "imported_files": set(),
    }
    with pytest.raises(ValueError, match="not found"):
        interpreter.build_import_primitive({"id": "x", "type": "import", "canonical_id": "x_A"}, import_ctx)


def test_load_import_config_resolves_relative_asset_root(tmp_path):
    interpreter = load_interpreter_module()
    config_path = tmp_path / "oeb.config.json"
    config_path.write_text(json.dumps({"asset_root": "assets", "assets": {}}))

    import_ctx = interpreter.load_import_config(config_path)

    assert import_ctx["asset_root"] == interpreter.PROJECT_ROOT / "assets"
    assert import_ctx["imported_files"] == set()


def test_build_blueprint_routes_import_type_to_build_import_primitive(monkeypatch):
    interpreter = load_interpreter_module()
    import_calls = []

    def fake_ensure_camera(objects_by_id):
        camera = FakeObj(name="camera")
        objects_by_id["camera"] = camera
        return camera

    def fake_build_import_primitive(spec, import_ctx):
        import_calls.append((spec["id"], import_ctx))
        return FakeObj(name=spec["id"], parent=None)

    monkeypatch.setattr(interpreter, "clear_scene", lambda: None)
    monkeypatch.setattr(interpreter, "_apply_frame_range", lambda blueprint: {"frame_start": 1, "frame_end": 10, "fps": 24.0})
    monkeypatch.setattr(interpreter.bpy, "data", types.SimpleNamespace(actions=[], objects=[]), raising=False)
    monkeypatch.setattr(interpreter, "_ensure_camera", fake_ensure_camera)
    monkeypatch.setattr(interpreter, "_add_preview_light", lambda: None)
    monkeypatch.setattr(interpreter, "_setup_default_preview_camera", lambda camera_obj: None)
    monkeypatch.setattr(interpreter, "load_import_config", lambda path: {"loaded_from": path})
    monkeypatch.setattr(interpreter, "build_import_primitive", fake_build_import_primitive)
    monkeypatch.setattr(interpreter, "parent_to_root", lambda canonical_id, objects: FakeObj(name=canonical_id))

    blueprint = {
        "canonical_id": "prop_test_A",
        "primitives": [{"id": "logo", "type": "import", "canonical_id": "set_bar_small_A"}],
        "operations": [],
    }

    interpreter.build_blueprint(blueprint, config_path="/fake/oeb.config.json")

    assert import_calls == [("logo", {"loaded_from": "/fake/oeb.config.json"})]


def _fake_bsdf_material():
    class FakeInput:
        def __init__(self, value):
            self.default_value = value

    inputs = {
        "Roughness": FakeInput(0.5),
        "Metallic": FakeInput(0.0),
        "Base Color": FakeInput((0.6, 0.6, 0.6, 1.0)),
    }
    bsdf = types.SimpleNamespace(inputs=inputs)
    node_tree = types.SimpleNamespace(nodes={"Principled BSDF": bsdf})
    return types.SimpleNamespace(use_nodes=True, node_tree=node_tree), inputs


def test_apply_set_material_updates_existing_bsdf_inputs():
    interpreter = load_interpreter_module()
    mat, inputs = _fake_bsdf_material()
    obj = FakeObj(material_slots=[types.SimpleNamespace(material=mat)])

    interpreter._apply_set_material(obj, {"roughness": 0.1, "metallic": 0.9, "color": [0.8, 0.1, 0.1, 1.0]}, {})

    assert inputs["Roughness"].default_value == 0.1
    assert inputs["Metallic"].default_value == 0.9
    assert inputs["Base Color"].default_value == (0.8, 0.1, 0.1, 1.0)


def test_apply_set_material_skips_slots_with_no_material():
    interpreter = load_interpreter_module()
    obj = FakeObj(material_slots=[types.SimpleNamespace(material=None)])

    # Must not raise even though the slot has nothing to update.
    interpreter._apply_set_material(obj, {"roughness": 0.2}, {})


def test_apply_set_shape_detail_routes_rounded_to_bevel(monkeypatch):
    interpreter = load_interpreter_module()
    calls = []
    monkeypatch.setattr(
        interpreter, "_apply_bevel", lambda obj, params, ctx: calls.append((obj, params))
    )
    fake_obj = FakeObj()

    interpreter._apply_set_shape_detail(fake_obj, {"corner_style": "rounded"}, {})

    assert calls == [(fake_obj, {"width": 0.04, "segments": 4})]


def test_apply_set_shape_detail_prefers_edge_profile_over_corner_style(monkeypatch):
    interpreter = load_interpreter_module()
    calls = []
    monkeypatch.setattr(
        interpreter, "_apply_bevel", lambda obj, params, ctx: calls.append(params)
    )

    interpreter._apply_set_shape_detail(
        FakeObj(), {"corner_style": "rounded", "edge_profile": "beveled"}, {}
    )

    assert calls == [{"width": 0.02, "segments": 1}]


def test_apply_set_shape_detail_unrecognized_style_applies_nothing(monkeypatch):
    interpreter = load_interpreter_module()
    calls = []
    monkeypatch.setattr(interpreter, "_apply_bevel", lambda obj, params, ctx: calls.append(1))

    interpreter._apply_set_shape_detail(FakeObj(), {"corner_style": "spiky"}, {})

    assert calls == []


def test_set_environment_is_a_scene_level_operation_not_target_resolved():
    interpreter = load_interpreter_module()
    assert "set_environment" in interpreter.SCENE_LEVEL_OPERATIONS
    assert "set_environment" in interpreter.OPERATIONS


def test_apply_operation_dispatches_scene_level_op_without_target_lookup(monkeypatch):
    interpreter = load_interpreter_module()
    calls = []
    monkeypatch.setitem(
        interpreter.OPERATIONS, "set_environment", lambda params, ctx: calls.append(params)
    )

    # objects_by_id is empty and target "camera" is never looked up --
    # scene-level ops must not require a resolvable target object.
    interpreter.apply_operation(
        {"op": "set_environment", "target": "camera", "params": {"preset": "deep_space"}},
        {},
        {},
    )

    assert calls == [{"preset": "deep_space"}]


def test_apply_operation_unknown_environment_preset_raises():
    interpreter = load_interpreter_module()
    with pytest.raises(ValueError, match="Unknown set_environment preset"):
        interpreter._apply_set_environment({"preset": "sunset_beach"}, {})


def test_play_fx_cue_is_target_scoped_not_scene_level():
    interpreter = load_interpreter_module()
    assert "play_fx_cue" in interpreter.OPERATIONS
    assert "play_fx_cue" not in interpreter.SCENE_LEVEL_OPERATIONS


def test_play_fx_cue_missing_root_raises(monkeypatch):
    interpreter = load_interpreter_module()
    monkeypatch.setattr(
        interpreter.bpy, "data",
        types.SimpleNamespace(objects=types.SimpleNamespace(get=lambda name: None)),
        raising=False,
    )
    with pytest.raises(ValueError, match="fx_root_id"):
        interpreter._apply_play_fx_cue(
            object(), {"frame": 1, "fx_root_id": "HYPERSPACE_EVENT_ROOT"},
            {"fps": 24, "frame_start": 1, "frame_end": 100},
        )
