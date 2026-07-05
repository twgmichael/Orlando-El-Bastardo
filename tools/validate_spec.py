#!/usr/bin/env python3
"""
validate_spec.py — OEB SceneSpec validator.

Checks a SceneSpec JSON against its schema, the approved-asset config, the
camera grammar, and the actual contents of the referenced GLB file(s), and
emits a schema-valid ValidationReport JSON.

Exit codes:
  0 — report written, passed=true  (zero errors; warnings allowed)
  1 — report written, passed=false (one or more errors)
  2 — tool cannot run (missing/unparseable input, or missing asset file on disk)
"""

import argparse
import json
import os
import pathlib
import re
import sys

import jsonschema
import pygltflib


EPS = 1e-6
REPORT_SCENE_ID_RE = re.compile(r'^[a-z][a-z0-9_]*$')


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_json(path):
    """Return (data, None) or (None, error_message)."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error in {path}: {exc}"
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"


def _die_exit2(messages):
    for msg in messages:
        print(f"VALIDATE-ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# GLB / library helpers
# ---------------------------------------------------------------------------

def _load_glb(abs_path):
    """Return (node_name_set, anim_name_set)."""
    g = pygltflib.GLTF2().load(abs_path)
    nodes = {n.name for n in g.nodes if n.name}
    anims = {a.name for a in g.animations if a.name}
    return nodes, anims


def _collect_referenced_files(spec, assets):
    """
    Return a set of relative GLB file paths referenced by this spec
    (set, characters, props that have config entries).
    """
    files = set()

    if isinstance(spec.get('set'), dict):
        sid = spec['set'].get('set_id')
        if isinstance(sid, str) and sid in assets:
            files.add(assets[sid]['file'])
        for prop in spec['set'].get('props', []) or []:
            if isinstance(prop, dict):
                aid = prop.get('asset_id')
                if isinstance(aid, str) and aid in assets:
                    files.add(assets[aid]['file'])

    for actor in spec.get('actors', []) or []:
        if isinstance(actor, dict):
            cid = actor.get('character_id')
            if isinstance(cid, str) and cid in assets:
                files.add(assets[cid]['file'])

    return files


def _build_library(referenced_files, asset_root):
    """
    Load each GLB file (sorted for determinism) and return
    (union_node_set, union_anim_set).  Files are guaranteed to exist.
    """
    nodes: set = set()
    anims: set = set()
    for rel in sorted(referenced_files):
        abs_path = os.path.join(asset_root, rel)
        n, a = _load_glb(abs_path)
        nodes |= n
        anims |= a
    return nodes, anims


# ---------------------------------------------------------------------------
# Checks V1-V12
# ---------------------------------------------------------------------------

def _run_checks(spec, config, grammar, scenespec_schema, asset_root):
    """
    Run checks V1-V12 in order.
    Returns (errors_list, warnings_list) — each item is a finding dict.
    """
    errors = []
    warnings = []

    # ── V1: schema_invalid ──────────────────────────────────────────────────
    validator = jsonschema.Draft202012Validator(scenespec_schema)
    v1_raw = sorted(
        validator.iter_errors(spec),
        key=lambda e: tuple(str(p) for p in e.absolute_path),
    )
    for e in v1_raw:
        path = (
            "/" + "/".join(str(p) for p in e.absolute_path)
            if e.absolute_path
            else "/"
        )
        errors.append({"code": "schema_invalid", "message": e.message, "path": path})

    if errors:
        # V1 errors present → skip V2-V12
        return errors, warnings

    # ── Shared ground truth (only reached when V1 is clean) ─────────────────
    assets = config.get('assets', {})
    grammar_cams = {c['camera_id']: c for c in grammar.get('cameras', [])}

    ref_files = _collect_referenced_files(spec, assets)
    lib_nodes, lib_anims = _build_library(ref_files, asset_root)

    # Build display string for GLB paths (used in V7 messages)
    glb_paths_str = ', '.join(
        os.path.join(asset_root, rel) for rel in sorted(ref_files)
    )

    # ── V2: unknown_actor ───────────────────────────────────────────────────
    valid_actor_ids = {
        a['actor_id']
        for a in spec.get('actors', [])
        if isinstance(a, dict)
    }
    for i, shot in enumerate(spec.get('shots', [])):
        for j, cue in enumerate(shot.get('cues', [])):
            if not isinstance(cue, dict):
                continue
            aid = cue.get('actor_id')
            if aid is not None and aid not in valid_actor_ids:
                errors.append({
                    "code": "unknown_actor",
                    "message": (
                        f"actor_id '{aid}' not found in actors list"
                    ),
                    "path": f"/shots/{i}/cues/{j}",
                })

    # ── V3: duplicate_id ────────────────────────────────────────────────────

    # actor_ids
    seen: dict = {}
    for i, actor in enumerate(spec.get('actors', [])):
        aid = actor.get('actor_id')
        if aid is not None:
            if aid in seen:
                errors.append({
                    "code": "duplicate_id",
                    "message": f"actor_id '{aid}' duplicates /actors/{seen[aid]}",
                    "path": f"/actors/{i}",
                })
            else:
                seen[aid] = i

    # shot_ids
    seen = {}
    for i, shot in enumerate(spec.get('shots', [])):
        sid = shot.get('shot_id')
        if sid is not None:
            if sid in seen:
                errors.append({
                    "code": "duplicate_id",
                    "message": f"shot_id '{sid}' duplicates /shots/{seen[sid]}",
                    "path": f"/shots/{i}",
                })
            else:
                seen[sid] = i

    # shot orders
    seen = {}
    for i, shot in enumerate(spec.get('shots', [])):
        order = shot.get('order')
        if order is not None:
            if order in seen:
                errors.append({
                    "code": "duplicate_id",
                    "message": f"shot order {order} duplicates /shots/{seen[order]}",
                    "path": f"/shots/{i}",
                })
            else:
                seen[order] = i

    # prop_ids
    seen = {}
    for k, prop in enumerate(spec.get('set', {}).get('props', [])):
        pid = prop.get('prop_id')
        if pid is not None:
            if pid in seen:
                errors.append({
                    "code": "duplicate_id",
                    "message": f"prop_id '{pid}' duplicates /set/props/{seen[pid]}",
                    "path": f"/set/props/{k}",
                })
            else:
                seen[pid] = k

    # cue_ids (globally across all shots; AudioCue may omit cue_id)
    seen = {}
    for i, shot in enumerate(spec.get('shots', [])):
        for j, cue in enumerate(shot.get('cues', [])):
            cid = cue.get('cue_id')
            if cid is not None:
                if cid in seen:
                    errors.append({
                        "code": "duplicate_id",
                        "message": f"cue_id '{cid}' duplicates {seen[cid]}",
                        "path": f"/shots/{i}/cues/{j}",
                    })
                else:
                    seen[cid] = f"/shots/{i}/cues/{j}"

    # ── V4: asset existence ─────────────────────────────────────────────────

    # set_id → unknown_asset (error)
    set_id = spec.get('set', {}).get('set_id')
    if isinstance(set_id, str) and set_id not in assets:
        errors.append({
            "code": "unknown_asset",
            "message": f"set_id '{set_id}' not found in oeb.config.json assets",
            "path": "/set",
        })

    # character_id → unknown_asset (error)
    for i, actor in enumerate(spec.get('actors', [])):
        cid = actor.get('character_id')
        if isinstance(cid, str) and cid not in assets:
            errors.append({
                "code": "unknown_asset",
                "message": (
                    f"character_id '{cid}' for actor '{actor.get('actor_id')}' "
                    f"not found in oeb.config.json assets"
                ),
                "path": f"/actors/{i}",
            })

    # prop asset_id → missing_prop_asset (WARNING)
    for k, prop in enumerate(spec.get('set', {}).get('props', [])):
        aid = prop.get('asset_id')
        if isinstance(aid, str) and aid not in assets:
            warnings.append({
                "code": "missing_prop_asset",
                "message": f"prop asset_id '{aid}' not found in oeb.config.json assets",
                "path": f"/set/props/{k}",
            })

    # ── V5: cameras ─────────────────────────────────────────────────────────
    for i, shot in enumerate(spec.get('shots', [])):
        cam = shot.get('camera_setup')
        if isinstance(cam, str):
            if cam not in grammar_cams:
                errors.append({
                    "code": "unknown_camera",
                    "message": (
                        f"camera_setup '{cam}' not found in camera grammar "
                        f"(data/camera_grammar.json)"
                    ),
                    "path": f"/shots/{i}",
                })
            else:
                scene_obj = grammar_cams[cam].get('scene_object')
                if isinstance(scene_obj, str) and scene_obj not in lib_nodes:
                    warnings.append({
                        "code": "unsupported_camera_grammar",
                        "message": (
                            f"camera '{cam}' scene_object '{scene_obj}' "
                            f"not found in GLB library nodes"
                        ),
                        "path": f"/shots/{i}",
                    })

    # ── V6: unknown_mark ────────────────────────────────────────────────────

    # set.marks
    for m, mark in enumerate(spec.get('set', {}).get('marks', [])):
        if isinstance(mark, str) and mark not in lib_nodes:
            errors.append({
                "code": "unknown_mark",
                "message": f"set mark '{mark}' not found in GLB library nodes",
                "path": f"/set/marks/{m}",
            })

    # actor spawn_mark
    for i, actor in enumerate(spec.get('actors', [])):
        spawn = actor.get('spawn_mark')
        if isinstance(spawn, str) and spawn not in lib_nodes:
            errors.append({
                "code": "unknown_mark",
                "message": (
                    f"actor '{actor.get('actor_id')}' spawn_mark '{spawn}' "
                    f"not found in GLB library nodes"
                ),
                "path": f"/actors/{i}",
            })

    # prop at_mark
    for k, prop in enumerate(spec.get('set', {}).get('props', [])):
        at = prop.get('at_mark')
        if isinstance(at, str) and at not in lib_nodes:
            errors.append({
                "code": "unknown_mark",
                "message": (
                    f"prop '{prop.get('prop_id')}' at_mark '{at}' "
                    f"not found in GLB library nodes"
                ),
                "path": f"/set/props/{k}",
            })

    # ── V7: unknown_clip (ERROR) ────────────────────────────────────────────
    for i, shot in enumerate(spec.get('shots', [])):
        for j, cue in enumerate(shot.get('cues', [])):
            if cue.get('type') == 'animation':
                clip_id = cue.get('clip_id')
                if isinstance(clip_id, str) and clip_id not in lib_anims:
                    errors.append({
                        "code": "unknown_clip",
                        "message": (
                            f"clip '{clip_id}' not found among GLB animations "
                            f"({glb_paths_str})"
                        ),
                        "path": f"/shots/{i}/cues/{j}",
                    })

    # ── V8: unknown_audio ───────────────────────────────────────────────────
    for i, shot in enumerate(spec.get('shots', [])):
        for j, cue in enumerate(shot.get('cues', [])):
            if cue.get('type') == 'audio':
                aid = cue.get('asset_id')
                if isinstance(aid, str):
                    if aid not in assets or assets[aid].get('kind') != 'audio':
                        errors.append({
                            "code": "unknown_audio",
                            "message": (
                                f"audio asset_id '{aid}' not found in "
                                f"oeb.config.json with kind='audio'"
                            ),
                            "path": f"/shots/{i}/cues/{j}",
                        })

    # ── V9: cue_out_of_bounds ───────────────────────────────────────────────
    for i, shot in enumerate(spec.get('shots', [])):
        shot_len = shot.get('end_time', 0.0) - shot.get('start_time', 0.0)
        for j, cue in enumerate(shot.get('cues', [])):
            start = cue.get('start_time', 0.0)
            dur = cue.get('duration', 0.0)
            if start < -EPS or start + dur > shot_len + EPS:
                errors.append({
                    "code": "cue_out_of_bounds",
                    "message": (
                        f"cue start_time={start} duration={dur} is out of "
                        f"bounds for shot length {shot_len}"
                    ),
                    "path": f"/shots/{i}/cues/{j}",
                })

    # ── V10: shot_overlap ───────────────────────────────────────────────────
    shots_by_order = sorted(
        enumerate(spec.get('shots', [])),
        key=lambda x: x[1].get('order', 0),
    )
    prev_end = None
    for orig_i, shot in shots_by_order:
        st = shot.get('start_time', 0.0)
        et = shot.get('end_time', 0.0)
        shot_id = shot.get('shot_id', f'shot_{orig_i}')

        if et <= st + EPS:
            errors.append({
                "code": "shot_overlap",
                "message": f"shot '{shot_id}' end_time {et} <= start_time {st}",
                "path": f"/shots/{orig_i}",
            })

        if prev_end is not None and st < prev_end - EPS:
            errors.append({
                "code": "shot_overlap",
                "message": (
                    f"shot '{shot_id}' start_time {st} overlaps "
                    f"previous shot end_time {prev_end}"
                ),
                "path": f"/shots/{orig_i}",
            })

        prev_end = et

    # ── V11: binding_unresolved ─────────────────────────────────────────────
    for i, actor in enumerate(spec.get('actors', [])):
        bindings = actor.get('target_bindings')
        if not isinstance(bindings, dict):
            continue
        aid_label = actor.get('actor_id', f'actor_{i}')

        bo = bindings.get('blender_object')
        if bo is not None and bo not in lib_nodes:
            errors.append({
                "code": "binding_unresolved",
                "message": (
                    f"actor '{aid_label}' blender_object '{bo}' "
                    f"not found in GLB library nodes"
                ),
                "path": f"/actors/{i}",
            })

        usd = bindings.get('usd_path')
        if usd is not None and not usd.startswith('/'):
            errors.append({
                "code": "binding_unresolved",
                "message": (
                    f"actor '{aid_label}' usd_path '{usd}' "
                    f"does not start with '/'"
                ),
                "path": f"/actors/{i}",
            })

        godot = bindings.get('godot_node')
        if godot is not None and (not godot or godot.startswith('/')):
            errors.append({
                "code": "binding_unresolved",
                "message": (
                    f"actor '{aid_label}' godot_node '{godot}' "
                    f"is empty or starts with '/'"
                ),
                "path": f"/actors/{i}",
            })

    # ── V12: dialogue_too_long_for_shot (WARNING) ───────────────────────────
    for i, shot in enumerate(spec.get('shots', [])):
        shot_len = shot.get('end_time', 0.0) - shot.get('start_time', 0.0)
        for j, cue in enumerate(shot.get('cues', [])):
            if cue.get('type') == 'dialogue':
                start = cue.get('start_time', 0.0)
                dur = cue.get('duration', 0.0)
                if start + dur > shot_len - 0.5:
                    warnings.append({
                        "code": "dialogue_too_long_for_shot",
                        "message": (
                            f"dialogue cue ends at {start + dur:.3f}s, "
                            f"inside final 0.5s of shot "
                            f"(shot length {shot_len:.3f}s)"
                        ),
                        "path": f"/shots/{i}/cues/{j}",
                    })

    return errors, warnings


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate a SceneSpec JSON against schema, config, grammar, and GLB."
    )
    parser.add_argument('--spec', required=True,
                        help="Path to the SceneSpec JSON to validate")
    parser.add_argument('--config', default='oeb.config.json',
                        help="Path to oeb.config.json (default: oeb.config.json)")
    parser.add_argument('--grammar', default='data/camera_grammar.json',
                        help="Path to camera_grammar.json (default: data/camera_grammar.json)")
    parser.add_argument('--schema-dir', default='schemas',
                        help="Directory containing JSON schemas (default: schemas)")
    parser.add_argument('--out', default=None,
                        help="Output path for the ValidationReport JSON")
    args = parser.parse_args()

    # ── Load all required input files (exit 2 on any failure) ──────────────
    exit2: list = []

    spec, err = _load_json(args.spec)
    if err:
        exit2.append(err)

    config, err = _load_json(args.config)
    if err:
        exit2.append(err)

    grammar, err = _load_json(args.grammar)
    if err:
        exit2.append(err)

    scenespec_schema_path = os.path.join(args.schema_dir, 'scenespec.schema.json')
    scenespec_schema, err = _load_json(scenespec_schema_path)
    if err:
        exit2.append(err)

    report_schema_path = os.path.join(args.schema_dir, 'validationreport.schema.json')
    report_schema, err = _load_json(report_schema_path)
    if err:
        exit2.append(err)

    if exit2:
        _die_exit2(exit2)

    # ── Derive scene_id for the report ─────────────────────────────────────
    raw_sid = spec.get('scene_id') if isinstance(spec, dict) else None
    scene_id = (
        raw_sid
        if isinstance(raw_sid, str) and REPORT_SCENE_ID_RE.match(raw_sid)
        else 'unknown_scene'
    )

    # ── Resolve output path ─────────────────────────────────────────────────
    out_path = args.out or os.path.join('out', f"{scene_id}.validationreport.json")

    # ── Check config-referenced asset files exist (exit 2 if missing) ───────
    asset_root = os.environ.get('OEB_ASSET_ROOT', config.get('asset_root', 'assets'))
    if isinstance(spec, dict):
        assets = config.get('assets', {})
        ref_files = _collect_referenced_files(spec, assets)
        for rel in sorted(ref_files):
            abs_path = os.path.join(asset_root, rel)
            if not os.path.exists(abs_path):
                exit2.append(f"config-referenced asset file missing: {abs_path}")

    if exit2:
        _die_exit2(exit2)

    # ── Run checks V1-V12 ───────────────────────────────────────────────────
    errs, warns = _run_checks(
        spec, config, grammar, scenespec_schema, asset_root
    )

    # ── Build report ────────────────────────────────────────────────────────
    report = {
        "schema_version": "1.0.0",
        "scene_id": scene_id,
        "passed": len(errs) == 0,
        "errors": errs,
        "warnings": warns,
    }

    # ── Validate the report against its own schema (bug guard) ──────────────
    try:
        jsonschema.Draft202012Validator(report_schema).validate(report)
    except jsonschema.ValidationError as exc:
        print(
            f"VALIDATE-ERROR: generated report failed its own schema: {exc.message}",
            file=sys.stderr,
        )
        sys.exit(2)

    # ── Write report ────────────────────────────────────────────────────────
    out_dir = os.path.dirname(out_path)
    if out_dir:
        pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
        f.write('\n')

    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
