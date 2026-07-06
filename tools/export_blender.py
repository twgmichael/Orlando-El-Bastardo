#!/usr/bin/env python3
"""
export_blender.py — OEB SceneSpec → .blend exporter (v0).

Runs inside headless Blender (bpy). Script arguments follow the '--' separator
on the Blender command line.

CLI contract
  Export:     --spec <path>
              [--config oeb.config.json]
              [--grammar data/camera_grammar.json]
              [--out out/blender/<scene_id>.blend]

  Introspect: --introspect <path.blend>
              --manifest <path.json>

Exit codes: 0 success; 2 input/gate failure; 3 internal/self-check failure.
Uses os._exit() to guarantee the Blender process exit code is propagated.
"""

import json
import math
import os
import re
import subprocess
import sys

# ─── Project root (script lives at <root>/tools/export_blender.py) ────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
VENV_PYTHON = os.path.join(PROJECT_ROOT, '.venv', 'bin', 'python')

# ─── Argument parsing ─────────────────────────────────────────────────────────

def _parse_args():
    """Parse script arguments that follow the '--' separator in sys.argv."""
    try:
        sep = sys.argv.index('--')
        raw = sys.argv[sep + 1:]
    except ValueError:
        raw = []

    import argparse
    p = argparse.ArgumentParser(prog='export_blender.py')
    p.add_argument('--spec', default=None,
                   help='Path to a validated SceneSpec JSON (export mode)')
    p.add_argument('--config', default='oeb.config.json',
                   help='Path to oeb.config.json (default: oeb.config.json)')
    p.add_argument('--grammar', default='data/camera_grammar.json',
                   help='Path to camera_grammar.json')
    p.add_argument('--out', default=None,
                   help='Output .blend path (default: out/blender/<scene_id>.blend)')
    p.add_argument('--introspect', default=None,
                   help='Path to an existing .blend (introspect mode)')
    p.add_argument('--manifest', default=None,
                   help='Output path for the introspection manifest JSON')
    return p.parse_args(raw)

# ─── Utilities ────────────────────────────────────────────────────────────────

def to_frame(t_seconds, fps):
    """R3: convert absolute seconds to Blender 1-based frame number."""
    return round(t_seconds * fps) + 1


