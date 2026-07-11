#!/usr/bin/env python3
"""
script_desk.py — PRODUCER-PLAN P2: script in, episode out.

Approved-script format (deterministic to chunk — no LLM involved in
splitting; the LLM's only job stays per-scene brief → intent translation):

    # EPISODE: ep_001 — optional title
    ## VOCABULARY
    <shared controlled-vocabulary block, prepended to every scene brief>
    ## SCENE: sc_some_scene_001
    <scene body: setting, beats, verbatim dialogue — brief format>
    ## SCENE: sc_other_scene_002
    ...

For each scene the desk assembles a self-contained brief (vocabulary +
scene body), runs the pipeline front door (`run_pipeline.py --brief`), and
classifies the outcome: DELIVERED / NEEDS_ASSETS (ticket, run continues
with the other scenes) / FAILED. Delivered scene renders are concatenated
into the episode cut. World state (config, resolver map, camera grammar)
is snapshotted per episode.

Run from repo root:
  .venv/bin/python tools/script_desk.py --script fixtures/ep_001.script.md
  .venv/bin/python tools/script_desk.py --script ... --no-render
"""

import argparse
import glob as globmod
import json
import os
import re
import shutil
import subprocess
import sys

VENV_PY = ".venv/bin/python"
SNAPSHOT_FILES = ["oeb.config.json", "data/resolver_map.json",
                  "data/camera_grammar.json"]
EXIT_BLOCKED = 4


def parse_args():
    p = argparse.ArgumentParser(prog="script_desk")
    p.add_argument("--script", required=True)
    p.add_argument("--no-render", action="store_true")
    return p.parse_args()


def parse_script(text):
    """Return (episode_id, vocabulary_block, [(scene_id, body), ...])."""
    ep = re.search(r"^#\s*EPISODE:\s*(\S+)", text, re.M)
    if not ep:
        sys.exit("[script_desk] ERROR: no '# EPISODE: <id>' line")
    episode = ep.group(1)

    vocab = ""
    vm = re.search(r"^##\s*VOCABULARY\s*$(.*?)(?=^##\s*SCENE:|\Z)",
                   text, re.M | re.S)
    if vm:
        vocab = vm.group(1).strip()

    scenes = []
    for m in re.finditer(r"^##\s*SCENE:\s*(\S+)\s*$(.*?)(?=^##\s*SCENE:|\Z)",
                         text, re.M | re.S):
        body = m.group(2).strip()
        # Structural scene facts are SCRIPT metadata, parsed here and later
        # stamped over the LLM's intent — the translator gets no vote on
        # where/when a scene happens (2026-07-07: the 3B silently normalized
        # an unknown location into known vocabulary instead of reporting it).
        meta = {}
        lm = re.search(r"^-\s*location:\s*(\S+)", body, re.M)
        if lm:
            meta["location_tag"] = lm.group(1).strip("`")
        tm = re.search(r"^-\s*time:\s*(\S+)", body, re.M)
        if tm:
            meta["time_of_day"] = tm.group(1).strip("`")
        scenes.append((m.group(1), body, meta))
    if not scenes:
        sys.exit("[script_desk] ERROR: no '## SCENE: <id>' blocks")
    return episode, vocab, scenes


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = globmod.glob(os.path.join(
        os.getcwd(), ".venv/lib/python*/site-packages/imageio_ffmpeg/"
                     "binaries/ffmpeg-*"))
    return hits[0] if hits else None


