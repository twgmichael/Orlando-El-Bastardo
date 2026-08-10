#!/usr/bin/env python3
"""register_kitbash_set.py -- the set designer kitbash tier's approval
propagation step (docs/planning/PRODUCTION-DESIGNER-PLAN.md): once a
human approves a kitbashed set in the oeb-studio-harness review UI
(/review/kitbash), a `kitbash.register` job runs this script on a
worker to write the REAL file registries (oeb.config.json,
data/resolver_map.json) the deterministic pipeline (tools/producer.py,
tools/resolve_intent.py) actually reads -- the harness's own Asset row
is a review/approval record, a separate system from these files (same
"genuinely different systems, DB vs. file" split documented in
tools/placeholder_blueprint.py); approving in the harness must
propagate out to here, not just flip a status bit there.

Runs as a job on the existing worker-agent job queue
(docs/planning/WORKER-AGENT-PLAN.md), via the *existing*
BlenderCLIAdapter's `script_file` payload mode -- no new adapter.
Deliberately stdlib-only (no bpy needed), matching
tools/set_designer.py's own convention, so it runs identically under
Blender's bundled Python (as the worker invokes it) or the project's
own .venv (for direct CLI use/testing).

If --location-tag names a location that already has a resolver_map.json
entry (the common case: a kitbash set upgrading a prior tier-1
stand-in or tier-2 placeholder), that entry's own marks are preserved
and merged with the new set's marks rather than dropped -- a kitbash
build's SetSpec typically only lists marks it adds or repositions,
carrying the rest over from its base_placeholder (see
schemas/setspec.schema.json), so the existing registry entry is the
only place the full mark set is known.

KNOWN LIMITATION: does not register data/camera_grammar.json entries
for any new cameras the set spec defines -- SetSpec's cameras[] has no
framing-purpose field (establishing/two_shot/close_on/medium_on) to
derive a camera_grammar.json entry from without inventing one; wiring
that vocabulary is deliberately left as human/Director follow-up work,
not silently skipped without a mention. The cameras themselves ARE
exported into the built GLB either way.

CLI:
  .venv/bin/python tools/register_kitbash_set.py \\
      --canonical-id set_bar_small_A --glb-path assets/sets/set_bar_small_A/set_bar_small_A.glb \\
      --spec-path data/setspecs/bar_scene_scifi.setspec.json \\
      --location-tag small_bar_interior
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONFIG_PATH = "oeb.config.json"
RESOLVER_MAP_PATH = "data/resolver_map.json"


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _write_json(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def register_kitbash_asset(
    config_path: str, canonical_id: str, glb_path: str, node_name: str,
    *, source: str = "set_designer_kitbash",
) -> None:
    config = _load_json(config_path)
    assets = config.setdefault("assets", {})
    assets[canonical_id] = {
        "file": glb_path,
        "node": node_name,
        "kind": "location",
        "placeholder": False,
        "source": source,
    }
    _write_json(config_path, config)


def register_kitbash_location(
    resolver_map_path: str, location_tag: str, canonical_id: str, marks: list[str],
    *, source: str = "set_designer_kitbash",
) -> None:
    """Create or upgrade *location_tag*'s resolver_map.json entry.
    Merges *marks* into any marks the entry already had (see module
    docstring) rather than replacing them.
    """
    rmap = _load_json(resolver_map_path)
    locations = rmap.setdefault("locations", {})
    existing = locations.get(location_tag, {})
    merged_marks = sorted(set(existing.get("marks", [])) | set(marks))
    locations[location_tag] = {
        "set_id": canonical_id,
        "variants": {"morning": "kitbash", "day": "kitbash",
                     "evening": "kitbash", "night": "kitbash"},
        "marks": merged_marks,
        "default_props": existing.get("default_props", []),
        "placeholder": False,
        "source": source,
    }
    _write_json(resolver_map_path, rmap)


def main() -> int:
    # Same Blender-launch argv convention as tools/set_designer.py: only
    # what's after `--` belongs to this script when run under
    # `blender --background --python ... -- <args>`.
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    p = argparse.ArgumentParser(prog="register_kitbash_set")
    p.add_argument("--canonical-id", required=True)
    p.add_argument("--glb-path", required=True)
    p.add_argument("--spec-path", required=True)
    p.add_argument("--location-tag", default=None,
                   help="If given, create/upgrade this location's resolver_map.json entry")
    p.add_argument("--config", default=CONFIG_PATH)
    p.add_argument("--resolver-map", default=RESOLVER_MAP_PATH)
    args = p.parse_args(argv)

    if not Path(args.glb_path).exists():
        print(f"[register_kitbash_set] ERROR: glb not found: {args.glb_path}")
        return 1
    if not Path(args.spec_path).exists():
        print(f"[register_kitbash_set] ERROR: spec not found: {args.spec_path}")
        return 1
    spec = _load_json(args.spec_path)

    register_kitbash_asset(
        args.config, args.canonical_id, args.glb_path,
        spec.get("canonical_node", args.canonical_id))
    print(f"[register_kitbash_set] registered asset {args.canonical_id!r} "
          f"-> {args.glb_path}")

    if args.location_tag:
        marks = [m["name"] for m in spec.get("marks", [])]
        register_kitbash_location(
            args.resolver_map, args.location_tag, args.canonical_id, marks)
        print(f"[register_kitbash_set] registered location "
              f"{args.location_tag!r} -> {args.canonical_id!r}")
    else:
        print("[register_kitbash_set] no --location-tag given; "
              "asset registered but not wired to any location")

    return 0


if __name__ == "__main__":
    sys.exit(main())
