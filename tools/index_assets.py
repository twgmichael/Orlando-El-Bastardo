#!/usr/bin/env python3
"""index_assets.py -- deterministic, offline asset library index
(docs/planning/PRODUCTION-DESIGNER-PLAN.md, "Build order" step 1: "the
library is ~750 pieces across 12 packs; 'review available assets' must
be a query, not a per-session expedition").

Walks every .glb under assets/, records per piece: name, pack (its
top-level assets/ subdirectory), file (repo-relative path), a bounding
box and triangle count parsed directly from the GLB's own glTF JSON
chunk (accessor min/max/count -- no Blender launch needed, so indexing
~750 pieces takes seconds, not the many-minutes a per-file `blender
--background` import would cost), and name-derived tags from a small
fixed vocabulary (wall/floor/door/table/... -- a lookup query
vocabulary, not raw filename tokenization).

Deterministic, offline, stdlib-only (matching tools/placeholder_blueprint.py's
own "no extra dependencies" convention) -- no bpy dependency, so this
also runs standalone in CI or any plain .venv/bin/python.

    .venv/bin/python tools/index_assets.py

Regenerate on pack additions; output is data/asset_index.json, sorted
deterministically by (pack, name) so diffs stay small and reviewable.

NOTE: assets/ commonly resolves through a symlink onto an external
drive (see docs/planning/OEB-PROJECT-STATE, "exFAT drive sandbox
denial" gotcha) -- os.walk() below passes followlinks=True explicitly;
without it, packs living behind a symlinked assets/<pack> directory
silently index as empty.
"""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

ASSETS_ROOT = "assets"
OUTPUT_PATH = "data/asset_index.json"

# A lookup vocabulary, not a tokenizer: a piece is tagged with every
# word below that appears as a substring of its filename
# (case-insensitive). Deliberately small and kitbash-relevant per the
# plan's own examples -- extend as real gaps show up during use, not
# speculatively.
TAG_VOCABULARY = (
    "wall", "floor", "door", "window", "table", "chair", "stool",
    "panel", "column", "corner", "shelf", "crate", "console", "screen",
    "pipe", "vent", "light", "lamp", "stair", "ramp", "railing", "roof",
    "ceiling", "counter", "bottle", "glass", "bar", "sofa", "bed",
    "cabinet", "desk", "crate", "container", "engine", "thruster",
    "cockpit", "hull", "wing", "antenna", "dish", "cargo",
)

GLB_MAGIC = 0x46546C67  # "glTF"
CHUNK_JSON = 0x4E4F534A  # "JSON"


def parse_glb_json(path: Path) -> dict | None:
    """Read only the JSON chunk header of a .glb -- no full parse, no
    external glTF library. Returns None (not raised) on anything that
    doesn't look like a well-formed GLB; a bad/partial file must not
    take the whole index down.
    """
    try:
        with open(path, "rb") as f:
            magic, version, length = struct.unpack("<III", f.read(12))
            if magic != GLB_MAGIC:
                return None
            chunk_length, chunk_type = struct.unpack("<II", f.read(8))
            if chunk_type != CHUNK_JSON:
                return None
            return json.loads(f.read(chunk_length))
    except (OSError, struct.error, json.JSONDecodeError):
        return None


def mesh_stats(gltf: dict) -> tuple[list[float] | None, list[float] | None, int]:
    """Aggregate bounding box (min/max) and triangle count across every
    mesh primitive in the glTF JSON. Blender's own glTF exporter always
    writes POSITION accessor min/max (glTF 2.0 spec requires it) and
    indexed triangle primitives, so this is exact for every asset in
    this library, not a heuristic -- but degrades to (None, None, 0)
    rather than crashing if a file breaks that assumption.
    """
    accessors = gltf.get("accessors", [])
    bbox_min = bbox_max = None
    triangles = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            pos_idx = prim.get("attributes", {}).get("POSITION")
            if pos_idx is not None and pos_idx < len(accessors):
                acc = accessors[pos_idx]
                amin, amax = acc.get("min"), acc.get("max")
                if amin and amax:
                    bbox_min = amin if bbox_min is None else [
                        min(a, b) for a, b in zip(bbox_min, amin)]
                    bbox_max = amax if bbox_max is None else [
                        max(a, b) for a, b in zip(bbox_max, amax)]
            idx_idx = prim.get("indices")
            mode = prim.get("mode", 4)  # 4 = TRIANGLES, glTF default
            if idx_idx is not None and idx_idx < len(accessors) and mode == 4:
                triangles += accessors[idx_idx].get("count", 0) // 3
    return bbox_min, bbox_max, triangles


def derive_tags(name: str) -> list[str]:
    lower = name.lower()
    return sorted({tag for tag in TAG_VOCABULARY if tag in lower})


def index_assets(assets_root: str = ASSETS_ROOT) -> list[dict]:
    root = Path(assets_root)
    entries = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        for filename in filenames:
            if not filename.lower().endswith(".glb"):
                continue
            file_path = Path(dirpath) / filename
            try:
                rel_parts = file_path.relative_to(root).parts
            except ValueError:
                continue
            pack = rel_parts[0] if rel_parts else "?"
            name = file_path.stem
            gltf = parse_glb_json(file_path)
            bbox_min = bbox_max = None
            triangle_count = 0
            if gltf is not None:
                bbox_min, bbox_max, triangle_count = mesh_stats(gltf)
            entries.append({
                "name": name,
                "pack": pack,
                "file": str(file_path),
                "bbox_min": bbox_min,
                "bbox_max": bbox_max,
                "triangle_count": triangle_count,
                "tags": derive_tags(name),
            })
    entries.sort(key=lambda e: (e["pack"], e["name"]))
    return entries


def main() -> int:
    entries = index_assets()
    packs = sorted({e["pack"] for e in entries})
    output = {
        "schema_version": "1.0.0",
        "generated_from": ASSETS_ROOT,
        "piece_count": len(entries),
        "pack_count": len(packs),
        "packs": packs,
        "pieces": entries,
    }
    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")
    print(f"[index_assets] {len(entries)} piece(s) across {len(packs)} "
          f"pack(s) -> {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
