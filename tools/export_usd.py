#!/usr/bin/env python3
"""
export_usd.py — OEB USD layer exporter.

Assembles a USD root layer from a validated SceneSpec:
  <scene_id>.usda, <scene_id>_timeline.json, plus a copy of each
  referenced .usdc.

Exit codes:
  0 — success
  2 — input or gate failure (EXPORT-ERROR: <detail> per problem on stderr;
      nothing written to out-dir)
  3 — internal error
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

from pxr import Sdf, Usd, UsdGeom


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


def _export_error(msg):
    print(f"EXPORT-ERROR: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Asset collection
# ---------------------------------------------------------------------------

def _collect_distinct_files(spec, config):
    """Return set of relative GLB file paths referenced by this spec."""
    assets = config.get('assets', {})
    files = set()

    # Set
    set_id = spec.get('set', {}).get('set_id')
    if set_id and set_id in assets:
        files.add(assets[set_id]['file'])

    # Props
    for prop in spec.get('set', {}).get('props', []):
        asset_id = prop.get('asset_id')
        if asset_id and asset_id in assets:
            files.add(assets[asset_id]['file'])

    # Characters
    for actor in spec.get('actors', []):
        char_id = actor.get('character_id')
        if char_id and char_id in assets:
            files.add(assets[char_id]['file'])

    return files


# ---------------------------------------------------------------------------
# U6 — timeline sidecar
# ---------------------------------------------------------------------------

def _make_timeline(spec, grammar):
    """Build the timeline sidecar JSON string (U6)."""
    cameras_by_id = {c['camera_id']: c for c in grammar.get('cameras', [])}
    fps = spec['render']['fps']
    scene_id = spec['scene_id']

    # Shots sorted by order
    shots_out = []
    for shot in sorted(spec['shots'], key=lambda s: s['order']):
        cam_id = shot['camera_setup']
        cam = cameras_by_id[cam_id]
        scene_obj = cam['scene_object']
        shots_out.append({
            'camera_scene_object': scene_obj,
            'camera_setup': cam_id,
            'end_time': shot['end_time'],
            'order': shot['order'],
            'shot_id': shot['shot_id'],
            'start_time': shot['start_time'],
        })

    # Actor map for godot_node lookup
    actor_map = {a['actor_id']: a for a in spec['actors']}

    animation_cues = []
    dialogue_cues = []

    for shot in spec['shots']:
        shot_start = shot['start_time']
        shot_id = shot['shot_id']
        for cue in shot.get('cues', []):
            cue_type = cue.get('type')
            if cue_type == 'animation':
                actor = actor_map.get(cue['actor_id'], {})
                tb = actor.get('target_bindings', {})
                godot_node = tb.get('godot_node', '')
                animation_cues.append({
                    'actor_id': cue['actor_id'],
                    'clip_id': cue['clip_id'],
                    'cue_id': cue.get('cue_id', ''),
                    'godot_node': godot_node,
                    'loop': cue.get('loop', False),
                    'shot_id': shot_id,
                    'time': shot_start + cue['start_time'],
                })
            elif cue_type == 'dialogue':
                dialogue_cues.append({
                    'actor_id': cue['actor_id'],
                    'cue_id': cue.get('cue_id', ''),
                    'duration': cue['duration'],
                    'shot_id': shot_id,
                    'text': cue['text'],
                    'time': shot_start + cue['start_time'],
                })

    # Sort cue arrays by time then cue_id (determinism)
    animation_cues.sort(key=lambda c: (c['time'], c['cue_id']))
    dialogue_cues.sort(key=lambda c: (c['time'], c['cue_id']))

    timeline = {
        'animation_cues': animation_cues,
        'dialogue_cues': dialogue_cues,
        'fps': fps,
        'scene_id': scene_id,
        'shots': shots_out,
    }

    return json.dumps(timeline, indent=2, sort_keys=True) + '\n'


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export a SceneSpec to a USD layer."
    )
    parser.add_argument('--spec', required=True,
                        help="Path to the SceneSpec JSON to export")
    parser.add_argument('--config', default='oeb.config.json',
                        help="Path to oeb.config.json (default: oeb.config.json)")
    parser.add_argument('--grammar', default='data/camera_grammar.json',
                        help="Path to camera_grammar.json (default: data/camera_grammar.json)")
    parser.add_argument('--out-dir', default=None,
                        help="Output directory (default: out/usd/<scene_id>)")
    args = parser.parse_args()

    # ── Load input files ────────────────────────────────────────────────────
    spec, err = _load_json(args.spec)
    if err:
        _export_error(err)
        sys.exit(2)

    config, err = _load_json(args.config)
    if err:
        _export_error(err)
        sys.exit(2)

    grammar, err = _load_json(args.grammar)
    if err:
        _export_error(err)
        sys.exit(2)

    scene_id = (
        spec.get('scene_id', 'unknown_scene')
        if isinstance(spec, dict)
        else 'unknown_scene'
    )

    # Determine out-dir
    if args.out_dir:
        out_dir = pathlib.Path(args.out_dir)
    else:
        out_dir = pathlib.Path('out') / 'usd' / scene_id

    # ── U1: Validation gate ─────────────────────────────────────────────────
    # Report path: <out-dir-parent>/<scene_id>.validationreport.json
    report_out = out_dir.parent / f"{scene_id}.validationreport.json"
    gate_result = subprocess.run(
        [
            sys.executable, 'tools/validate_spec.py',
            '--spec', args.spec,
            '--config', args.config,
            '--grammar', args.grammar,
            '--out', str(report_out),
        ],
        capture_output=True,
        text=True,
    )
    if gate_result.returncode != 0:
        _export_error(f"validation gate failed (exit {gate_result.returncode})")
        sys.exit(2)

    # ── U2: v0 cue scope ────────────────────────────────────────────────────
    supported_types = {'animation', 'dialogue'}
    for shot in spec.get('shots', []):
        for cue in shot.get('cues', []):
            cue_type = cue.get('type')
            if cue_type not in supported_types:
                cue_id = cue.get('cue_id', '<no-id>')
                _export_error(
                    f"unsupported cue type '{cue_type}' in v0 "
                    f"({shot['shot_id']}/{cue_id})"
                )
                sys.exit(2)

    # ── U3: Asset derivation ─────────────────────────────────────────────────
    asset_root = os.environ.get(
        'OEB_ASSET_ROOT', config.get('asset_root', 'assets')
    )
    assets = config.get('assets', {})
    distinct_files = _collect_distinct_files(spec, config)

    # Map: rel_glb → abs_usdc_path
    usdc_map = {}
    for rel in sorted(distinct_files):
        rel_path = pathlib.Path(rel)
        usdc_rel = rel_path.with_suffix('.usdc')
        abs_usdc = pathlib.Path(asset_root) / usdc_rel
        if not abs_usdc.exists():
            _export_error(f"no USD sibling for {rel}")
            sys.exit(2)
        usdc_map[rel] = abs_usdc

    # Identify the set's usdc basename for the Set prim reference
    set_id = spec.get('set', {}).get('set_id')
    set_file = assets[set_id]['file'] if (set_id and set_id in assets) else None
    set_usdc_basename = (
        usdc_map[set_file].name
        if (set_file and set_file in usdc_map)
        else None
    )

    # ── Create output directory (ONLY after all checks pass) ──────────────
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── U3: Copy usdc files into out-dir ──────────────────────────────────
    for rel, abs_usdc in usdc_map.items():
        dst = out_dir / abs_usdc.name
        shutil.copy2(str(abs_usdc), str(dst))

    # ── U4: Create USD stage ──────────────────────────────────────────────
    fps = spec['render']['fps']
    shots = spec['shots']
    last_end_time = max(s['end_time'] for s in shots)
    end_time_code = round(last_end_time * fps)

    usda_path = out_dir / f"{scene_id}.usda"
    stage = Usd.Stage.CreateNew(str(usda_path))

    stage.SetTimeCodesPerSecond(fps)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(end_time_code)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    # ── U5: Prims ──────────────────────────────────────────────────────────

    # /World — Xform (defaultPrim)
    world = UsdGeom.Xform.Define(stage, '/World')
    stage.SetDefaultPrim(world.GetPrim())

    # /World/Set — Xform with reference to ./<usdc_basename>
    set_prim = UsdGeom.Xform.Define(stage, '/World/Set')
    if set_usdc_basename:
        set_prim.GetPrim().GetReferences().AddReference(
            f'./{set_usdc_basename}'
        )

    # /World/Cameras — Xform container
    UsdGeom.Xform.Define(stage, '/World/Cameras')

    # /World/Cameras/<camera_id> — one Camera prim per distinct camera_setup,
    # in first-use order across shots sorted by order
    cameras_by_id = {c['camera_id']: c for c in grammar.get('cameras', [])}
    seen_cams = {}
    cam_order = []
    for shot in sorted(shots, key=lambda s: s['order']):
        cs = shot['camera_setup']
        if cs not in seen_cams:
            seen_cams[cs] = len(cam_order)
            cam_order.append(cs)

    for cam_id in cam_order:
        cam_entry = cameras_by_id[cam_id]
        cam_prim = UsdGeom.Camera.Define(stage, f'/World/Cameras/{cam_id}')
        cam_prim.GetFocalLengthAttr().Set(float(cam_entry['lens_mm']))
        cam_prim.GetPrim().CreateAttribute(
            'oeb:sceneObject', Sdf.ValueTypeNames.String
        ).Set(cam_entry['scene_object'])

    # Actor prims at their target_bindings.usd_path — Xform, possibly
    # root-level outside /World (expected per U5)
    for actor in spec.get('actors', []):
        tb = actor.get('target_bindings', {})
        usd_path = tb.get('usd_path')
        if usd_path:
            actor_prim = UsdGeom.Xform.Define(stage, usd_path)
            actor_prim.GetPrim().CreateAttribute(
                'oeb:characterId', Sdf.ValueTypeNames.String
            ).Set(actor['character_id'])
            actor_prim.GetPrim().CreateAttribute(
                'oeb:spawnMark', Sdf.ValueTypeNames.String
            ).Set(actor['spawn_mark'])

    stage.Save()

    # ── U6: Timeline sidecar ──────────────────────────────────────────────
    timeline_path = out_dir / f"{scene_id}_timeline.json"
    timeline_path.write_text(_make_timeline(spec, grammar), encoding='utf-8')

    sys.exit(0)


if __name__ == '__main__':
    main()
