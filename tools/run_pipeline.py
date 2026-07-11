#!/usr/bin/env python3
"""
run_pipeline.py — the pipeline's single front door (SEAMLESS-RUN-PLAN Tier 1
+ PRODUCER-PLAN P1/P3 gates).

One command: script in → render out. Subprocesses each stage with the
pipeline's exit-code discipline; failures are classified (see tickets.py):
missing-library errors → NEEDED ticket + exit 4 (BLOCKED); bugs → FAILED.

Brief path protections (2026-07-07):
- Scene-fact STAMPING: structural facts (`scene_id`, `- location:`,
  `- time:`) parsed from the brief override the translator's output — the
  LLM gets no vote on where/when a scene happens.
- Verbatim FIDELITY GATE: the resolved spec's dialogue must match the
  brief's quoted lines exactly (order, speaker, text). One retry at
  seed+1, then FAILED — never deliver a scene that dropped a line.

Render QA gates: duration vs. spec (±0.6 s) and non-black frame sampling.

Exit codes: 0 delivered; 2 bad input; 3 internal/QA/fidelity failure;
4 BLOCKED (NEEDED ticket written).

Run from repo root:
  .venv/bin/python tools/run_pipeline.py --intent fixtures/bar_scene.sceneintent.json
  .venv/bin/python tools/run_pipeline.py --brief fixtures/bar_scene.brief.md --episode dev
"""

import argparse
import glob as globmod
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tickets  # noqa: E402

VENV_PY = ".venv/bin/python"
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
EXIT_BLOCKED = 4


def parse_args():
    p = argparse.ArgumentParser(prog="run_pipeline")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--brief", help="Approved brief → LLM translator front end")
    src.add_argument("--intent", help="SceneIntent JSON (skips the LLM)")
    p.add_argument("--targets", default="blender",
                   help='"blender" (default), comma list, or "all"')
    p.add_argument("--render-out", default=None)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--temp", default="0.0")
    p.add_argument("--seed", default="1")
    p.add_argument("--episode", default="dev",
                   help="Episode id for tickets/report (out/production/<id>/)")
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


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = globmod.glob(os.path.join(
        os.getcwd(), ".venv/lib/python*/site-packages/imageio_ffmpeg/"
                     "binaries/ffmpeg-*"))
    return hits[0] if hits else None


# ── Brief-path helpers ──────────────────────────────────────────────────────

def parse_scene_facts(brief_text):
    """Structural facts the translator gets no vote on. The LAST declaration
    in the brief wins: desk-generated briefs put the shared vocabulary block
    before the scene's own metadata, and specific must beat general (found
    2026-07-07: first-match stamped the vocab default over the scene's
    location)."""
    facts = {}
    m = re.findall(r"^-\s*scene_id:\s*`?([a-z][a-z0-9_]*)`?", brief_text, re.M)
    if m:
        facts["scene_id"] = m[-1]
    m = re.findall(r"^-\s*location(?:_tag)?:\s*`?([a-z][a-z0-9_]*)`?",
                   brief_text, re.M)
    if m:
        facts["location_tag"] = m[-1]
    m = re.findall(r"^-\s*time(?:_of_day)?:\s*`?([a-z]+)`?", brief_text, re.M)
    if m:
        facts["time_of_day"] = m[-1]
    return facts


def brief_dialogue(brief_text):
    """Approved lines: `- NAME: "text"` → [(actor_id, text)] in order."""
    return [(m.group(1).lower(), m.group(2)) for m in
            re.finditer(r'^-\s*([A-Z][A-Z_]*):\s*"(.+)"\s*$', brief_text, re.M)]


def spec_dialogue(spec_path):
    d = json.load(open(spec_path))
    return [(c["actor_id"], c["text"])
            for s in sorted(d["shots"], key=lambda s: s["order"])
            for c in s["cues"] if c["type"] == "dialogue"]


def generate_and_stamp(brief_path, facts, intent_path, temp, seed):
    stage("generate-intent", [VENV_PY, "tools/generate_intent.py",
                              "--brief", brief_path, "--out", intent_path,
                              "--temp", temp, "--seed", seed], timeout=900)
    intent = json.load(open(intent_path))
    intent.update(facts)
    with open(intent_path, "w") as f:
        json.dump(intent, f, indent=2)
        f.write("\n")


