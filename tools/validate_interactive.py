#!/usr/bin/env python3
"""Validate OEB interactive asset contracts and declarative missions.

This validator is read-only. It checks JSON Schema structure, canonical asset
registry references, source files, capability/marker invariants, mission
references, sensor ordering, and deterministic mission dependency ordering.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InteractiveValidationError(RuntimeError):
    """One or more interactive-contract validation gates failed."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InteractiveValidationError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InteractiveValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InteractiveValidationError(f"expected JSON object in {path}")
    return value


def validate_schema(document: dict[str, Any], schema: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{path}: {location}: {error.message}")
    return errors


def marker_roles(contract: dict[str, Any]) -> set[str]:
    return {marker["role"] for marker in contract.get("markers", [])}


def validate_contract_invariants(contract: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    capabilities = set(contract.get("capabilities", []))
    roles = marker_roles(contract)
    required_markers = {
        "pilotable": {"cockpit_camera"},
        "sensor_source": {"sensor_origin"},
        "sensor_target": {"sensor_signature"},
        "data_download": {"data_port"},
        "tow_source": {"probe_tow_origin"},
        "tow_target": {"tow_anchor"},
        "weapon_source": {
            "frap_hardpoint_left",
            "frap_hardpoint_right",
            "torpedo_launcher",
        },
    }
    for capability, required_roles in required_markers.items():
        if capability in capabilities:
            missing = required_roles - roles
            if missing:
                errors.append(
                    f"{path}: capability {capability!r} requires marker roles {sorted(missing)}"
                )
    if "pilotable" in capabilities and not contract.get("controller_profile"):
        errors.append(f"{path}: pilotable assets require controller_profile")
    if "beacon" in capabilities and "beacon" not in contract.get("animation_bindings", {}):
        errors.append(f"{path}: beacon capability requires animation_bindings.beacon")
    marker_ids = [marker["marker_id"] for marker in contract.get("markers", [])]
    if len(marker_ids) != len(set(marker_ids)):
        errors.append(f"{path}: marker_id values must be unique")
    shape_ids = [shape["shape_id"] for shape in contract.get("collision", [])]
    if len(shape_ids) != len(set(shape_ids)):
        errors.append(f"{path}: collision shape_id values must be unique")
    return errors


def load_contracts(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Path], list[str]]:
    schema = load_json(root / "schemas" / "interactive-asset.schema.json")
    contracts: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    errors: list[str] = []
    source_dir = root / "data" / "interactive" / "asset_contracts"
    for path in sorted(source_dir.glob("*.interactive.json")):
        document = load_json(path)
        errors.extend(validate_schema(document, schema, path))
        errors.extend(validate_contract_invariants(document, path))
        contract_id = document.get("contract_id")
        if isinstance(contract_id, str):
            if contract_id in contracts:
                errors.append(f"{path}: duplicate contract_id {contract_id!r}")
            else:
                contracts[contract_id] = document
                paths[contract_id] = path
    if not contracts:
        errors.append(f"no interactive asset contracts found in {source_dir}")
    return contracts, paths, errors


def resolve_contract_source(
    root: Path,
    asset_root: Path,
    registry_entry: dict[str, Any],
    contract: dict[str, Any],
) -> Path:
    canonical_path = asset_root / registry_entry["file"]
    if canonical_path.is_file():
        return canonical_path
    fallback = contract["source"].get("deterministic_fallback")
    if isinstance(fallback, dict):
        fallback_path = root / fallback["file"]
        if fallback_path.is_file():
            return fallback_path
        raise InteractiveValidationError(
            f"canonical source asset is missing: {canonical_path}; deterministic "
            f"fallback is also missing: {fallback_path} (run: {fallback['builder']})"
        )
    raise InteractiveValidationError(
        f"canonical source asset is missing: {canonical_path} "
        "(run its registered deterministic builder before sync)"
    )


def validate_registered_sources(
    root: Path,
    contracts: dict[str, dict[str, Any]],
    contract_paths: dict[str, Path],
) -> list[str]:
    config = load_json(root / "oeb.config.json")
    assets = config.get("assets", {})
    asset_root = root / config.get("asset_root", "assets")
    errors: list[str] = []
    for contract_id, contract in contracts.items():
        path = contract_paths[contract_id]
        source = contract["source"]
        config_id = source["config_asset_id"]
        entry = assets.get(config_id)
        if not isinstance(entry, dict):
            errors.append(f"{path}: source config asset {config_id!r} is not registered")
            continue
        if contract["asset_id"] != config_id:
            errors.append(f"{path}: asset_id must equal source.config_asset_id")
        if entry.get("node") != source["expected_node"]:
            errors.append(
                f"{path}: expected node {source['expected_node']!r} does not match "
                f"oeb.config.json node {entry.get('node')!r}"
            )
        relpath = entry.get("file")
        if not isinstance(relpath, str) or not relpath:
            errors.append(f"{path}: registered asset {config_id!r} has no file")
            continue
        try:
            resolve_contract_source(root, asset_root, entry, contract)
        except InteractiveValidationError as exc:
            errors.append(f"{path}: {exc}")
    return errors


def validate_mission_invariants(
    mission: dict[str, Any],
    path: Path,
    contracts: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    referenced: list[tuple[str, str]] = [("player", mission["player"]["contract_id"])]
    referenced.extend(
        (f"environment obstacle {item['instance_id']}", item["contract_id"])
        for item in mission["environment"]["obstacles"]
    )
    referenced.extend(
        (f"entity {item['instance_id']}", item["contract_id"])
        for item in mission["entities"]
    )
    for label, contract_id in referenced:
        if contract_id not in contracts:
            errors.append(f"{path}: {label} references unknown contract {contract_id!r}")

    player_contract = contracts.get(mission["player"]["contract_id"])
    if player_contract and "pilotable" not in player_contract.get("capabilities", []):
        errors.append(f"{path}: player contract must have pilotable capability")

    instance_ids = [mission["player"]["instance_id"]]
    instance_ids.extend(item["instance_id"] for item in mission["environment"]["obstacles"])
    instance_ids.extend(item["instance_id"] for item in mission["entities"])
    if len(instance_ids) != len(set(instance_ids)):
        errors.append(f"{path}: player, obstacle, and entity instance_id values must be unique")

    entity_ids = {item["instance_id"] for item in mission["entities"]}
    sensor_target = mission["sensors"]["target_instance_id"]
    download_target = mission["interactions"]["download"]["target_instance_id"]
    tow_target = mission["interactions"]["tow"]["target_instance_id"]
    for label, target_id in (
        ("sensors", sensor_target),
        ("download", download_target),
        ("tow", tow_target),
    ):
        if target_id not in entity_ids:
            errors.append(f"{path}: {label} target {target_id!r} is not a mission entity")
    if len({sensor_target, download_target, tow_target}) != 1:
        errors.append(f"{path}: sensor, download, and tow targets must be the same entity")

    target_entity = next(
        (item for item in mission["entities"] if item["instance_id"] == sensor_target),
        None,
    )
    if target_entity:
        target_contract = contracts.get(target_entity["contract_id"])
        needed = {"sensor_target", "data_download", "tow_target"}
        if target_contract:
            missing = needed - set(target_contract.get("capabilities", []))
            if missing:
                errors.append(
                    f"{path}: target contract {target_entity['contract_id']!r} "
                    f"is missing capabilities {sorted(missing)}"
                )

    sensor = mission["sensors"]
    ranges = [
        sensor["detection_range_m"],
        sensor["bearing_range_m"],
        sensor["strength_range_m"],
        sensor["identification_range_m"],
        sensor["visual_range_m"],
        mission["interactions"]["download"]["range_m"],
    ]
    if any(left <= right for left, right in zip(ranges, ranges[1:])):
        errors.append(
            f"{path}: sensor ranges must strictly descend from detection through download"
        )

    step_states = [item["state"] for item in mission["steps"]]
    step_ids = [item["step_id"] for item in mission["steps"]]
    if len(step_states) != len(set(step_states)):
        errors.append(f"{path}: mission step state values must be unique")
    if len(step_ids) != len(set(step_ids)):
        errors.append(f"{path}: mission step_id values must be unique")
    seen: set[str] = set()
    for step in mission["steps"]:
        for required in step.get("requires", []):
            if required not in seen:
                errors.append(
                    f"{path}: step {step['step_id']!r} requires {required!r} "
                    f"before that state has occurred"
                )
        seen.add(step["state"])
    if step_states[0] != "BRIEFING" or step_states[-1] != "COMPLETE":
        errors.append(f"{path}: mission must begin with BRIEFING and end with COMPLETE")

    boundary = mission["environment"]["entry_boundary"]["boundary_id"]
    if mission["completion"]["return_boundary_id"] != boundary:
        errors.append(f"{path}: completion must return to the declared entry boundary")
    return errors


def load_missions(
    root: Path,
    contracts: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Path], list[str]]:
    schema = load_json(root / "schemas" / "interactive-mission.schema.json")
    missions: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    errors: list[str] = []
    source_dir = root / "data" / "interactive" / "missions"
    for path in sorted(source_dir.glob("*.interactive.json")):
        document = load_json(path)
        schema_errors = validate_schema(document, schema, path)
        errors.extend(schema_errors)
        if not schema_errors:
            errors.extend(validate_mission_invariants(document, path, contracts))
        mission_id = document.get("mission_id")
        if isinstance(mission_id, str):
            if mission_id in missions:
                errors.append(f"{path}: duplicate mission_id {mission_id!r}")
            else:
                missions[mission_id] = document
                paths[mission_id] = path
    if not missions:
        errors.append(f"no interactive missions found in {source_dir}")
    return missions, paths, errors


def validate_project(
    root: Path = PROJECT_ROOT,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    contracts, contract_paths, errors = load_contracts(root)
    errors.extend(validate_registered_sources(root, contracts, contract_paths))
    missions, _mission_paths, mission_errors = load_missions(root, contracts)
    errors.extend(mission_errors)
    if errors:
        raise InteractiveValidationError("\n".join(errors))
    return contracts, missions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        contracts, missions = validate_project(args.project_root.resolve())
    except InteractiveValidationError as exc:
        for line in str(exc).splitlines():
            print(f"INTERACTIVE-VALIDATION-ERROR: {line}", file=sys.stderr)
        return 2
    print(
        f"INTERACTIVE-VALIDATION-OK assets={len(contracts)} missions={len(missions)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
