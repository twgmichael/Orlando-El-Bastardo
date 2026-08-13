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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oeb_blender.cue_execution import apply_fx_cue  # noqa: E402
from oeb_blender.cue_execution import apply_move as _shared_apply_move  # noqa: E402
from oeb_blender.cue_execution import apply_nla_clip, to_frame  # noqa: E402
from oeb_blender.space_env import setup_space_env  # noqa: E402

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

# ─── R12: move-cue keyframing ─────────────────────────────────────────────────
# Now lives in oeb_blender/cue_execution.py, shared with
# blueprint_interpreter.py's play_move_cue/play_animation_cue operations
# (docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 11 item 3) --
# this wrapper just translates that shared code's ValueError into this
# script's die(2) convention, preserving exact prior behavior.

def _apply_move(obj, cue, start_frame, end_frame, fps):
    try:
        _shared_apply_move(obj, cue, start_frame, end_frame, fps)
    except ValueError as exc:
        _die(str(exc), 2)

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
    import mathutils  # noqa

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
            if ctype not in ('animation', 'dialogue', 'move', 'fx'):
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
    for shot in shots:
        for cue in shot.get('cues', []):
            if cue.get('type') == 'fx':
                fxid = cue.get('fx_id', '')
                if fxid in assets:
                    file_set.add(assets[fxid]['file'])

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

    # ── R5: environment preset (SetSpec.environment) ─────────────────────────
    # An EXT space location with no real set geometry gets its backdrop from
    # here instead: star sphere + emissive sun + bloom, same recipe as
    # docs/world-building/SPACESCAPE.md, shared with blueprint_interpreter.py's
    # set_environment operation via tools/oeb_blender/space_env.py.
    environment = spec['set'].get('environment')
    if environment == 'deep_space':
        setup_space_env(scene)

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
    # An actual imported node shared by 2+ actors in this scene (e.g.
    # Casting Director's shared background placeholder -- see docs/bug-fix/
    # E-DUPLICATE-CHARACTER-CORRECTION.md) can't just be moved once per
    # actor: bpy.data.objects.get(real_node) always returns the SAME
    # object, so the second actor's placement silently clobbers the
    # first's, with no error. Collection Instancing (the pattern already
    # proven in tools/jb100_hyberspace_swarm_draft.py's fleet swarm) fixes
    # this: the shared object's geometry moves into its own hidden
    # collection once, and every actor that needs it gets its own
    # lightweight Empty instance pointed at that collection. An actor
    # whose node is unique to it (the common case) is untouched -- same
    # direct move as before, zero behavior change for every scene that
    # already delivers correctly today.
    #
    # Sharing must be detected on the REAL resolved node, not the raw
    # blender_object/character_id: the E_DUPLICATE_CHARACTER registry
    # fix gives every background role its OWN character_id precisely so
    # they're registry-distinct, which means two actors can perfectly
    # legitimately have different character_ids that both resolve
    # (via assets[...]['node']) to the identical real imported object.
    # Counting raw character_ids here would never see that collision.
    node_counts = {}
    for actor in spec['actors']:
        bo_name = actor.get('target_bindings', {}).get('blender_object')
        if bo_name:
            real_node = assets.get(bo_name, {}).get('node', bo_name)
            node_counts[real_node] = node_counts.get(real_node, 0) + 1
    shared_nodes = {node for node, n in node_counts.items() if n > 1}
    instance_collections = {}   # real_node -> its hidden source Collection

    for actor in spec['actors']:
        bo_name = actor.get('target_bindings', {}).get('blender_object')
        spawn_mark = actor.get('spawn_mark')
        if not bo_name:
            continue
        # bo_name is target_bindings.blender_object == the actor's
        # character_id (tools/resolve_intent.py sets it directly). That's
        # only ever a real imported object name when the registry's own
        # "node" field defaults to canonical_id (register_placeholder_asset()'s
        # default) -- a role sharing another asset's build (the
        # E_DUPLICATE_CHARACTER fix) registers its OWN character_id with
        # node pointing at the asset that was ACTUALLY imported, so
        # resolve through it here, same as the props loop below already
        # does via assets[asset_id]['node'].
        real_node = assets.get(bo_name, {}).get('node', bo_name)
        obj = bpy.data.objects.get(real_node)
        if obj is None:
            _die(
                f"actor object '{real_node}' (blender_object='{bo_name}') "
                f"not found in scene after import (actor '{actor['actor_id']}')",
                2,
            )
        mark_obj = bpy.data.objects.get(spawn_mark)
        if mark_obj is None:
            _die(
                f"spawn_mark '{spawn_mark}' not found in scene "
                f"(actor '{actor['actor_id']}')",
                2,
            )

        if real_node in shared_nodes:
            src_col = instance_collections.get(real_node)
            if src_col is None:
                # First actor to need this shared asset: move its
                # imported geometry into a dedicated hidden collection,
                # once -- it becomes a template, never rendered itself.
                src_col = bpy.data.collections.new(f"{real_node}_SRC")
                for col in list(obj.users_collection):
                    col.objects.unlink(obj)
                src_col.objects.link(obj)
                obj.hide_render = True
                obj.hide_viewport = True
                instance_collections[real_node] = src_col
            inst_name = f"{real_node}__{actor['actor_id']}"
            inst = bpy.data.objects.new(inst_name, None)
            scene.collection.objects.link(inst)
            inst.instance_type = 'COLLECTION'
            inst.instance_collection = src_col
            inst.location = mark_obj.location.copy()
            # Downstream cue application (move/animation/fx, R7/R8/R13)
            # looks actors up by actor_map[...]['blender_object'] -- point
            # it at this actor's own instance, not the shared template.
            actor_map[actor['actor_id']]['blender_object'] = inst_name
            placement_obj_names.append(inst_name)
        else:
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

        # R6 (2026-08-09): props get no cue of their own -- unlike actors,
        # nothing in a shot's cues ever names a prop_id -- so a prop's own
        # baked ambient animation (e.g. the mining probe's beacon blink)
        # would otherwise never play: R4 already cleared every imported
        # object's animation_data, keeping only the underlying actions.
        # Auto-trigger it here, looped for the whole scene, using the same
        # naming-convention discovery apply_fx_cue() uses -- no per-prop
        # authoring, and props with no matching action are silently
        # unaffected (most have none).
        for obj in [prop_obj] + prop_obj.children_recursive:
            clip_id = f"{obj.name}Action"
            try:
                apply_nla_clip(
                    obj, clip_id, clip_id, 1, fps,
                    loop=True, available_frames=scene.frame_end,
                )
            except ValueError:
                continue

    # Store sorted unique placement names in scene custom prop for introspect
    scene['_oeb_placements'] = json.dumps(
        sorted(set(placement_obj_names))
    )

    # ── R7 + R8: NLA strips for animation/move cues, keyframes for moves ─────
    for shot in shots:
        shot_start = shot['start_time']
        shot_end = shot['end_time']

        for cue in shot.get('cues', []):
            ctype = cue.get('type')
            if ctype not in ('animation', 'move'):
                continue

            cue_id = cue.get('cue_id', '')
            actor_id = cue['actor_id']
            clip_id = cue.get('clip_id')
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

            abs_time = shot_start + cue_start
            frame_num = to_frame(abs_time, fps)

            # R12 (move cues, 2026-07-11): keyframe the object transform
            # from from_mark to to_mark across the cue duration.
            if ctype == 'move':
                move_end_frame = to_frame(abs_time + cue['duration'], fps)
                _apply_move(obj, cue, frame_num, move_end_frame, fps)
                if not clip_id:
                    continue   # transform-only move

            # R7/R8: resolve clip, create the NLA track/strip (HOLD_FORWARD
            # extrapolation, optional crossfade, optional loop-to-fill) --
            # a looped move clip fills the MOVE duration, a looped
            # animation cue fills the rest of the shot.
            if ctype == 'move':
                available_frames = move_end_frame - frame_num
            else:
                available_frames = to_frame(shot_end, fps) - frame_num
            try:
                apply_nla_clip(
                    obj, cue_id, clip_id, frame_num, fps,
                    blend_in=cue.get('blend_in', 0.0),
                    loop=loop,
                    available_frames=available_frames,
                )
            except ValueError as exc:
                _die(str(exc), 2)

    # ── R13: fx cues (multi-object effect rigs, e.g. Hyperspace Effect) ──────
    for shot in shots:
        shot_start = shot['start_time']
        for cue in shot.get('cues', []):
            if cue.get('type') != 'fx':
                continue

            cue_id = cue.get('cue_id', '')
            fxid = cue['fx_id']
            actor_id = cue['actor_id']
            cue_start = cue.get('start_time', 0.0)

            bo_name = actor_map.get(actor_id, {}).get('blender_object')
            if not bo_name:
                _die(f"actor '{actor_id}' has no blender_object binding (cue '{cue_id}')", 2)
            target_obj = bpy.data.objects.get(bo_name)
            if target_obj is None:
                _die(f"actor object '{bo_name}' not found (cue '{cue_id}')", 2)

            root_name = assets.get(fxid, {}).get('node')
            if not root_name:
                _die(f"fx asset '{fxid}' not found in oeb.config.json assets (cue '{cue_id}')", 2)
            root_obj = bpy.data.objects.get(root_name)
            if root_obj is None:
                _die(f"fx asset root object '{root_name}' not found (cue '{cue_id}')", 2)

            frame_num = to_frame(shot_start + cue_start, fps)
            apply_fx_cue(root_obj, target_obj, frame_num, fps)

    # ── R9: shot markers with camera binding ──────────────────────────────────
    fallback_cam = {"obj": None}

    def _fallback_camera():
        # A placeholder set (tools/placeholder_blueprint.py) has no
        # camera baked into its .glb at all -- Blueprint's own reserved
        # "camera" is excluded from geometry export by design (it's a
        # scene-level sibling of the asset root, not asset geometry).
        # render_blend.py hard-requires *some* camera bound to a
        # marker, so a scene with zero real camera_grammar matches
        # needs one created here, lazily, once, shared across every
        # unbound marker -- same simple framing
        # blueprint_interpreter.py's own _setup_default_preview_camera
        # falls back to when nothing else says where the camera goes.
        if fallback_cam["obj"] is None:
            cam_data = bpy.data.cameras.new("fallback_camera")
            cam_obj = bpy.data.objects.new("fallback_camera", cam_data)
            scene.collection.objects.link(cam_obj)
            cam_obj.location = (0.0, -8.0, 3.0)
            direction = mathutils.Vector((0.0, 0.0, 1.0)) - cam_obj.location
            cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            fallback_cam["obj"] = cam_obj
            print("EXPORT-WARNING: no camera_grammar scene_object found anywhere in "
                  "this scene's imported sets; created a default fallback camera",
                  file=sys.stderr)
        return fallback_cam["obj"]

    for shot in shots:
        frame_num = to_frame(shot['start_time'], fps)
        marker = scene.timeline_markers.new(shot['shot_id'], frame=frame_num)
        cam_id = shot['camera_setup']
        cam_info = grammar_cams.get(cam_id)
        if cam_info:
            cam_obj_name = cam_info['scene_object']
            cam_obj = bpy.data.objects.get(cam_obj_name)
            if cam_obj is None:
                # validate_spec.py's V5 already treats this as a warning
                # (unsupported_camera_grammar), not an error -- matching
                # that leniency here, but the marker still needs *some*
                # bound camera for render_blend.py to work at all.
                print(f"EXPORT-WARNING: camera object '{cam_obj_name}' for setup "
                      f"'{cam_id}' not found in scene; binding the fallback camera",
                      file=sys.stderr)
                marker.camera = _fallback_camera()
            else:
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
