#!/usr/bin/env python3
"""
batch_convert_glb.py — Headless Blender: batch-convert asset-pack sources
(.fbx / .gltf) to packed single-file .glb.

Walks the given source directories, imports each matching file into a fresh
scene, and exports `<pack>/GLB/<stem>.glb` (textures embedded). Existing
outputs are skipped unless --force. Prints a per-file OK/FAIL summary and a
final count; exits nonzero if any file failed.

Run from repo root:
  blender --background --factory-startup \
    --python tools/batch_convert_glb.py -- \
    --src "assets/Ultimate Modular Sci-Fi - Feb 2021/FBX" \
    --out "assets/Ultimate Modular Sci-Fi - Feb 2021/GLB"
"""

import sys
import os
import argparse

import bpy

EXTS = (".fbx", ".gltf")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="batch_convert_glb")
    p.add_argument("--src", required=True, help="Source directory (recursed)")
    p.add_argument("--out", required=True, help="Output directory for .glb files")
    p.add_argument("--force", action="store_true")
    return p.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def convert(src_path, out_path):
    reset_scene()
    ext = os.path.splitext(src_path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=src_path)
    else:
        bpy.ops.import_scene.gltf(filepath=src_path)
    if not bpy.data.objects:
        raise RuntimeError("import produced no objects")
    # Quaternius Blender-export materials often arrive alpha-MASK/HASHED
    # with alpha 0 — invisible downstream (found on the sci-fi kit, again on
    # the modular garments). Normalize to opaque unless the material really
    # uses an alpha TEXTURE link.
    for mat in bpy.data.materials:
        if hasattr(mat, "blend_method") and mat.use_nodes:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf and "Alpha" in bsdf.inputs and not bsdf.inputs["Alpha"].links:
                mat.blend_method = 'OPAQUE'
                bsdf.inputs["Alpha"].default_value = 1.0
    bpy.ops.export_scene.gltf(
        filepath=out_path, export_format='GLB', use_selection=False,
        export_animations=True, export_cameras=False,
    )


def main():
    args = parse_args()
    src_root = os.path.abspath(args.src)
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    # Collect sources, then dedupe by stem PREFERRING .gltf over .fbx —
    # vendor packs ship both, and the FBX twins can lack texture links
    # (found 2026-07-06: Space Kit atlas missing when FBX dirs walked first).
    found = {}
    for dirpath, _dirs, files in os.walk(src_root):
        for f in sorted(files):
            if f.lower().endswith(EXTS) and not f.startswith("."):
                stem = os.path.splitext(f)[0]
                ext = os.path.splitext(f)[1].lower()
                if stem not in found or (ext == ".gltf" and
                                         found[stem][1] == ".fbx"):
                    found[stem] = (os.path.join(dirpath, f), ext)
    sources = sorted(path for path, _ext in found.values())

    ok, failed, skipped = [], [], []
    for src in sources:
        stem = os.path.splitext(os.path.basename(src))[0]
        out = os.path.join(out_root, stem + ".glb")
        if os.path.exists(out) and not args.force:
            skipped.append(stem)
            continue
        try:
            convert(src, out)
            ok.append(stem)
            print(f"[batch_convert_glb] OK   {stem}")
        except Exception as exc:  # noqa: BLE001 — report and continue the batch
            failed.append((stem, str(exc)[:120]))
            print(f"[batch_convert_glb] FAIL {stem}: {exc}")

    print(f"[batch_convert_glb] done: {len(ok)} converted, "
          f"{len(skipped)} skipped, {len(failed)} failed "
          f"(of {len(sources)} sources)")
    for stem, err in failed:
        print(f"  FAILED: {stem}: {err}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
