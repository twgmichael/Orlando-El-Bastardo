#!/usr/bin/env python3
"""
export_godot.py — OEB Godot 4 project exporter.

Builds a self-contained Godot 4 project from a validated SceneSpec:
  project.godot, <scene_id>.tscn, SceneDirector.gd, timeline.json,
  plus byte-for-byte copies of referenced GLB file(s).

Exit codes:
  0 — success
  2 — input or gate failure (EXPORT-ERROR: <detail> per problem on stderr; nothing written)
  3 — internal error
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys


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
# G4 — project.godot
# ---------------------------------------------------------------------------

def _make_project_godot(scene_id):
    return (
        f'config_version=5\n'
        f'\n'
        f'[application]\n'
        f'config/name="{scene_id}"\n'
        f'run/main_scene="res://{scene_id}.tscn"\n'
    )


# ---------------------------------------------------------------------------
# G5 — <scene_id>.tscn
# ---------------------------------------------------------------------------

def _make_tscn(spec, config, grammar):
    scene_id = spec['scene_id']
    assets = config.get('assets', {})
    cameras_by_id = {c['camera_id']: c for c in grammar.get('cameras', [])}

    # Set GLB basename (used for ext_resource path)
    set_id = spec['set']['set_id']
    set_file = assets[set_id]['file']
    glb_basename = os.path.basename(set_file)

    lines = []

    # Header
    lines.append('[gd_scene load_steps=3 format=3]')
    lines.append('')

    # External resources — fixed literal ids for determinism (G8)
    lines.append(
        f'[ext_resource type="PackedScene" path="res://{glb_basename}" id="1_set"]'
    )
    lines.append(
        '[ext_resource type="Script" path="res://SceneDirector.gd" id="2_dir"]'
    )
    lines.append('')

    # Root node
    lines.append(f'[node name="{scene_id}" type="Node3D"]')
    lines.append('')

    # Set instance
    lines.append('[node name="Set" parent="." instance=ExtResource("1_set")]')
    lines.append('')

    # Actors container
    lines.append('[node name="Actors" type="Node3D" parent="."]')
    lines.append('')

    # One Node3D per actor (spec order)
    for actor in spec['actors']:
        tb = actor.get('target_bindings', {})
        godot_node = tb.get('godot_node', '')
        parts = godot_node.split('/')
        name = parts[-1]
        parent = '/'.join(parts[:-1]) if len(parts) > 1 else '.'
        character_id = actor['character_id']
        spawn_mark = actor['spawn_mark']
        blender_object = tb.get('blender_object', '')

        lines.append(f'[node name="{name}" type="Node3D" parent="{parent}"]')
        lines.append(f'metadata/character_id = "{character_id}"')
        lines.append(f'metadata/spawn_mark = "{spawn_mark}"')
        lines.append(f'metadata/blender_object = "{blender_object}"')
        lines.append('')

    # Cameras container
    lines.append('[node name="Cameras" type="Node3D" parent="."]')
    lines.append('')

    # One Node3D per distinct camera_setup, in first-use order across shots
    seen_cams = {}
    cam_order = []
    for shot in sorted(spec['shots'], key=lambda s: s['order']):
        cs = shot['camera_setup']
        if cs not in seen_cams:
            seen_cams[cs] = len(cam_order)
            cam_order.append(cs)

    for cam_id in cam_order:
        cam = cameras_by_id[cam_id]
        scene_obj = cam['scene_object']
        lines.append(f'[node name="{scene_obj}" type="Node3D" parent="Cameras"]')
        lines.append(f'metadata/camera_id = "{cam_id}"')
        lines.append('')

    # SceneDirector — script property in body (keeps header clean for needle check)
    lines.append('[node name="SceneDirector" type="Node" parent="."]')
    lines.append('script = ExtResource("2_dir")')
    lines.append('')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# G6 — SceneDirector.gd  (exact content per profile)
# ---------------------------------------------------------------------------

SCENE_DIRECTOR_GD = (
    'extends Node\n'
    '\n'
    'const TIMELINE_PATH := "res://timeline.json"\n'
    '\n'
    'var timeline: Dictionary = {}\n'
    '\n'
    '\n'
    'func _ready() -> void:\n'
    '    var f := FileAccess.open(TIMELINE_PATH, FileAccess.READ)\n'
    '    if f:\n'
    '        timeline = JSON.parse_string(f.get_as_text())\n'
)


# ---------------------------------------------------------------------------
# G7 — timeline.json
# ---------------------------------------------------------------------------

def _make_timeline(spec, grammar):
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

    # Sort cue arrays by time then cue_id (G7, G8)
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
# Asset collection
# ---------------------------------------------------------------------------

def _collect_distinct_files(spec, config):
    """Return set of relative file paths (set, characters, props) referenced."""
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
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export a SceneSpec to a self-contained Godot 4 project."
    )
    parser.add_argument('--spec', required=True,
                        help="Path to the SceneSpec JSON to export")
    parser.add_argument('--config', default='oeb.config.json',
                        help="Path to oeb.config.json (default: oeb.config.json)")
    parser.add_argument('--grammar', default='data/camera_grammar.json',
                        help="Path to camera_grammar.json (default: data/camera_grammar.json)")
    parser.add_argument('--out-dir', default=None,
                        help="Output directory (default: out/godot/<scene_id>)")
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

    scene_id = spec.get('scene_id', 'unknown_scene') if isinstance(spec, dict) else 'unknown_scene'

    # Determine out-dir
    if args.out_dir:
        out_dir = pathlib.Path(args.out_dir)
    else:
        out_dir = pathlib.Path('out') / 'godot' / scene_id

    # ── G1: Validation gate ─────────────────────────────────────────────────
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

    # ── G2: v0 cue scope ────────────────────────────────────────────────────
    supported_types = {'animation', 'dialogue'}
    for shot in spec.get('shots', []):
        for cue in shot.get('cues', []):
            cue_type = cue.get('type')
            if cue_type not in supported_types:
                cue_id = cue.get('cue_id', '<no-id>')
                _export_error(
                    f"unsupported cue type '{cue_type}' in v0 ({shot['shot_id']}/{cue_id})"
                )
                sys.exit(2)

    # ── Verify referenced asset files exist ─────────────────────────────────
    asset_root = os.environ.get('OEB_ASSET_ROOT', config.get('asset_root', 'assets'))
    distinct_files = _collect_distinct_files(spec, config)
    for rel in sorted(distinct_files):
        abs_path = os.path.join(asset_root, rel)
        if not os.path.exists(abs_path):
            _export_error(f"referenced asset file missing: {abs_path}")
            sys.exit(2)

    # ── Create output directory (ONLY after gate passes) ───────────────────
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── G4: project.godot ───────────────────────────────────────────────────
    (out_dir / 'project.godot').write_text(
        _make_project_godot(scene_id), encoding='utf-8'
    )

    # ── G5: <scene_id>.tscn ─────────────────────────────────────────────────
    (out_dir / f'{scene_id}.tscn').write_text(
        _make_tscn(spec, config, grammar), encoding='utf-8'
    )

    # ── G6: SceneDirector.gd ────────────────────────────────────────────────
    (out_dir / 'SceneDirector.gd').write_text(SCENE_DIRECTOR_GD, encoding='utf-8')

    # ── G7: timeline.json ───────────────────────────────────────────────────
    (out_dir / 'timeline.json').write_text(
        _make_timeline(spec, grammar), encoding='utf-8'
    )

    # ── G3: Copy distinct GLB files (byte-for-byte under basename) ───────────
    for rel in sorted(distinct_files):
        src = os.path.join(asset_root, rel)
        dst = out_dir / os.path.basename(rel)
        shutil.copy2(src, str(dst))

    sys.exit(0)


if __name__ == '__main__':
    main()