def _load_json(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def _die(msg, code=2):
    """Print EXPORT-ERROR, flush both streams, and hard-exit with *code*."""
    print(f"EXPORT-ERROR: {msg}", file=sys.stderr)
    sys.stderr.flush()
    sys.stdout.flush()
    os._exit(code)


def _resolve_path(arg_path, base=PROJECT_ROOT):
    """Return an absolute path; relative paths are anchored to *base*."""
    if os.path.isabs(arg_path):
        return arg_path
    return os.path.join(base, arg_path)

# ─── R7: clip lookup ──────────────────────────────────────────────────────────

def _find_action(clip_id):
    """
    R7: resolve *clip_id* to exactly one bpy.data.actions entry.
    Candidate = exact name match OR name with trailing .NNN suffix stripped.
    Exactly one candidate → return it; otherwise → die(2).
    """
    import bpy  # noqa – available inside Blender

    candidates = []
    seen_ptr = set()
    for action in bpy.data.actions:
        nm = action.name
        match = (nm == clip_id) or (re.sub(r'\.\d+$', '', nm) == clip_id)
        if match and id(action) not in seen_ptr:
            candidates.append(action)
            seen_ptr.add(id(action))

    if len(candidates) == 1:
        return candidates[0]
    _die(f"clip '{clip_id}' resolved to {len(candidates)} actions", 2)

# ─── R1: validation gate ──────────────────────────────────────────────────────

def _run_gate(spec_path, out_dir, scene_id):
    """
    R1: run validate_spec.py via the project venv as a subprocess.
    Non-zero exit → print EXPORT-ERROR and die(2).
    Never re-implements or weakens the validator.
    """
    report_path = os.path.join(out_dir, f"{scene_id}.validationreport.json")
    validate_script = os.path.join(PROJECT_ROOT, 'tools', 'validate_spec.py')
    result = subprocess.run(
        [VENV_PYTHON, validate_script,
         '--spec', spec_path,
         '--out', report_path],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        _die(f"validation gate failed (exit {result.returncode})", 2)

# ─── Export mode ──────────────────────────────────────────────────────────────

def _export(args):
    """Build a .blend from a validated SceneSpec (rules R1–R10)."""
    import bpy  # noqa

    spec_path = os.path.abspath(args.spec)
    if not os.path.isfile(spec_path):
        _die(f"spec not found: {spec_path}", 2)

    spec = _load_json(spec_path)
    scene_id = spec['scene_id']
    shots = spec['shots']
    fps = spec['render']['fps']
    render_cfg = spec['render']

    # Resolve output .blend path
    if args.out:
        blend_path = os.path.abspath(args.out)
    else:
        blend_path = os.path.join(
            PROJECT_ROOT, 'out', 'blender', f"{scene_id}.blend"
        )
    out_dir = os.path.dirname(blend_path)

    # ── R1: validation gate (before touching bpy data) ───────────────────────
    _run_gate(spec_path, out_dir, scene_id)

    # Load config + grammar (relative paths anchored to PROJECT_ROOT)
    config = _load_json(_resolve_path(args.config))
    grammar = _load_json(_resolve_path(args.grammar))

    asset_root = os.environ.get(
        'OEB_ASSET_ROOT', config.get('asset_root', 'assets')
    )
    asset_root = _resolve_path(asset_root)

    assets = config['assets']
    grammar_cams = {c['camera_id']: c for c in grammar['cameras']}

    # ── R2: v0 cue scope (reject unsupported types before build) ─────────────
    for shot in shots:
        for cue in shot.get('cues', []):
            ctype = cue.get('type', '')
            if ctype not in ('animation', 'dialogue'):
                cue_id = cue.get('cue_id', '<no-id>')
                _die(
                    f"unsupported cue type '{ctype}' in v0 "
                    f"({shot['shot_id']}/{cue_id})",
                    2,
                )

    # ── R4: delete every object from the factory scene ───────────────────────
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Collect distinct GLB files referenced by this spec
    file_set = set()
    set_id = spec['set']['set_id']
    if set_id in assets:
        file_set.add(assets[set_id]['file'])
    for actor in spec['actors']:
        cid = actor.get('character_id', '')
        if cid in assets:
            file_set.add(assets[cid]['file'])
    for prop in spec['set'].get('props', []):
        aid = prop.get('asset_id', '')
        if aid in assets:
            file_set.add(assets[aid]['file'])

    # Import each distinct GLB exactly once (sorted for determinism)
    for rel_file in sorted(file_set):
        glb_path = os.path.join(asset_root, rel_file)
        bpy.ops.import_scene.gltf(filepath=glb_path)

    # ── R4: clear animation data from objects; keep bpy.data.actions ─────────
    # Give all imported actions a fake user so they survive the clear.
    for action in bpy.data.actions:
        action.use_fake_user = True
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data_clear()

    # ── R5: scene settings ───────────────────────────────────────────────────
    scene = bpy.context.scene
    scene.name = scene_id
    scene.render.fps = fps
    scene.render.resolution_x = render_cfg['resolution']['width']
    scene.render.resolution_y = render_cfg['resolution']['height']
    scene.frame_start = 1

    # ── R3: frame_end = frame(last shot end_time) - 1 ────────────────────────
    last_shot = max(shots, key=lambda s: s['order'])
    scene.frame_end = to_frame(last_shot['end_time'], fps) - 1

    # Actor lookup: actor_id → {blender_object, spawn_mark}
    actor_map = {
        a['actor_id']: {
            'blender_object': a.get('target_bindings', {}).get('blender_object'),
            'spawn_mark': a.get('spawn_mark'),
        }
        for a in spec['actors']
    }

    # Track all objects that receive a placement (for R11 manifest)
    placement_obj_names = []

    # ── R6: actor placements ─────────────────────────────────────────────────
    for actor in spec['actors']:
        bo_name = actor.get('target_bindings', {}).get('blender_object')
        spawn_mark = actor.get('spawn_mark')
        if not bo_name:
            continue
        obj = bpy.data.objects.get(bo_name)
        if obj is None:
            _die(
                f"actor object '{bo_name}' not found in scene after import "
                f"(actor '{actor['actor_id']}')",
                2,
            )
        mark_obj = bpy.data.objects.get(spawn_mark)
        if mark_obj is None:
            _die(
                f"spawn_mark '{spawn_mark}' not found in scene "
                f"(actor '{actor['actor_id']}')",
                2,
            )
        obj.location = mark_obj.location.copy()
        placement_obj_names.append(bo_name)

    # ── R6: prop placements ──────────────────────────────────────────────────
    for prop in spec['set'].get('props', []):
        at_mark = prop.get('at_mark')
        if not at_mark:
            continue
        asset_id = prop.get('asset_id', '')
        if asset_id not in assets:
            continue
        node_name = assets[asset_id]['node']
        prop_obj = bpy.data.objects.get(node_name)
        if prop_obj is None:
            _die(
                f"prop object '{node_name}' (asset_id='{asset_id}') "
                f"not found after import",
                2,
            )
        mark_obj = bpy.data.objects.get(at_mark)
        if mark_obj is None:
            _die(
                f"prop at_mark '{at_mark}' not found in scene "
                f"(prop '{prop.get('prop_id')}')",
                2,
            )
        # R6 (revised): take mark's x and y but keep prop's own z
        # (prop origins are not floor-based; a full-xyz move buries them)
        prop_obj.location.x = mark_obj.location.x
        prop_obj.location.y = mark_obj.location.y
        # prop_obj.location.z intentionally unchanged
        placement_obj_names.append(node_name)

    # Store sorted unique placement names in scene custom prop for introspect
    scene['_oeb_placements'] = json.dumps(
        sorted(set(placement_obj_names))
    )

    # ── R7 + R8: NLA strips for animation cues ───────────────────────────────
    for shot in shots:
        shot_start = shot['start_time']
        shot_end = shot['end_time']

        for cue in shot.get('cues', []):
            if cue.get('type') != 'animation':
                continue

            cue_id = cue.get('cue_id', '')
            actor_id = cue['actor_id']
            clip_id = cue['clip_id']
            cue_start = cue.get('start_time', 0.0)
            loop = cue.get('loop', False)

            bo_name = actor_map.get(actor_id, {}).get('blender_object')
            if not bo_name:
                _die(
                    f"actor '{actor_id}' has no blender_object binding "
                    f"(cue '{cue_id}')",
                    2,
                )
            obj = bpy.data.objects.get(bo_name)
            if obj is None:
                _die(
                    f"actor object '{bo_name}' not found (cue '{cue_id}')",
                    2,
                )

            # R7: resolve clip to exactly one action
            action = _find_action(clip_id)

            abs_time = shot_start + cue_start
            frame_num = to_frame(abs_time, fps)

            if obj.animation_data is None:
                obj.animation_data_create()

            # R8: one NLA track per cue_id (overlap-proof, deterministic)
            track = obj.animation_data.nla_tracks.new()
            track.name = cue_id

            strip = track.strips.new(cue_id, frame_num, action)

            if loop:
                # R8: repeat = max(1, ceil(shot_frames / action_frames))
                # shot_frames = frame(shot.end_time) - frame(abs_time)
                action_frames = max(
                    1.0,
                    action.frame_range[1] - action.frame_range[0],
                )
                shot_frame_end = to_frame(shot_end, fps)
                available_frames = shot_frame_end - frame_num
                repeat = max(1, math.ceil(available_frames / action_frames))
                strip.repeat = repeat

    # ── R9: shot markers with camera binding ──────────────────────────────────
    for shot in shots:
        frame_num = to_frame(shot['start_time'], fps)
        marker = scene.timeline_markers.new(shot['shot_id'], frame=frame_num)
        cam_id = shot['camera_setup']
        cam_info = grammar_cams.get(cam_id)
        if cam_info:
            cam_obj_name = cam_info['scene_object']
            cam_obj = bpy.data.objects.get(cam_obj_name)
            if cam_obj is None:
                _die(
                    f"camera object '{cam_obj_name}' for setup '{cam_id}' "
                    f"not found in scene",
                    2,
                )
            marker.camera = cam_obj

    # ── R9: dialogue markers ─────────────────────────────────────────────────
    for shot in shots:
        shot_start = shot['start_time']
        for cue in shot.get('cues', []):
            if cue.get('type') != 'dialogue':
                continue
            cue_id = cue.get('cue_id', '')
            abs_time = shot_start + cue.get('start_time', 0.0)
            frame_num = to_frame(abs_time, fps)
            scene.timeline_markers.new(f"dlg_{cue_id}", frame=frame_num)

    # ── R10: save ────────────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    print(f"EXPORT-OK: {blend_path}")
    sys.stdout.flush()

# ─── Introspect mode ──────────────────────────────────────────────────────────

def _introspect(blend_path, manifest_path):
    """
    R11: open a .blend and emit a deterministic JSON introspection manifest.
    Two exports of the same spec produce byte-identical manifests.
    """
    import bpy  # noqa

    abs_blend = os.path.abspath(blend_path)
    if not os.path.isfile(abs_blend):
        _die(f"blend file not found: {abs_blend}", 2)

    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene = bpy.context.scene

    fps = scene.render.fps
    resolution = [scene.render.resolution_x, scene.render.resolution_y]
    frame_start = scene.frame_start
    frame_end = scene.frame_end

    # ── Markers (sorted by frame then name) ───────────────────────────────────
    markers = []
    for m in scene.timeline_markers:
        cam_name = m.camera.name if m.camera else None
        markers.append({
            'camera': cam_name,
            'frame': m.frame,
            'name': m.name,
        })
    markers.sort(key=lambda x: (x['frame'], x['name']))

    # ── NLA (sorted by frame_start then track) ────────────────────────────────
    nla = []
    for obj in bpy.data.objects:
        if not obj.animation_data:
            continue
        for track in obj.animation_data.nla_tracks:
            for strip in track.strips:
                nla.append({
                    'action': strip.action.name if strip.action else None,
                    'frame_start': int(round(strip.frame_start)),
                    'object': obj.name,
                    'repeat': strip.repeat,
                    'track': track.name,
                })
    nla.sort(key=lambda x: (x['frame_start'], x['track']))

    # ── Placements ────────────────────────────────────────────────────────────
    # Object names were stored as a JSON array in a scene custom property
    # during export (scene['_oeb_placements']).
    raw = scene.get('_oeb_placements', '[]')
    if isinstance(raw, str):
        placement_names = json.loads(raw)
    else:
        # Blender may return bytes or other types after save/load
        try:
            placement_names = json.loads(str(raw, 'utf-8'))
        except Exception:
            placement_names = []

    placements = {}
    for name in sorted(placement_names):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            loc = obj.location
            placements[name] = [
                round(float(loc.x), 4),
                round(float(loc.y), 4),
                round(float(loc.z), 4),
            ]

    # ── Assemble and write manifest ───────────────────────────────────────────
    manifest = {
        'fps': fps,
        'frame_end': frame_end,
        'frame_start': frame_start,
        'markers': markers,
        'nla': nla,
        'placements': placements,
        'resolution': resolution,
        'scene': scene.name,
    }

    abs_manifest = os.path.abspath(manifest_path)
    os.makedirs(os.path.dirname(abs_manifest), exist_ok=True)

    with open(abs_manifest, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write('\n')

    print(f"INTROSPECT-OK: {abs_manifest}")
    sys.stdout.flush()

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    args = _parse_args()

    try:
        if args.introspect:
            if not args.manifest:
                _die("--manifest is required with --introspect", 2)
            _introspect(args.introspect, args.manifest)
        elif args.spec:
            _export(args)
        else:
            _die("either --spec or --introspect is required", 2)
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        _die(f"internal error: {exc}", 3)


main()
