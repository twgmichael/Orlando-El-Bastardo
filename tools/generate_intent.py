#!/usr/bin/env python3
"""
generate_intent.py — Local-LLM SceneIntent generation (Phase 5 wiring).

Feeds an approved episode brief to the local translator model via llama-cli
with JSON-schema-constrained decoding, and writes the resulting SceneIntent.
The LLM is a translator: it transcribes approved material into the intent
shape; it never invents content. Downstream, the deterministic resolver and
validator treat its output like any other intent.

Run from repo root:
  .venv/bin/python tools/generate_intent.py \
    --brief fixtures/bar_scene.brief.md \
    --out out/llm/intent_t0.json --temp 0.0 --seed 1
"""

import argparse
import json
import os
import subprocess
import sys

# llama-completion is the one-shot binary; llama-cli (even with -no-cnv on
# this build) drops into interactive conversation mode and never exits.
LLAMA_CLI = "llama-completion"
DEFAULT_MODEL = "models/qwen2.5-3b-instruct-q4_k_m.gguf"
SCHEMA_PATH = "schemas/sceneintent.schema.json"

SYSTEM = """You are a scene-intent translator for a deterministic 3D \
animation pipeline. You convert APPROVED episode briefs into SceneIntent \
JSON. Rules: transcribe dialogue lines VERBATIM in their given order with \
the correct speaker; use ONLY the controlled-vocabulary tags the brief \
provides; number beats and shots from 0 in story order; every shot_intent \
covers its beat via beat_orders; close_on shots require subject_actor_id. \
You never invent dialogue, actors, locations, or tags. Output only JSON."""


def parse_args():
    p = argparse.ArgumentParser(prog="generate_intent")
    p.add_argument("--brief", required=True)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--schema", default=SCHEMA_PATH)
    p.add_argument("--out", required=True)
    p.add_argument("--temp", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--n-predict", type=int, default=2048)
    return p.parse_args()


def build_prompt(brief_text):
    return (
        f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\nTranslate this approved brief into SceneIntent "
        f"JSON (schema_version \"1.0.0\"):\n\n{brief_text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def main():
    args = parse_args()
    for path in (args.brief, args.model, args.schema):
        if not os.path.isfile(path):
            print(f"[generate_intent] ERROR: not found: {path}", file=sys.stderr)
            sys.exit(2)

    schema = open(args.schema).read()
    prompt = build_prompt(open(args.brief).read())

    cmd = [
        LLAMA_CLI,
        "-m", args.model,
        "-p", prompt,
        "--json-schema", schema,
        "--temp", str(args.temp),
        "--seed", str(args.seed),
        "-n", str(args.n_predict),
        "-c", "4096",
        "--no-display-prompt",
    ]
    print(f"[generate_intent] {LLAMA_CLI} temp={args.temp} seed={args.seed}")
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                         stdin=subprocess.DEVNULL)
    if run.returncode != 0:
        print(f"[generate_intent] ERROR: llama-cli exit {run.returncode}:\n"
              f"{run.stderr[-2000:]}", file=sys.stderr)
        sys.exit(2)

    raw = run.stdout.strip()
    # Grammar-constrained decode should yield pure JSON; trim anything after
    # the closing brace defensively (end-of-generation markers).
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        print(f"[generate_intent] ERROR: no JSON object in output:\n{raw[:500]}",
              file=sys.stderr)
        sys.exit(3)
    try:
        intent = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        print(f"[generate_intent] ERROR: JSON parse failed: {exc}", file=sys.stderr)
        sys.exit(3)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(intent, f, indent=2)
        f.write("\n")
    print(f"[generate_intent] Wrote {args.out}")


if __name__ == "__main__":
    main()
