#!/usr/bin/env python3
"""Stage validated OEB assets and generate Godot interactive wrapper scenes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate_interactive import (
    InteractiveValidationError,
    load_json,
    resolve_contract_source,
    validate_project,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "interactive" / "journeyblaster"


def number(value: float) -> str:
    rendered = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return rendered if rendered not in {"-0", ""} else "0"


def vector3(values: list[float]) -> str:
    return f"Vector3({', '.join(number(value) for value in values)})"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scene_path_to_relative(scene_path: str) -> Path:
    if not scene_path.startswith("res://generated/"):
        raise InteractiveValidationError(
            f"generated wrapper scene must be under res://generated/: {scene_path}"
        )
    return Path(scene_path.removeprefix("res://generated/"))


def render_shape_subresource(shape: dict[str, Any], index: int) -> tuple[str, str]:
    identifier = f"Shape_{index}_{shape['shape_id']}"
    kind = shape["kind"]
    if kind == "box":
        lines = [f'[sub_resource type="BoxShape3D" id="{identifier}"]', f"size = {vector3(shape['size'])}"]
    elif kind == "sphere":
        lines = [f'[sub_resource type="SphereShape3D" id="{identifier}"]', f"radius = {number(shape['radius'])}"]
    elif kind == "capsule":
        lines = [
            f'[sub_resource type="CapsuleShape3D" id="{identifier}"]',
            f"radius = {number(shape['radius'])}",
            f"height = {number(shape['height'])}",
        ]
    else:
        raise InteractiveValidationError(f"unsupported collision shape kind: {kind}")
    return identifier, "\n".join(lines)


def render_wrapper(contract: dict[str, Any], staged_glb: str) -> str:
    is_pilotable = "pilotable" in contract.get("capabilities", [])
    is_destructible = "destructible" in contract.get("capabilities", [])
    destructible_script = contract.get("runtime", {}).get(
        "controller_script", "res://scripts/asteroid_destructible.gd"
    )
    shape_resources = [
        render_shape_subresource(shape, index)
        for index, shape in enumerate(contract["collision"], start=1)
    ]
    extra_resources = (2 if is_pilotable else 0) + (1 if is_destructible else 0)
    lines = [
        f"[gd_scene load_steps={2 + extra_resources + len(shape_resources)} format=3]",
        "",
        f'[ext_resource type="PackedScene" path="res://generated/assets/{staged_glb}" id="1_visual"]',
    ]
    if is_pilotable:
        lines.extend(
            [
                '[ext_resource type="Script" path="res://scripts/jb100_controller.gd" id="2_flight"]',
                '[ext_resource type="Script" path="res://scripts/pilot_view_controller.gd" id="3_view"]',
            ]
        )
    if is_destructible:
        lines.append(
            f'[ext_resource type="Script" path="{destructible_script}" id="4_destructible"]'
        )
    lines.append("")
    for _identifier, rendered in shape_resources:
        lines.extend([rendered, ""])

    root_type = contract["runtime"]["root_node_type"]
    lines.extend(
        [
            f'[node name="{contract["contract_id"]}" type="{root_type}"]',
            f'metadata/contract_id = "{contract["contract_id"]}"',
            f'metadata/asset_id = "{contract["asset_id"]}"',
            f'metadata/runtime_kind = "{contract["runtime"]["kind"]}"',
        ]
    )
    if root_type == "RigidBody3D":
        lines.extend(["freeze = true", "gravity_scale = 0.0"])
    if is_pilotable:
        lines.append('script = ExtResource("2_flight")')
    if is_destructible:
        lines.append('script = ExtResource("4_destructible")')
    lines.extend(
        [
            "",
            '[node name="Visual" parent="." instance=ExtResource("1_visual")]',
            f"rotation_degrees = {vector3(contract['orientation']['visual_rotation_degrees'])}",
            f"scale = {vector3(contract['visual']['scale'])}",
            "",
        ]
    )

    for shape, (identifier, _rendered) in zip(contract["collision"], shape_resources):
        lines.extend(
            [
                f'[node name="{shape["shape_id"]}" type="CollisionShape3D" parent="."]',
                f"position = {vector3(shape['position'])}",
                f"rotation_degrees = {vector3(shape['rotation_degrees'])}",
                f'shape = SubResource("{identifier}")',
                "",
            ]
        )

    for marker in contract.get("markers", []):
        if marker["role"] == "cockpit_camera":
            lines.extend(
                [
                    '[node name="SeatPivot" type="Node3D" parent="."]',
                    f"position = {vector3(marker['position'])}",
                    'script = ExtResource("3_view")',
                    'metadata/interactive_role = "rotating_pilot_chair"',
                    "",
                    f'[node name="{marker["marker_id"]}" type="Camera3D" parent="SeatPivot"]',
                    f"rotation_degrees = {vector3(marker['rotation_degrees'])}",
                    f'metadata/interactive_role = "{marker["role"]}"',
                    f"fov = {number(marker['fov_degrees'])}",
                    "current = true",
                    "",
                    '[node name="DebugCamera" type="Camera3D" parent="."]',
                    "position = Vector3(0, 7, 15)",
                    "rotation_degrees = Vector3(-16, 0, 0)",
                    "fov = 68.0",
                    "",
                ]
            )
            continue
        node_type = "Marker3D"
        lines.extend(
            [
                f'[node name="{marker["marker_id"]}" type="{node_type}" parent="."]',
                f"position = {vector3(marker['position'])}",
                f"rotation_degrees = {vector3(marker['rotation_degrees'])}",
                f'metadata/interactive_role = "{marker["role"]}"',
            ]
        )
        if "radius_m" in marker:
            lines.append(f'metadata/effect_exclusion_radius_m = {number(marker["radius_m"])}')
        if "clearance_m" in marker:
            lines.append(
                f'metadata/effect_exclusion_clearance_m = {number(marker["clearance_m"])}'
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_transform(transform: dict[str, Any]) -> list[str]:
    return [
        f"position = {vector3(transform['position'])}",
        f"rotation_degrees = {vector3(transform['rotation_degrees'])}",
        f"scale = {vector3(transform['scale'])}",
    ]


def render_mission_scene(mission: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> str:
    placements: list[tuple[str, str, dict[str, Any], str]] = []
    player = mission["player"]
    placements.append((player["instance_id"], player["contract_id"], player["spawn"], "player"))
    placements.extend(
        (item["instance_id"], item["contract_id"], item["transform"], "entity")
        for item in mission["entities"]
    )
    placements.extend(
        (item["instance_id"], item["contract_id"], item["transform"], "obstacle")
        for item in mission["environment"]["obstacles"]
    )

    ext_resources = [
        '[ext_resource type="Script" path="res://scripts/mission_boot.gd" id="1_boot"]'
    ]
    resource_ids: dict[str, str] = {}
    for index, contract_id in enumerate(dict.fromkeys(item[1] for item in placements), start=2):
        resource_id = f"{index}_{contract_id}"
        resource_ids[contract_id] = resource_id
        ext_resources.append(
            f'[ext_resource type="PackedScene" path="{contracts[contract_id]["runtime"]["wrapper_scene"]}" id="{resource_id}"]'
        )

    lines = [
        f"[gd_scene load_steps={len(ext_resources) + 4} format=3]",
        "",
        *ext_resources,
        "",
        '[sub_resource type="ProceduralSkyMaterial" id="SkyMaterial_deep_space"]',
        "sky_top_color = Color(0.002, 0.004, 0.012, 1)",
        "sky_horizon_color = Color(0.015, 0.025, 0.055, 1)",
        "ground_bottom_color = Color(0.001, 0.002, 0.006, 1)",
        "ground_horizon_color = Color(0.008, 0.012, 0.025, 1)",
        "sun_angle_max = 4.0",
        "",
        '[sub_resource type="Sky" id="Sky_deep_space"]',
        'sky_material = SubResource("SkyMaterial_deep_space")',
        "",
        '[sub_resource type="Environment" id="Environment_deep_space"]',
        "background_mode = 2",
        'sky = SubResource("Sky_deep_space")',
        "ambient_light_source = 3",
        "ambient_light_color = Color(0.22, 0.29, 0.42, 1)",
        "ambient_light_energy = 0.42",
        "tonemap_mode = 2",
        "",
        f'[node name="{mission["mission_id"]}" type="Node3D"]',
        'script = ExtResource("1_boot")',
        f'mission_data_path = "res://generated/data/missions/{mission["mission_id"]}.interactive.json"',
        "",
        '[node name="WorldEnvironment" type="WorldEnvironment" parent="."]',
        'environment = SubResource("Environment_deep_space")',
        "",
        '[node name="KeyLight" type="DirectionalLight3D" parent="."]',
        "rotation_degrees = Vector3(-32, -28, 12)",
        "light_color = Color(0.72, 0.82, 1, 1)",
        "light_energy = 1.35",
        "shadow_enabled = true",
        "",
        '[node name="WarmFill" type="DirectionalLight3D" parent="."]',
        "rotation_degrees = Vector3(18, 138, -8)",
        "light_color = Color(1, 0.38, 0.12, 1)",
        "light_energy = 0.38",
        "",
    ]

    for instance_id, contract_id, transform, role in placements:
        lines.extend(
            [
                f'[node name="{instance_id}" parent="." instance=ExtResource("{resource_ids[contract_id]}")]',
                *render_transform(transform),
                f'metadata/mission_role = "{role}"',
                "",
            ]
        )

    boundary = mission["environment"]["entry_boundary"]
    lines.extend(
        [
            f'[node name="{boundary["boundary_id"]}" type="Marker3D" parent="."]',
            f"position = {vector3(boundary['center'])}",
            f"metadata/radius_m = {number(boundary['radius_m'])}",
            'metadata/interactive_role = "return_boundary"',
            "",
            '[node name="HUD" type="CanvasLayer" parent="."]',
            "",
            '[node name="TopBar" type="ColorRect" parent="HUD"]',
            "offset_left = 20.0",
            "offset_top = 20.0",
            "offset_right = 760.0",
            "offset_bottom = 126.0",
            "color = Color(0.02, 0.035, 0.04, 0.88)",
            "",
            '[node name="Title" type="Label" parent="HUD/TopBar"]',
            "offset_left = 18.0",
            "offset_top = 12.0",
            "offset_right = 700.0",
            "offset_bottom = 34.0",
            'theme_override_colors/font_color = Color(0.38, 0.92, 0.67, 1)',
            "theme_override_font_sizes/font_size = 14",
            'text = "JOURNEYBLASTER · MISSION 001 · DEMO PROTOTYPE V2"',
            "",
            '[node name="Status" type="Label" parent="HUD/TopBar"]',
            "offset_left = 18.0",
            "offset_top = 38.0",
            "offset_right = 700.0",
            "offset_bottom = 62.0",
            'theme_override_colors/font_color = Color(0.92, 0.89, 0.79, 1)',
            "theme_override_font_sizes/font_size = 12",
            'text = "MISSION STATE · BRIEFING"',
            "",
            '[node name="Objective" type="Label" parent="HUD/TopBar"]',
            "offset_left = 18.0",
            "offset_top = 66.0",
            "offset_right = 710.0",
            "offset_bottom = 94.0",
            'theme_override_colors/font_color = Color(0.76, 0.84, 0.88, 1)',
            "theme_override_font_sizes/font_size = 13",
            'text = "Bring the JB100 online and enter the asteroid field."',
            "",
            '[node name="SensorPanel" type="ColorRect" parent="HUD"]',
            "anchors_preset = 1",
            "anchor_left = 1.0",
            "anchor_right = 1.0",
            "offset_left = -400.0",
            "offset_top = 20.0",
            "offset_right = -20.0",
            "offset_bottom = 146.0",
            "color = Color(0.055, 0.032, 0.012, 0.9)",
            "",
            '[node name="Sensor" type="Label" parent="HUD/SensorPanel"]',
            "offset_left = 18.0",
            "offset_top = 15.0",
            "offset_right = 360.0",
            "offset_bottom = 112.0",
            'theme_override_colors/font_color = Color(1, 0.63, 0.18, 1)',
            "theme_override_font_sizes/font_size = 13",
            'text = "SENSO-GLOBES · ACTIVE/PASSIVE\\nNO CONTACT"',
            "",
            '[node name="WeaponsPanel" type="ColorRect" parent="HUD"]',
            "anchors_preset = 1",
            "anchor_left = 1.0",
            "anchor_right = 1.0",
            "offset_left = -400.0",
            "offset_top = 158.0",
            "offset_right = -20.0",
            "offset_bottom = 278.0",
            "color = Color(0.018, 0.032, 0.07, 0.9)",
            "",
            '[node name="Weapons" type="Label" parent="HUD/WeaponsPanel"]',
            "offset_left = 18.0",
            "offset_top = 12.0",
            "offset_right = 360.0",
            "offset_bottom = 110.0",
            'theme_override_colors/font_color = Color(0.42, 0.68, 1, 1)',
            "theme_override_font_sizes/font_size = 13",
            'text = "WEAPONS\\nFRAPRAY  READY · SPACE\\nPROTON TORPEDO  08 · T\\nAIM HUD  ON · TAB"',
            "",
            '[node name="TelemetryPanel" type="ColorRect" parent="HUD"]',
            "anchors_preset = 2",
            "anchor_top = 1.0",
            "anchor_bottom = 1.0",
            "offset_left = 20.0",
            "offset_top = -178.0",
            "offset_right = 430.0",
            "offset_bottom = -20.0",
            "color = Color(0.02, 0.035, 0.04, 0.88)",
            "",
            '[node name="Flight" type="Label" parent="HUD/TelemetryPanel"]',
            "offset_left = 18.0",
            "offset_top = 15.0",
            "offset_right = 194.0",
            "offset_bottom = 140.0",
            'theme_override_colors/font_color = Color(0.38, 0.92, 0.67, 1)',
            "theme_override_font_sizes/font_size = 12",
            'text = "SHIP VECTOR\\nSPEED  000 m/s\\nTHROTTLE  0%\\nCOURSE LOCK  OFF"',
            "",
            '[node name="View" type="Label" parent="HUD/TelemetryPanel"]',
            "offset_left = 208.0",
            "offset_top = 15.0",
            "offset_right = 394.0",
            "offset_bottom = 140.0",
            'theme_override_colors/font_color = Color(0.92, 0.89, 0.79, 1)',
            "theme_override_font_sizes/font_size = 12",
            'text = "PILOT CHAIR\\nVIEW  FORWARD\\nSHIP HEADING INDEPENDENT"',
            "",
            '[node name="Help" type="Label" parent="HUD"]',
            "anchors_preset = 3",
            "anchor_left = 1.0",
            "anchor_top = 1.0",
            "anchor_right = 1.0",
            "anchor_bottom = 1.0",
            "offset_left = -760.0",
            "offset_top = -116.0",
            "offset_right = -20.0",
            "offset_bottom = -20.0",
            'theme_override_colors/font_color = Color(0.68, 0.72, 0.72, 0.86)',
            "theme_override_font_sizes/font_size = 11",
            'text = "W/S throttle · A/D or ←/→ turn · ↑/↓ pitch · Q/E roll · X dead stop · SPACE FRAPRAY · T TORPEDO\\nZ/C strafe · R/F lift · G interact · TAB aim HUD · RMB chair look · 1–5 views · L course lock · F3 exterior"',
            "horizontal_alignment = 2",
            "",
            '[node name="Prompt" type="Label" parent="HUD"]',
            "anchors_preset = 7",
            "anchor_left = 0.5",
            "anchor_top = 1.0",
            "anchor_right = 0.5",
            "anchor_bottom = 1.0",
            "offset_left = -260.0",
            "offset_top = -82.0",
            "offset_right = 260.0",
            "offset_bottom = -38.0",
            'theme_override_colors/font_color = Color(1, 0.68, 0.22, 1)',
            "theme_override_font_sizes/font_size = 18",
            'text = "ENTER · BEGIN MISSION"',
            "horizontal_alignment = 1",
            "",
            '[node name="WeaponAim" type="Control" parent="HUD"]',
            "layout_mode = 3",
            "anchors_preset = 15",
            "anchor_right = 1.0",
            "anchor_bottom = 1.0",
            "grow_horizontal = 2",
            "grow_vertical = 2",
            "mouse_filter = 2",
            "",
            '[node name="FrapRayLeft" type="Label" parent="HUD/WeaponAim"]',
            "offset_right = 17.0",
            "offset_bottom = 17.0",
            'theme_override_colors/font_color = Color(1, 0.12, 0.08, 0.98)',
            "theme_override_font_sizes/font_size = 14",
            'text = "•"',
            "horizontal_alignment = 1",
            "vertical_alignment = 1",
            "",
            '[node name="FrapRayRight" type="Label" parent="HUD/WeaponAim"]',
            "offset_right = 17.0",
            "offset_bottom = 17.0",
            'theme_override_colors/font_color = Color(1, 0.12, 0.08, 0.98)',
            "theme_override_font_sizes/font_size = 14",
            'text = "•"',
            "horizontal_alignment = 1",
            "vertical_alignment = 1",
            "",
            '[node name="Torpedo" type="Label" parent="HUD/WeaponAim"]',
            "offset_right = 17.0",
            "offset_bottom = 17.0",
            'theme_override_colors/font_color = Color(1, 0.12, 0.08, 0.98)',
            "theme_override_font_sizes/font_size = 14",
            'text = "×"',
            "horizontal_alignment = 1",
            "vertical_alignment = 1",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def sync_project(root: Path, runtime_root: Path) -> dict[str, Any]:
    contracts, missions = validate_project(root)
    config = load_json(root / "oeb.config.json")
    asset_root = root / config.get("asset_root", "assets")
    runtime_root.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".generated-", dir=runtime_root))
    manifest_assets: list[dict[str, Any]] = []
    manifest_missions: list[dict[str, Any]] = []
    try:
        (temp_root / "assets").mkdir(parents=True)
        (temp_root / "scenes" / "missions").mkdir(parents=True)
        (temp_root / "data" / "missions").mkdir(parents=True)
        for contract_id, contract in sorted(contracts.items()):
            entry = config["assets"][contract["source"]["config_asset_id"]]
            source_path = resolve_contract_source(root, asset_root, entry, contract)
            staged_name = f"{contract['asset_id']}{source_path.suffix.lower()}"
            staged_path = temp_root / "assets" / staged_name
            shutil.copy2(source_path, staged_path)
            source_hash = sha256(source_path)
            if sha256(staged_path) != source_hash:
                raise InteractiveValidationError(
                    f"staged asset hash mismatch for {contract_id}: {source_path}"
                )
            wrapper_relpath = scene_path_to_relative(contract["runtime"]["wrapper_scene"])
            wrapper_path = temp_root / wrapper_relpath
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            wrapper_path.write_text(render_wrapper(contract, staged_name), encoding="utf-8")
            manifest_assets.append(
                {
                    "contract_id": contract_id,
                    "asset_id": contract["asset_id"],
                    "source": str(source_path.relative_to(root)),
                    "sha256": source_hash,
                    "staged": f"generated/assets/{staged_name}",
                    "wrapper_scene": contract["runtime"]["wrapper_scene"],
                }
            )

        mission_source_dir = root / "data" / "interactive" / "missions"
        for mission_id, mission in sorted(missions.items()):
            source_path = mission_source_dir / f"{mission_id}.interactive.json"
            staged_path = temp_root / "data" / "missions" / source_path.name
            shutil.copy2(source_path, staged_path)
            mission_scene_relpath = scene_path_to_relative(mission["runtime_scene"])
            mission_scene_path = temp_root / mission_scene_relpath
            mission_scene_path.parent.mkdir(parents=True, exist_ok=True)
            mission_scene_path.write_text(
                render_mission_scene(mission, contracts), encoding="utf-8"
            )
            manifest_missions.append(
                {
                    "mission_id": mission_id,
                    "source": str(source_path.relative_to(root)),
                    "sha256": sha256(source_path),
                    "runtime_scene": mission["runtime_scene"],
                }
            )

        manifest = {
            "schema_version": "1.0.0",
            "generated_by": "tools/sync_interactive_assets.py",
            "assets": manifest_assets,
            "missions": manifest_missions,
        }
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        generated_root = runtime_root / "generated"
        if generated_root.exists():
            shutil.rmtree(generated_root)
        temp_root.rename(generated_root)
        return manifest
    except Exception:
        if temp_root.exists():
            shutil.rmtree(temp_root)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    args = parser.parse_args()
    try:
        manifest = sync_project(args.project_root.resolve(), args.runtime_root.resolve())
    except InteractiveValidationError as exc:
        for line in str(exc).splitlines():
            print(f"INTERACTIVE-SYNC-ERROR: {line}", file=sys.stderr)
        return 2
    print(
        f"INTERACTIVE-SYNC-OK assets={len(manifest['assets'])} "
        f"missions={len(manifest['missions'])} runtime={args.runtime_root.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