def resolve_or_block(intent_path, spec, episode, scene_id, script_ref):
    """Resolve; classify failure into NEEDED ticket (exit 4) or FAILED."""
    run = subprocess.run([VENV_PY, "tools/resolve_intent.py",
                          "--intent", intent_path, "--out", spec],
                         capture_output=True, text=True, timeout=600,
                         stdin=subprocess.DEVNULL)
    print(f"[run_pipeline] ── resolve: exit {run.returncode}")
    if run.returncode == 0:
        return
    missing = tickets.missing_from_resolver(run.stderr)
    if missing:
        tpath = tickets.write_ticket(episode, scene_id, missing,
                                     script_ref=script_ref)
        rpath = tickets.update_report(episode, scene_id, "NEEDS_ASSETS",
                                      ticket=os.path.basename(tpath))
        print(f"[run_pipeline] BLOCKED — scene needs assets the library "
              f"lacks.\n  ticket: {tpath}\n  report: {rpath}", file=sys.stderr)
        sys.exit(EXIT_BLOCKED)
    print(f"[run_pipeline] STAGE-FAILED resolve\n{run.stderr[-1500:]}",
          file=sys.stderr)
    tickets.update_report(episode, scene_id, "FAILED", stage="resolve")
    sys.exit(run.returncode if run.returncode in (1, 2, 3) else 3)


def qa_render(render_out, spec_path, ffmpeg):
    """Duration vs spec (±0.6 s) + non-black sampling. Returns error or None."""
    d = json.load(open(spec_path))
    expect = max(s["end_time"] for s in d["shots"])
    probe = subprocess.run([ffmpeg, "-i", render_out],
                           capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not m:
        return "QA: could not read duration"
    got = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    if abs(got - expect) > 0.6:
        return f"QA: duration {got:.2f}s vs spec {expect:.2f}s"
    for t in (expect * 0.1, expect * 0.5, expect * 0.9):
        r = subprocess.run([ffmpeg, "-ss", f"{t:.2f}", "-i", render_out,
                            "-frames:v", "1", "-vf", "signalstats",
                            "-f", "null", "-"],
                           capture_output=True, text=True)
        ym = re.findall(r"YAVG:(\d+\.?\d*)", r.stderr)
        if ym and float(ym[-1]) < 4.0:
            return f"QA: near-black frame at {t:.1f}s (YAVG {ym[-1]})"
    return None


def main():
    args = parse_args()
    targets = ({"blender", "godot", "usd"} if args.targets == "all"
               else {t.strip() for t in args.targets.split(",") if t.strip()})
    unknown = targets - {"blender", "godot", "usd"}
    if unknown:
        print(f"[run_pipeline] ERROR: unknown targets {sorted(unknown)}",
              file=sys.stderr)
        sys.exit(2)

    script_ref = args.brief or args.intent
    intent_path = args.intent
    expected_lines = None
    facts = {}
    if args.brief:
        brief_text = open(args.brief).read()
        facts = parse_scene_facts(brief_text)
        expected_lines = brief_dialogue(brief_text)
        intent_path = "out/llm/pipeline_intent.json"
        generate_and_stamp(args.brief, facts, intent_path, args.temp, args.seed)

    scene_id = json.load(open(intent_path))["scene_id"]
    spec = f"out/{scene_id}.scenespec.json"
    report = f"out/{scene_id}.validationreport.json"
    blend = f"out/blender/{scene_id}.blend"

    resolve_or_block(intent_path, spec, args.episode, scene_id, script_ref)

    # Verbatim fidelity gate (brief path): one retry at seed+1, then FAILED.
    if expected_lines is not None and spec_dialogue(spec) != expected_lines:
        print("[run_pipeline] fidelity gate: dialogue mismatch — retrying "
              "at seed+1")
        generate_and_stamp(args.brief, facts, intent_path, args.temp,
                           str(int(args.seed) + 1))
        resolve_or_block(intent_path, spec, args.episode, scene_id, script_ref)
        if spec_dialogue(spec) != expected_lines:
            tickets.update_report(args.episode, scene_id, "FAILED",
                                  stage="fidelity")
            print("[run_pipeline] FAILED — translation fidelity: resolved "
                  "dialogue does not match the approved brief verbatim",
                  file=sys.stderr)
            sys.exit(3)
        print("[run_pipeline] fidelity gate: retry passed")

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
                                         script_ref=script_ref)
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

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        qa_err = qa_render(render_out, spec, ffmpeg)
        if qa_err:
            tickets.update_report(args.episode, scene_id, "FAILED",
                                  stage="render-qa", detail=qa_err)
            print(f"[run_pipeline] FAILED — {qa_err}", file=sys.stderr)
            sys.exit(3)
        print("[run_pipeline] render QA: pass")

    size_kb = os.path.getsize(render_out) // 1024
    rpath = tickets.update_report(args.episode, scene_id, "DELIVERED",
                                  spec=spec, render=render_out)
    print(f"[run_pipeline] DONE — {render_out} ({size_kb} KB)\n"
          f"[run_pipeline] report: {rpath}")


if __name__ == "__main__":
    main()
