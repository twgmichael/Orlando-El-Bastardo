#!/usr/bin/env python3
"""
producer.py — PRODUCER-PLAN P3: the production run. Screenplay in,
episode out, no prompting.

    .venv/bin/python tools/producer.py --script scripts/pilot/pilot.md

Per run:
  1. Deterministic screenplay parse (tools/screenplay.py) — sluglines,
     shot headings, dialogue, arrivals, audio sweep. No LLM in structure.
  2. Vocabulary sweep against the library (resolver map, camera grammar,
     stand-in registry data/standins.json). Location stand-ins render the
     scene NOW and still ticket the real asset. Unknown locations/roles
     BLOCK the scene with a NEEDED ticket. Audio directions and
     LLM-flagged set dressing become non-blocking vocab tickets.
  3. The local producer LLM reviews each scene (constrained by
     schemas/scenereview.schema.json): beat descriptions + a mentioned-
     items inventory. Flagging only — structure and dialogue are already
     fixed. On LLM failure the run continues with deterministic fallbacks.
  4. Scene intents are assembled deterministically, schema-validated, and
     run through the per-scene front door (run_pipeline.py --intent) with
     its own gates. DELIVERED / NEEDS_ASSETS / FAILED per scene; the run
     never halts for one scene's failure.
  5. Episode cut with slates + production_report.json/.md.

Exit codes: 0 = no FAILED scenes (blocked scenes allowed); 1 = failures;
2 = cannot run (bad input).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screenplay  # noqa: E402
import tickets     # noqa: E402
from script_desk import find_ffmpeg  # noqa: E402

VENV_PY = ".venv/bin/python"
LLAMA = "llama-completion"
MODEL = "llm/qwen2.5-3b-instruct-q4_k_m.gguf"
REVIEW_SCHEMA = "schemas/scenereview.schema.json"
INTENT_SCHEMA = "schemas/sceneintent.schema.json"
SNAPSHOT_FILES = ["oeb.config.json", "data/resolver_map.json",
                  "data/camera_grammar.json", "data/standins.json"]
EXIT_BLOCKED = 4

REVIEW_SYSTEM = (
    "You are the producer's script reviewer for a deterministic 3D "
    "animation pipeline. You condense approved screenplay sections into "
    "one-sentence beat descriptions (order = section number), and you "
    "inventory every physical item, piece of set dressing, sound source, "
    "or background character the text mentions. You never invent content. "
    "Output only JSON.")


def parse_args():
    p = argparse.ArgumentParser(prog="producer")
    p.add_argument("--script", required=True)
    p.add_argument("--episode", default=None,
                   help="Episode id (default: script's folder name)")
    p.add_argument("--targets", default="blender")
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--temp", default="0.0")
    p.add_argument("--seed", default="1")
    return p.parse_args()


def llm_review(scene_id, scene, temp, seed):
    """Constrained review call. Returns (review_dict|None, note)."""
    parts = [f"Review scene {scene_id} ({scene['slugline']}). Give one "
             f"beat description per numbered section and the "
             f"mentioned_items inventory.\n"]
    for j, sec in enumerate(scene["sections"]):
        parts.append(f"SECTION {j}:")
        if sec["heading"]:
            parts.append(f"(shot: {sec['heading']})")
        parts.extend(sec["action"])
        for name, text in sec["dialogue"]:
            parts.append(f'{name}: "{text}"')
        parts.append("")
    prompt = (f"<|im_start|>system\n{REVIEW_SYSTEM}<|im_end|>\n"
              f"<|im_start|>user\n" + "\n".join(parts) +
              "<|im_end|>\n<|im_start|>assistant\n")
    cmd = [LLAMA, "-m", MODEL, "-p", prompt,
           "--json-schema", open(REVIEW_SCHEMA).read(),
           "--temp", temp, "--seed", seed,
           "-n", "1024", "-c", "4096", "--no-display-prompt"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=600, stdin=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"llm review failed: {exc}"
    if run.returncode != 0:
        return None, f"llm review exit {run.returncode}"
    raw = run.stdout.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None, "llm review: no JSON in output"
    try:
        return json.loads(raw[start:end + 1]), "ok"
    except json.JSONDecodeError as exc:
        return None, f"llm review: bad JSON ({exc})"


def fallback_descriptions(scene):
    """Deterministic beat descriptions: first sentence of each section."""
    out = {}
    for j, sec in enumerate(scene["sections"]):
        text = " ".join(sec["action"]) or " ".join(
            t for _n, t in sec["dialogue"])
        first = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text else \
            f"Section {j}."
        out[j] = first[:200]
    return out


def names_in(text, cast_names):
    found = []
    for name in cast_names:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            found.append(name)
    return found


def build_intent(scene_id, scene, cast, location_tag, arrivals,
                 departures, descriptions):
    """Deterministic SceneIntent assembly from parsed structure."""
    scene_text = " ".join(
        p for sec in scene["sections"] for p in sec["action"])
    speakers = {n.lower() for sec in scene["sections"]
                for n, _t in sec["dialogue"]}
    present = [n for n in cast
               if n in speakers or names_in(scene_text, [n])]

    actors = []
    for name in present:
        actor = {"actor_id": name, "role_tag": cast[name]}
        if name in arrivals:
            actor["arrives"] = True
        if name in departures:
            actor["departs"] = True
        actors.append(actor)

    beats = []
    shot_intents = []
    for j, sec in enumerate(scene["sections"]):
        sec_text = " ".join(sec["action"])
        actor_ids = sorted(set(
            names_in(sec_text, present) +
            [n.lower() for n, _t in sec["dialogue"] if n.lower() in cast]))
        beat = {"order": j, "description": descriptions.get(
            j, f"Section {j}.")}
        if actor_ids:
            beat["actor_ids"] = actor_ids
        if sec["dialogue"]:
            beat["dialogue"] = [{"actor_id": n.lower(), "text": t}
                                for n, t in sec["dialogue"]]
        beats.append(beat)

        framing = sec["framing"]
        subject = (sec["subject_raw"] or "").lower() or None
        si = {"order": j, "beat_orders": [j]}
        if framing in ("close_on", "medium_on"):
            if subject in cast:
                si["framing"] = framing
                si["subject_actor_id"] = subject
            else:
                si["framing"] = "establishing"   # fallback, noted upstream
        else:
            si["framing"] = framing or "establishing"
        shot_intents.append(si)

    return {
        "schema_version": "1.0.0",
        "scene_id": scene_id,
        "location_tag": location_tag,
        "time_of_day": scene["time_of_day"],
        "actors": actors,
        "beats": beats,
        "shot_intents": shot_intents,
    }


def episode_cut(episode, delivered, edir):
    """Slate + concat the delivered renders (script_desk pattern)."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg or not delivered:
        return None
    font = "/System/Library/Fonts/Helvetica.ttc"
    parts = []
    for sid, render in delivered:
        slate = os.path.join(edir, "scenes", sid, "slate.mp4")
        os.makedirs(os.path.dirname(slate), exist_ok=True)
        text = f"{episode}\\n{sid}".replace(":", r"\:")
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi",
             "-i", "color=c=0x101018:s=960x540:r=24:d=1.5",
             "-vf", (f"drawtext=fontfile={font}:text='{text}':"
                     "fontcolor=0xD8D8E0:fontsize=42:"
                     "x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=18"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", slate],
            check=True, capture_output=True)
        parts += [slate, render]
    lst = os.path.join(edir, "concat.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cut = f"renders/reviews/{episode}_episode.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", cut], check=True, capture_output=True)
    return cut


def main():
    args = parse_args()
    if not os.path.isfile(args.script):
        sys.exit(f"[producer] ERROR: script not found: {args.script}")
    episode = args.episode or os.path.basename(
        os.path.dirname(os.path.abspath(args.script)))

    vocab = json.load(open("data/standins.json"))
    rmap = json.load(open("data/resolver_map.json"))
    cast = vocab.get("cast", {})
    import jsonschema
    intent_schema = json.load(open(INTENT_SCHEMA))

    doc = screenplay.parse(open(args.script).read(), vocab)
    if not doc["scenes"]:
        sys.exit("[producer] ERROR: no scenes (no sluglines?) in script")
    print(f"[producer] episode {episode}: {len(doc['scenes'])} scene(s), "
          f"acts: {doc['acts'] or ['-']}")

    edir = os.path.join("out", "production", episode)
    snap = os.path.join(edir, "snapshot")
    os.makedirs(snap, exist_ok=True)
    for f in SNAPSHOT_FILES:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(snap, os.path.basename(f)))

    known_items = {k.lower() for k in vocab.get("known_items", [])} \
        | {k.lower() for k in cast} \
        | {w.lower() for k in vocab.get("location_standins", {})
           for w in k.split("_")}
    audio_kw = {k.lower() for k in vocab.get("audio_keywords", [])}

    outcomes = {}
    vocab_findings = {}
    for idx, scene in enumerate(doc["scenes"]):
        scene_id = f"{episode}_sc{idx + 1:02d}"
        sdir = os.path.join(edir, "scenes", scene_id)
        os.makedirs(sdir, exist_ok=True)
        print(f"[producer] ── {scene_id}: {scene['slugline']}")

        blocking = []       # ticket entries that stop this scene
        notes = []          # non-blocking ticket entries (vocab backlog)
        standins_used = []

        # Location: direct, stand-in, or blocked
        loc = scene["location_tag"]
        if loc in rmap.get("locations", {}):
            location_tag = loc
        else:
            standin = vocab.get("location_standins", {}).get(loc)
            if standin and standin in rmap.get("locations", {}):
                location_tag = standin
                standins_used.append({"kind": "location", "script": loc,
                                      "stand_in": standin})
                notes.append({
                    "kind": "location", "name": loc,
                    "source": "producer stand-in",
                    "detail": f"scene rendered with stand-in '{standin}'; "
                              f"the real '{loc}' set does not exist yet"})
            else:
                location_tag = None
                blocking.append({
                    "kind": "location", "name": loc,
                    "source": "producer vocabulary sweep",
                    "detail": f"location '{loc}' is not in the resolver "
                              f"map and has no stand-in"})

        # Cast: unknown speakers block (no improvised casting)
        for sec in scene["sections"]:
            for name, _t in sec["dialogue"]:
                if name.lower() not in cast:
                    blocking.append({
                        "kind": "role", "name": name.lower(),
                        "source": "producer vocabulary sweep",
                        "detail": f"speaker '{name}' has no cast mapping "
                                  f"in data/standins.json"})

        # Shot headings without a mapped framing → fallback + note
        for sec in scene["sections"]:
            if sec["heading"] and sec["framing"] is None:
                notes.append({
                    "kind": "framing", "name": sec["heading"],
                    "source": "producer vocabulary sweep",
                    "detail": "unmapped shot heading; rendered as "
                              "'establishing'"})
            subj = (sec["subject_raw"] or "").lower()
            if sec["framing"] in ("close_on", "medium_on") \
                    and subj not in cast:
                notes.append({
                    "kind": "framing", "name": sec["heading"] or "?",
                    "source": "producer vocabulary sweep",
                    "detail": f"shot subject '{sec['subject_raw']}' is not "
                              f"in the cast; rendered as 'establishing'"})

        # Audio directions → tickets (v0 renders are silent)
        for line in screenplay.audio_directions(scene, audio_kw):
            notes.append({"kind": "audio", "name": line[:70],
                          "source": "producer audio sweep",
                          "detail": f"audio direction deferred (v0 silent "
                                    f"renders): {line}"})

        # Producer LLM review: beat descriptions + item inventory
        review, review_note = llm_review(scene_id, scene,
                                         args.temp, args.seed)
        descriptions = fallback_descriptions(scene)
        unknown_items = []
        if review:
            for b in review.get("beats", []):
                if isinstance(b.get("order"), int) and b.get("description"):
                    descriptions[b["order"]] = b["description"]
            for item in review.get("mentioned_items", []):
                norm = item.strip().lower()
                words = set(re.split(r"[^a-z0-9]+", norm)) - {""}
                if not words or words & known_items or words & audio_kw:
                    continue
                unknown_items.append(item.strip())
        for item in sorted(set(unknown_items)):
            notes.append({"kind": "prop", "name": item,
                          "source": "producer llm review",
                          "detail": f"script mentions '{item}'; nothing in "
                                    f"the library maps to it"})
        print(f"[producer]    review: {review_note}; "
              f"{len(unknown_items)} unknown item(s), "
              f"{len(notes)} vocab note(s), {len(blocking)} blocker(s)")

        vocab_findings[scene_id] = {
            "blocking": blocking, "notes": notes,
            "standins_used": standins_used, "llm_review": review_note,
            "arrivals": [], "departures": [], "review_items": review.get(
                "mentioned_items", []) if review else []}

        if notes:
            tickets.write_ticket(episode, f"{scene_id}_vocab", notes,
                                 script_ref=args.script)
        if blocking:
            tpath = tickets.write_ticket(episode, scene_id, blocking,
                                         script_ref=args.script)
            tickets.update_report(episode, scene_id, "NEEDS_ASSETS",
                                  ticket=os.path.basename(tpath))
            outcomes[scene_id] = ("NEEDS_ASSETS", None)
            print(f"[producer]    BLOCKED — {len(blocking)} missing; "
                  f"ticket written; continuing")
            continue

        arrivals = screenplay.detect_arrivals(scene, list(cast))
        departures = screenplay.detect_departures(scene, list(cast))
        vocab_findings[scene_id]["arrivals"] = sorted(arrivals)
        vocab_findings[scene_id]["departures"] = sorted(departures)
        intent = build_intent(scene_id, scene, cast, location_tag,
                              arrivals, departures, descriptions)
        try:
            jsonschema.Draft202012Validator(intent_schema).validate(intent)
        except jsonschema.ValidationError as exc:
            outcomes[scene_id] = ("FAILED", None)
            print(f"[producer]    FAILED — assembled intent invalid: "
                  f"{exc.message}; continuing")
            tickets.update_report(episode, scene_id, "FAILED",
                                  stage="producer-intent")
            continue
        intent_path = os.path.join(sdir, "intent.json")
        with open(intent_path, "w") as f:
            json.dump(intent, f, indent=2)
            f.write("\n")

        render_out = f"renders/reviews/{episode}_{scene_id}.mp4"
        cmd = [VENV_PY, "tools/run_pipeline.py", "--intent", intent_path,
               "--episode", episode, "--targets", args.targets]
        if args.no_render:
            cmd.append("--no-render")
        else:
            cmd += ["--render-out", render_out]
        run = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=7200, stdin=subprocess.DEVNULL)
        if run.returncode == 0:
            outcomes[scene_id] = (
                "DELIVERED", None if args.no_render else render_out)
            print("[producer]    DELIVERED")
        elif run.returncode == EXIT_BLOCKED:
            outcomes[scene_id] = ("NEEDS_ASSETS", None)
            print("[producer]    BLOCKED — pipeline ticket written; "
                  "continuing")
        else:
            outcomes[scene_id] = ("FAILED", None)
            tail = (run.stdout + run.stderr).strip().splitlines()[-6:]
            print(f"[producer]    FAILED (exit {run.returncode}); "
                  f"continuing\n      " + "\n      ".join(tail))

    delivered = [(sid, r) for sid, (st, r) in outcomes.items()
                 if st == "DELIVERED" and r]
    cut = None
    if delivered and not args.no_render:
        cut = episode_cut(episode, delivered, edir)
        if cut:
            print(f"[producer] episode cut → {cut}")

    n = {"DELIVERED": 0, "NEEDS_ASSETS": 0, "FAILED": 0}
    for st, _ in outcomes.values():
        n[st] += 1
    report = {
        "episode": episode, "script": args.script,
        "scenes": {sid: {"status": st, "render": r}
                   for sid, (st, r) in outcomes.items()},
        "vocabulary": vocab_findings,
        "delivered": n["DELIVERED"], "blocked": n["NEEDS_ASSETS"],
        "failed": n["FAILED"], "episode_cut": cut,
    }
    rpath = os.path.join(edir, "production_report.json")
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    md = [f"# Production report — {episode}", "",
          f"Script: `{args.script}`", ""]
    for sid, (st, r) in outcomes.items():
        md.append(f"## {sid} — {st}")
        if r:
            md.append(f"- render: `{r}`")
        vf = vocab_findings.get(sid, {})
        for s in vf.get("standins_used", []):
            md.append(f"- stand-in: `{s['script']}` → `{s['stand_in']}`")
        for b in vf.get("blocking", []):
            md.append(f"- **BLOCKED on {b['kind']}**: `{b['name']}`")
        for note in vf.get("notes", []):
            md.append(f"- needed ({note['kind']}): {note['name']}")
        md.append("")
    if cut:
        md.append(f"Episode cut: `{cut}`")
    with open(os.path.join(edir, "production_report.md"), "w") as f:
        f.write("\n".join(md) + "\n")

    print(f"[producer] SUMMARY: {n['DELIVERED']} delivered, "
          f"{n['NEEDS_ASSETS']} blocked, {n['FAILED']} failed — {rpath}")
    sys.exit(0 if n["FAILED"] == 0 else 1)


if __name__ == "__main__":
    main()