def main():
    args = parse_args()
    text = open(args.script).read()
    episode, vocab, scenes = parse_script(text)
    edir = os.path.join("out", "production", episode)
    os.makedirs(edir, exist_ok=True)
    print(f"[script_desk] episode {episode}: {len(scenes)} scene(s)")

    # World snapshot — what the library looked like for this run
    snap = os.path.join(edir, "snapshot")
    os.makedirs(snap, exist_ok=True)
    for f in SNAPSHOT_FILES:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(snap, os.path.basename(f)))

    outcomes = {}
    for scene_id, body, meta in scenes:
        sdir = os.path.join(edir, "scenes", scene_id)
        os.makedirs(sdir, exist_ok=True)
        brief_path = os.path.join(sdir, "brief.md")
        with open(brief_path, "w") as f:
            f.write(f"# Approved scene brief — {scene_id} "
                    f"(episode {episode})\n\n")
            if vocab:
                f.write("## Controlled vocabulary (use exactly these tags)"
                        f"\n\n- scene_id: `{scene_id}`\n{vocab}\n\n")
            f.write(body + "\n")

        print(f"[script_desk] ── {scene_id} …")
        # 1. LLM translates the brief (beats/dialogue/shots)
        intent_path = os.path.join(sdir, "intent.json")
        gen = subprocess.run([VENV_PY, "tools/generate_intent.py",
                              "--brief", brief_path, "--out", intent_path],
                             capture_output=True, text=True, timeout=900,
                             stdin=subprocess.DEVNULL)
        if gen.returncode != 0:
            outcomes[scene_id] = ("FAILED", None)
            print(f"[script_desk]    FAILED (translation, exit "
                  f"{gen.returncode}); continuing")
            continue
        # 2. Deterministic stamp: script metadata overrides the translator
        intent = json.load(open(intent_path))
        intent["scene_id"] = scene_id
        for key, val in meta.items():
            intent[key] = val
        with open(intent_path, "w") as f:
            json.dump(intent, f, indent=2)
            f.write("\n")

        render_out = f"renders/reviews/{episode}_{scene_id}.mp4"
        cmd = [VENV_PY, "tools/run_pipeline.py", "--intent", intent_path,
               "--episode", episode]
        if args.no_render:
            cmd.append("--no-render")
        else:
            cmd += ["--render-out", render_out]
        run = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=7200, stdin=subprocess.DEVNULL)
        if run.returncode == 0:
            outcomes[scene_id] = ("DELIVERED", render_out
                                  if not args.no_render else None)
            print(f"[script_desk]    DELIVERED")
        elif run.returncode == EXIT_BLOCKED:
            outcomes[scene_id] = ("NEEDS_ASSETS", None)
            print(f"[script_desk]    BLOCKED — ticket written; continuing")
        else:
            outcomes[scene_id] = ("FAILED", None)
            tail = (run.stdout + run.stderr).strip().splitlines()[-6:]
            print(f"[script_desk]    FAILED (exit {run.returncode}); "
                  f"continuing\n      " + "\n      ".join(tail))

    # Episode assembly: slate card before each delivered scene, then a
    # re-encoded concat (re-encode because slates and renders come from
    # different encoder invocations).
    episode_cut = None
    delivered = [(sid, r) for sid, (st, r) in outcomes.items()
                 if st == "DELIVERED" and r]
    if delivered and not args.no_render:
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            font = "/System/Library/Fonts/Helvetica.ttc"
            parts = []
            for sid, r in delivered:
                slate = os.path.join(edir, "scenes", sid, "slate.mp4")
                text = f"{episode}\\n{sid}".replace(":", r"\:")
                subprocess.run(
                    [ffmpeg, "-y", "-f", "lavfi",
                     "-i", "color=c=0x101018:s=960x540:r=24:d=1.5",
                     "-vf", (f"drawtext=fontfile={font}:text='{text}':"
                             "fontcolor=0xD8D8E0:fontsize=42:"
                             "x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=18"),
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", slate],
                    check=True, capture_output=True)
                parts += [slate, r]
            lst = os.path.join(edir, "concat.txt")
            with open(lst, "w") as f:
                for p in parts:
                    f.write(f"file '{os.path.abspath(p)}'\n")
            episode_cut = f"renders/reviews/{episode}_episode.mp4"
            subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                            "-i", lst, "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "23",
                            episode_cut],
                           check=True, capture_output=True)
            print(f"[script_desk] episode cut (with slates) → {episode_cut}")

    # Production summary
    n = {"DELIVERED": 0, "NEEDS_ASSETS": 0, "FAILED": 0}
    for st, _ in outcomes.values():
        n[st] += 1
    summary = {"episode": episode, "script": args.script,
               "scenes": {sid: st for sid, (st, _r) in outcomes.items()},
               "delivered": n["DELIVERED"], "blocked": n["NEEDS_ASSETS"],
               "failed": n["FAILED"], "episode_cut": episode_cut}
    spath = os.path.join(edir, "production_summary.json")
    with open(spath, "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(f"[script_desk] SUMMARY: {n['DELIVERED']} delivered, "
          f"{n['NEEDS_ASSETS']} blocked (tickets), {n['FAILED']} failed"
          f" — {spath}")
    sys.exit(0 if n["FAILED"] == 0 else 1)


if __name__ == "__main__":
    main()
