#!/usr/bin/env python3
"""
vet_translator.py — Phase 5 vetting of the local translator LLM.

Runs the SceneIntent generation N times (configurable temp/seed matrix),
pushes each output through the deterministic pipeline (schema validation →
resolver → validator), checks dialogue fidelity against the approved brief,
and prints a scorecard. The translator passes vetting only if every gate
passes on the deterministic config (temp 0) and a majority of sampled
configs.

Run from repo root:
  .venv/bin/python tools/vet_translator.py \
    --brief fixtures/bar_scene.brief.md \
    --expect fixtures/bar_scene.sceneintent.json \
    --runs t0:0.0:1 t7a:0.7:1 t7b:0.7:2 t7c:0.7:3
"""

import argparse
import json
import os
import subprocess
import sys

VENV_PY = ".venv/bin/python"


def parse_args():
    p = argparse.ArgumentParser(prog="vet_translator")
    p.add_argument("--brief", required=True)
    p.add_argument("--expect", required=True,
                   help="Reference intent whose beats/dialogue define fidelity")
    p.add_argument("--runs", nargs="+", default=["t0:0.0:1"],
                   help="tag:temp:seed triples")
    p.add_argument("--out-dir", default="out/llm")
    p.add_argument("--skip-generate", action="store_true",
                   help="Score existing out-dir intents instead of generating")
    return p.parse_args()


def expected_lines(expect_path):
    ref = json.load(open(expect_path))
    return [(l["actor_id"], l["text"])
            for b in sorted(ref["beats"], key=lambda b: b["order"])
            for l in b.get("dialogue", [])]


def run_step(cmd, timeout=1800):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-800:]


def main():
    args = parse_args()
    want = expected_lines(args.expect)
    os.makedirs(args.out_dir, exist_ok=True)
    results = []

    for spec in args.runs:
        tag, temp, seed = spec.split(":")
        intent_path = f"{args.out_dir}/intent_{tag}.json"
        row = {"tag": tag, "temp": temp, "seed": seed, "generate": None,
               "schema": None, "resolve": None, "validate": None,
               "dialogue": None, "notes": ""}

        if not args.skip_generate:
            code, _out = run_step([VENV_PY, "tools/generate_intent.py",
                                   "--brief", args.brief, "--out", intent_path,
                                   "--temp", temp, "--seed", seed])
            row["generate"] = code == 0
            if code != 0:
                row["notes"] = "generation failed/timeout"
                results.append(row)
                continue
        else:
            row["generate"] = os.path.isfile(intent_path)
            if not row["generate"]:
                row["notes"] = "missing intent file"
                results.append(row)
                continue

        code, out = run_step([VENV_PY, "-c",
            "import json,sys,jsonschema;"
            "s=json.load(open('schemas/sceneintent.schema.json'));"
            f"d=json.load(open('{intent_path}'));"
            "jsonschema.Draft202012Validator(s).validate(d)"])
        row["schema"] = code == 0
        if code != 0:
            row["notes"] = "schema: " + out.splitlines()[-1][:120] if out else "schema fail"
            results.append(row)
            continue

        spec_path = f"{args.out_dir}/spec_{tag}.json"
        code, out = run_step([VENV_PY, "tools/resolve_intent.py",
                              "--intent", intent_path, "--out", spec_path])
        row["resolve"] = code == 0
        if code != 0:
            row["notes"] = "resolve: " + (out.splitlines()[-1][:120] if out else "fail")
            results.append(row)
            continue

        code, out = run_step([VENV_PY, "tools/validate_spec.py",
                              "--spec", spec_path,
                              "--out", f"{args.out_dir}/report_{tag}.json"])
        row["validate"] = code == 0
        if code != 0:
            row["notes"] = "validate: " + (out.splitlines()[-1][:120] if out else "fail")

        # Fidelity is judged on the RESOLVED SPEC, not the intent's beats:
        # a beat that no shot covers silently drops its lines from the show
        # (found 2026-07-06 when optional beat_orders was omitted by the LLM).
        spec = json.load(open(spec_path))
        got = [(c["actor_id"], c["text"])
               for sh in sorted(spec["shots"], key=lambda s: s["order"])
               for c in sh["cues"] if c["type"] == "dialogue"]
        row["dialogue"] = got == want
        if not row["dialogue"] and not row["notes"]:
            row["notes"] = f"spec dialogue mismatch: {len(got)} lines vs {len(want)} expected"
        results.append(row)

    print("\n=== TRANSLATOR VETTING SCORECARD ===")
    cols = ["tag", "temp", "seed", "generate", "schema", "resolve", "validate", "dialogue"]
    print(" | ".join(c.ljust(8) for c in cols))
    for r in results:
        print(" | ".join(str(r[c]).ljust(8) for c in cols) +
              ("  " + r["notes"] if r["notes"] else ""))

    def ok(r):
        return all(r[k] for k in ("generate", "schema", "resolve", "validate", "dialogue"))

    t0 = [r for r in results if r["temp"] in ("0", "0.0")]
    sampled = [r for r in results if r not in t0]
    t0_pass = bool(t0) and all(ok(r) for r in t0)
    sampled_pass = (not sampled) or (sum(ok(r) for r in sampled) * 2 > len(sampled))
    verdict = "PASS" if (t0_pass and sampled_pass) else "FAIL"
    print(f"\nVERDICT: {verdict} (temp-0 gate: {'pass' if t0_pass else 'FAIL'}; "
          f"sampled majority: {'pass' if sampled_pass else 'FAIL'})")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
