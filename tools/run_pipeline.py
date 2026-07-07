#!/usr/bin/env python3
"""
run_pipeline.py — the pipeline's single front door (SEAMLESS-RUN-PLAN Tier 1).

One command: script in → render out. Subprocesses each stage with the
pipeline's exit-code discipline; any stage failure stops the run with a
stage-tagged error and that stage's output.

  brief (--brief)  → generate_intent (local LLM, temp 0)
  intent (--intent)→ resolve_intent → validate_spec → export_blender
                   → [optional: export_godot, export_usd]
                   → render_blend → MP4

Run from repo root:
  .venv/bin/python tools/run_pipeline.py --intent fixtures/bar_scene.sceneintent.json
  .venv/bin/python tools/run_pipeline.py --brief fixtures/bar_scene.brief.md --targets all
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tickets  # noqa: E402 — the production office (PRODUCER-PLAN P1)

VENV_PY = ".venv/bin/python"
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"

# Exit codes: 0 delivered; 2 bad input; 3 internal; 4 BLOCKED — the scene
# needs assets the library lacks; a NEEDED ticket has been written.
EXIT_BLOCKED = 4


def parse_args():
    p = argparse.ArgumentParser(prog="run_pipeline")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--brief", help="Approved brief → LLM translator front end")
    src.add_argument("--intent", help="SceneIntent JSON (skips the LLM)")
    p.add_argument("--targets", default="blender",
                   help='"blender" (default), comma list, or "all" '
                        "(godot/usd exports in addition to the render path)")
    p.add_argument("--render-out", default=None,
                   help="MP4 path (default renders/reviews/<scene_id>_pipeline.mp4)")
    p.add_argument("--no-render", action="store_true",
                   help="Stop after exports (no MP4)")
    p.add_argument("--temp", default="0.0", help="LLM temperature (brief mode)")
    p.add_argument("--seed", default="1", help="LLM seed (brief mode)")
    p.add_argument("--episode", default="dev",
                   help="Episode id for the production report/tickets "
                        "(out/production/<episode>/; default: dev)")
    return p.parse_args()


def stage(name, cmd, timeout=1800):
    print(f"[run_pipeline] ── {name}: {' '.join(cmd[:6])}{' …' if len(cmd) > 6 else ''}")
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         stdin=subprocess.DEVNULL)
    if run.returncode != 0:
        print(f"[run_pipeline] STAGE-FAILED {name} (exit {run.returncode})",
              file=sys.stderr)
        tail = (run.stdout + "\n" + run.stderr).strip().splitlines()[-25:]
        print("\n".join(tail), file=sys.stderr)
        sys.exit(run.returncode if run.returncode in (1, 2, 3) else 3)
    return run


def blender_stage(name, script, script_args, timeout=1800):
    return stage(name, [BLENDER, "--background", "--factory-startup",
                        "--python", script, "--"] + script_args, timeout)


def main():
    args = parse_args()
    targets = ({"blender", "godot", "usd"} if args.targets == "all"
               else {t.strip() for t in args.targets.split(",") if t.strip()})
    unknown = targets - {"blender", "godot", "usd"}
    if unknown:
        print(f"[run_pipeline] ERROR: unknown targets {sorted(unknown)}",
              file=sys.stderr)
        sys.exit(2)

    intent_path = args.intent
    if args.brief:
        intent_path = "out/llm/pipeline_intent.json"
        stage("generate-intent", [VENV_PY, "tools/generate_intent.py",
                                  "--brief", args.brief, "--out", intent_path,
                                  "--temp", args.temp, "--seed", args.seed],
              timeout=900)

    scene_id = json.load(open(intent_path))["scene_id"]
    spec = f"out/{scene_id}.scenespec.json"
    report = f"out/{scene_id}.validationreport.json"
    blend = f"out/blender/{scene_id}.blend"

    # Resolve + validate are the missing-asset sensors: their library-class
    # failures become NEEDED tickets (scene BLOCKED, exit 4); anything else
    # stays a plain stage failure.
    run = subprocess.run([VENV_PY, "tools/resolve_intent.py",
                          "--intent", intent_path, "--out", spec],
                         capture_output=True, text=True, timeout=600,
                         stdin=subprocess.DEVNULL)
    print(f"[run_pipeline] ── resolve: exit {run.returncode}")
    if run.returncode != 0:
        missing = tickets.missing_from_resolver(run.stderr)
        if missing:
            tpath = tickets.write_ticket(args.episode, scene_id, missing,
                                         script_ref=args.brief or intent_path)
            rpath = tickets.update_report(args.episode, scene_id,
                                          "NEEDS_ASSETS",
                                          ticket=os.path.basename(tpath))
            print(f"[run_pipeline] BLOCKED — scene needs assets the library "
                  f"lacks.\n  ticket: {tpath}\n  report: {rpath}",
                  file=sys.stderr)
            sys.exit(EXIT_BLOCKED)
        print(f"[run_pipeline] STAGE-FAILED resolve\n{run.stderr[-1500:]}",
              file=sys.stderr)
        tickets.update_report(args.episode, scene_id, "FAILED",
                              stage="resolve")
        sys.exit(run.returncode if run.returncode in (1, 2, 3) else 3)

    run = subprocess.run([VENV_PY, "tools/validate_spec.py",
                          "--spec", spec, "--out", report],
                         capture_output=True, text=True, timeout=600,
                         stdin=subprocess.DEVNULL)
    print(f"[run_pipeline] ── validate: exit {run.returncode}")
    if run.returncode != 0:
        missing = []
        if os.path.exists(report):
            missing = tickets.missing_from_validation(json.load(open(report)))
        if missing:
            tpath = tickets.write_ticket(args.episode, scene_id, missing,
                                         script_ref=args.brief or intent_path)
            rpath = tickets.update_report(args.episode, scene_id,
                                          "NEEDS_ASSETS",
                                          ticket=os.path.basename(tpath))
            print(f"[run_pipeline] BLOCKED — scene needs assets the library "
                  f"lacks.\n  ticket: {tpath}\n  report: {rpath}",
                  file=sys.stderr)
            sys.exit(EXIT_BLOCKED)
        print(f"[run_pipeline] STAGE-FAILED validate\n{run.stderr[-1500:]}",
              file=sys.stderr)
        tickets.update_report(args.episode, scene_id, "FAILED",
                              stage="validate")
        sys.exit(1)

    if "blender" in targets or not args.no_render:
        blender_stage("export-blender", "tools/export_blender.py",
                      ["--spec", spec, "--out", blend])
    if "godot" in targets:
        stage("export-godot", [VENV_PY, "tools/export_godot.py", "--spec", spec])
    if "usd" in targets:
        stage("export-usd", [VENV_PY, "tools/export_usd.py", "--spec", spec])

    if args.no_render:
        tickets.update_report(args.episode, scene_id, "DELIVERED_NO_RENDER",
                              spec=spec)
        print(f"[run_pipeline] DONE (no render) — spec {spec}")
        return

    render_out = args.render_out or f"renders/reviews/{scene_id}_pipeline.mp4"
    blender_stage("render", "tools/render_blend.py",
                  ["--blend", blend, "--output", render_out], timeout=3600)

    size_kb = os.path.getsize(render_out) // 1024
    rpath = tickets.update_report(args.episode, scene_id, "DELIVERED",
                                  spec=spec, render=render_out)
    print(f"[run_pipeline] DONE — {render_out} ({size_kb} KB)\n"
          f"[run_pipeline] report: {rpath}")


if __name__ == "__main__":
    main()
