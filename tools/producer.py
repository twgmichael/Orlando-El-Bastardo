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
from script_desk import find_ffmpeg, find_slate_font, slate_drawtext  # noqa: E402
from producer_studio_chat_client import build_scene_via_studio_chat  # noqa: E402
import placeholder_blueprint  # noqa: E402
from screenplay_entity_resolution import extract_entity_candidates  # noqa: E402

CONFIG_PATH = "oeb.config.json"
RESOLVER_MAP_PATH = "data/resolver_map.json"
STANDINS_PATH = "data/standins.json"
PLACEHOLDER_ASSETS_ROOT = "assets/placeholders"

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
    p.add_argument("--publish", action="store_true",
                   help="Upload the episode cut to YouTube (unlisted) per "
                        "docs/planning/PUBLISHING-PLAN.md. Off by default; "
                        "a publish failure never fails the run.")
    p.add_argument("--scenes", default=None,
                   help="Comma list of scene numbers to run (testing aid); "
                        "others are skipped entirely.")
    p.add_argument("--studio-chat-fallback", action="store_true",
                   help="docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md "
                        "section 4/7: when the deterministic pipeline blocks "
                        "a scene, fall through to Producer-as-Studio-Chat-"
                        "client for a rough draft instead of leaving it as a "
                        "bare NEEDS_ASSETS ticket. Off by default -- opt in "
                        "explicitly; requires OEB_HARNESS_URL/API_ADMIN_TOKEN.")
    p.add_argument("--primitive-fallback", action="store_true",
                   help="docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md "
                        "section 7: when producer's own vocabulary sweep "
                        "blocks a scene on a missing location or role, "
                        "register a crude primitive placeholder (deterministic, "
                        "offline -- no live harness needed, unlike "
                        "--studio-chat-fallback) and keep going instead of "
                        "leaving the scene NEEDS_ASSETS. Off by default; a "
                        "placeholder-generation failure never fails the run, "
                        "the scene just stays NEEDS_ASSETS as it does today.")
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


def scene_action_text(scene):
    return " ".join(p for sec in scene["sections"] for p in sec["action"])


def present_actors(scene, cast):
    scene_text = scene_action_text(scene)
    speakers = {n.lower() for sec in scene["sections"]
                for n, _t in sec["dialogue"]}
    return [n for n in cast if n in speakers or names_in(scene_text, [n])]


def build_intent(scene_id, scene, cast, location_tag, arrivals,
                 departures, descriptions):
    """Deterministic SceneIntent assembly from parsed structure."""
    present = present_actors(scene, cast)
    # SceneIntent's actor_id must match ^[a-z][a-z0-9_]*$ -- a raw
    # dialogue-cue speaker name can contain a space ("SHIP AI"), so the
    # id used everywhere below is a slug, not the cast key itself.
    slug = {name: _role_tag_for(name) for name in present}

    actors = []
    for name in present:
        actor = {"actor_id": slug[name], "role_tag": cast[name]}
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
            [slug[n] for n in names_in(sec_text, present)] +
            [slug[n.lower()] for n, _t in sec["dialogue"] if n.lower() in cast]))
        beat = {"order": j, "description": descriptions.get(
            j, f"Section {j}.")}
        if actor_ids:
            beat["actor_ids"] = actor_ids
        if sec["dialogue"]:
            beat["dialogue"] = [{"actor_id": slug.get(n.lower(), _role_tag_for(n)), "text": t}
                                for n, t in sec["dialogue"]]
        beats.append(beat)

        framing = sec["framing"]
        subject = (sec["subject_raw"] or "").lower() or None
        si = {"order": j, "beat_orders": [j]}
        if framing in ("close_on", "medium_on"):
            if subject in cast:
                si["framing"] = framing
                si["subject_actor_id"] = slug[subject]
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
    font = find_slate_font()
    parts = []
    for sid, render in delivered:
        slate = os.path.join(edir, "scenes", sid, "slate.mp4")
        os.makedirs(os.path.dirname(slate), exist_ok=True)
        text = f"{episode}\\n{sid}".replace(":", r"\:")
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi",
             "-i", "color=c=0x101018:s=960x540:r=24:d=1.5",
             "-vf", slate_drawtext(font, text),
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


def scene_creative_request(scene_id, scene):
    """Render a scene's own screenplay text (slugline + action + dialogue)
    as a single creative_request string for the Studio Chat fallback --
    the teleplay's own language, not a paraphrase or an invented summary.
    See docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 4's
    "no story invention" guardrail: Producer works within what the
    teleplay actually says.
    """
    lines = [scene["slugline"]]
    for sec in scene["sections"]:
        if sec["heading"]:
            lines.append(f"({sec['heading']})")
        lines.extend(sec["action"])
        for name, text in sec["dialogue"]:
            lines.append(f'{name}: "{text}"')
    return "\n".join(line for line in lines if line)


def _role_tag_for(speaker_name):
    return re.sub(r"[^a-z0-9]+", "_", speaker_name.strip().lower()).strip("_") or "actor"


def primitive_fallback(blocking, rmap, cast, location_tag):
    """docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 7: for
    each missing location/role this scene's vocabulary sweep found,
    register a crude primitive placeholder -- deterministically and
    offline (no live harness needed, unlike --studio-chat-fallback).
    Mutates the real oeb.config.json / data/resolver_map.json /
    data/standins.json on disk (tagged "placeholder": true -- the same
    registry every other tool already reads, per section 7's "no
    separate placeholder-specific store" decision, not a parallel one)
    AND the in-memory *rmap*/*cast* dicts this same run already holds,
    so the scene can immediately continue through the deterministic
    pipeline using what was just registered, without re-reading files.

    Returns `(still_blocking, resolved_location_tag)` -- entries still
    genuinely unresolved (a placeholder build that itself failed; a
    role blocker with no location, placeholder or real, to anchor
    marks against), and the location_tag the caller should now use
    (unchanged if there was no location blocker, the new placeholder's
    tag otherwise). A failure here is never fatal to the run -- an
    unresolved entry just leaves the scene NEEDS_ASSETS, same as
    without this flag.
    """
    still_blocking = []
    location_set_id = None
    resolved_location_tag = location_tag

    for item in blocking:
        if item["kind"] != "location":
            continue
        try:
            canonical_id = placeholder_blueprint.slugify_placeholder_id(item["name"], "location")
            bp = placeholder_blueprint.default_placeholder_blueprint(
                canonical_id, "location", item["name"], with_location_marks=True)
            placeholder_blueprint.build_placeholder_glb(
                bp, f"{PLACEHOLDER_ASSETS_ROOT}/{canonical_id}.glb",
                f"out/blueprint_builds/{canonical_id}.blend",
                f"out/blueprint_builds/{canonical_id}.manifest.json")
            placeholder_blueprint.register_placeholder_asset(
                CONFIG_PATH, canonical_id, "location", f"placeholders/{canonical_id}.glb")
            placeholder_blueprint.register_placeholder_location(RESOLVER_MAP_PATH, item["name"], canonical_id)
            rmap["locations"][item["name"]] = json.load(open(RESOLVER_MAP_PATH))["locations"][item["name"]]
            location_set_id = canonical_id
            resolved_location_tag = item["name"]
            print(f"[producer]    primitive-fallback: registered placeholder location "
                  f"'{item['name']}' -> {canonical_id}")
        except Exception as exc:  # noqa: BLE001 -- must not crash the run
            print(f"[producer]    primitive-fallback: FAILED building location "
                  f"'{item['name']}' ({exc}); still blocked")
            still_blocking.append(item)

    if location_set_id is None and location_tag is not None:
        # No location blocker this scene -- if a role blocker is also
        # present, anchor its marks to this scene's own already-
        # resolved location (real, or an existing stand-in).
        location_set_id = rmap.get("locations", {}).get(location_tag, {}).get("set_id")

    for item in blocking:
        if item["kind"] != "role":
            continue
        if location_set_id is None:
            print(f"[producer]    primitive-fallback: no location to anchor role "
                  f"'{item['name']}' marks against; still blocked")
            still_blocking.append(item)
            continue
        try:
            role_tag = _role_tag_for(item["name"])
            canonical_id = placeholder_blueprint.slugify_placeholder_id(item["name"], "character")
            bp = placeholder_blueprint.default_placeholder_blueprint(canonical_id, "character", item["name"])
            placeholder_blueprint.build_placeholder_glb(
                bp, f"{PLACEHOLDER_ASSETS_ROOT}/{canonical_id}.glb",
                f"out/blueprint_builds/{canonical_id}.blend",
                f"out/blueprint_builds/{canonical_id}.manifest.json")
            placeholder_blueprint.register_placeholder_asset(
                CONFIG_PATH, canonical_id, "character", f"placeholders/{canonical_id}.glb")
            placeholder_blueprint.register_placeholder_role(
                RESOLVER_MAP_PATH, role_tag, canonical_id, resolved_location_tag, location_set_id)
            placeholder_blueprint.register_placeholder_cast(STANDINS_PATH, item["name"], role_tag)
            rmap["roles"][role_tag] = json.load(open(RESOLVER_MAP_PATH))["roles"][role_tag]
            cast[item["name"]] = role_tag
            print(f"[producer]    primitive-fallback: registered placeholder role "
                  f"'{item['name']}' -> {canonical_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"[producer]    primitive-fallback: FAILED building role "
                  f"'{item['name']}' ({exc}); still blocked")
            still_blocking.append(item)

    for item in blocking:
        if item["kind"] != "role_location":
            continue
        if location_set_id is None:
            print(f"[producer]    primitive-fallback: no location to anchor "
                  f"role '{item['name']}' marks against; still blocked")
            still_blocking.append(item)
            continue
        try:
            # Already cast and already has a built asset -- just extend the
            # existing role with a spawn_mark for this new location, no
            # rebuild/re-registration needed.
            placeholder_blueprint.register_placeholder_role(
                RESOLVER_MAP_PATH, item["role_tag"], item["character_id"],
                resolved_location_tag, location_set_id)
            rmap["roles"][item["role_tag"]] = json.load(
                open(RESOLVER_MAP_PATH))["roles"][item["role_tag"]]
            print(f"[producer]    primitive-fallback: extended placeholder "
                  f"role '{item['role_tag']}' to location "
                  f"'{resolved_location_tag}'")
        except Exception as exc:  # noqa: BLE001
            print(f"[producer]    primitive-fallback: FAILED extending role "
                  f"'{item['role_tag']}' ({exc}); still blocked")
            still_blocking.append(item)

    return still_blocking, resolved_location_tag


def register_vehicle_placeholder(scene, cast, rmap, location_tag):
    """docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 7 item
    7's second known blocker: a pure ship/vehicle shot with no on-camera
    named character still needs `SceneIntent.actors` to be non-empty.
    Rather than loosen that schema requirement, give the scene an
    honest subject: extract candidate proper-noun phrases from the
    scene's own action text (tools/screenplay_entity_resolution.py --
    already built and tested for exactly this "what does this
    capitalized phrase refer to" extraction, section 6) and register
    the first one as a placeholder *vehicle* actor -- reusing
    primitive_fallback's same role-registration path, just with
    kind="vehicle" so the crude primitive is ship-shaped
    (tools/placeholder_blueprint.py's _DEFAULT_PRIMITIVE_BY_KIND)
    instead of person-shaped.

    Returns the registered speaker-name key (already added to *cast*
    in place) or None if no candidate phrase was found at all -- never
    fatal, the scene just stays FAILED on the empty-actors schema error
    exactly as it did before this existed.
    """
    text = scene_action_text(scene)
    candidates = extract_entity_candidates(text)
    candidates = [c for c in candidates if c.lower() not in cast]
    if not candidates:
        return None
    # Prefer the most-repeated candidate, not just the first-seen one:
    # a genuine recurring subject (e.g. a ship named throughout the
    # scene) gets mentioned more than once; a one-off capitalized
    # scene-opener word ("Black.", describing the void before the
    # stars appear) doesn't. Confirmed live 2026-08-09 -- first-seen
    # alone picked "Black" over "JourneyBlaster" for exactly this scene.
    lowered = text.lower()
    candidates.sort(key=lambda c: lowered.count(c.lower()), reverse=True)

    location_set_id = rmap.get("locations", {}).get(location_tag or "", {}).get("set_id")
    if location_set_id is None:
        print("[producer]    primitive-fallback: no location to anchor vehicle "
              "placeholder marks against; skipping")
        return None

    subject = candidates[0]
    speaker_name = subject.lower()
    try:
        role_tag = _role_tag_for(subject)
        canonical_id = placeholder_blueprint.slugify_placeholder_id(subject, "vehicle")
        bp = placeholder_blueprint.default_placeholder_blueprint(canonical_id, "vehicle", subject)
        placeholder_blueprint.build_placeholder_glb(
            bp, f"{PLACEHOLDER_ASSETS_ROOT}/{canonical_id}.glb",
            f"out/blueprint_builds/{canonical_id}.blend",
            f"out/blueprint_builds/{canonical_id}.manifest.json")
        placeholder_blueprint.register_placeholder_asset(
            CONFIG_PATH, canonical_id, "vehicle", f"placeholders/{canonical_id}.glb")
        placeholder_blueprint.register_placeholder_role(
            RESOLVER_MAP_PATH, role_tag, canonical_id, location_tag, location_set_id)
        placeholder_blueprint.register_placeholder_cast(STANDINS_PATH, speaker_name, role_tag)
        rmap["roles"][role_tag] = json.load(open(RESOLVER_MAP_PATH))["roles"][role_tag]
        cast[speaker_name] = role_tag
        print(f"[producer]    primitive-fallback: registered placeholder vehicle "
              f"'{subject}' -> {canonical_id} (subject for an otherwise actor-less shot)")
        return speaker_name
    except Exception as exc:  # noqa: BLE001 -- must not crash the run
        print(f"[producer]    primitive-fallback: FAILED building vehicle "
              f"'{subject}' ({exc}); scene stays as-is")
        return None


def studio_chat_rough_draft(scene_id, scene, episode, args):
    """docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 4/7:
    Producer as a literal Studio Chat client, used here as the fallback
    when the deterministic pipeline blocks a scene. Never fatal to the
    run -- any failure (harness unreachable, unresolved even after the
    bounded auto-clarification retry) is caught and reported as still
    NEEDS_ASSETS, same as today's behavior without this flag.
    """
    harness_url = os.environ.get("OEB_HARNESS_URL")
    admin_token = os.environ.get("API_ADMIN_TOKEN")
    if not harness_url or not admin_token:
        print("[producer]    studio-chat-fallback: OEB_HARNESS_URL/API_ADMIN_TOKEN "
              "not set; skipping, scene stays NEEDS_ASSETS")
        return None
    try:
        result = build_scene_via_studio_chat(
            harness_url, admin_token, scene_creative_request(scene_id, scene),
            thread_title=f"{episode}/{scene_id} (Producer rough draft)",
        )
    except Exception as exc:  # noqa: BLE001 -- any failure here must not crash the run
        print(f"[producer]    studio-chat-fallback: FAILED ({exc}); "
              f"scene stays NEEDS_ASSETS")
        return None
    if result.get("unresolved"):
        print("[producer]    studio-chat-fallback: still unresolved after "
              "auto-clarification; scene stays NEEDS_ASSETS")
        return None
    return result


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

    only = None
    if args.scenes:
        only = {int(n) for n in args.scenes.split(",") if n.strip()}

    outcomes = {}
    vocab_findings = {}
    for idx, scene in enumerate(doc["scenes"]):
        number = scene.get("number", idx + 1)
        if only is not None and number not in only:
            continue
        scene_id = f"{episode}_sc{number:02d}"
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
                lname = name.lower()
                if lname not in cast:
                    blocking.append({
                        "kind": "role", "name": lname,
                        "source": "producer vocabulary sweep",
                        "detail": f"speaker '{name}' has no cast mapping "
                                  f"in data/standins.json"})

        # Already-cast actors present in this scene (dialogue OR named in
        # the action text -- same rule build_intent()'s present_actors()
        # uses) can still be missing a spawn_mark for THIS scene's
        # location: data/resolver_map.json roles are per-location (see
        # register_placeholder_role), and a role first registered for one
        # location has nothing for a different one. The resolve stage
        # would only catch this later, too late for --primitive-fallback
        # to help unless flagged here.
        if location_tag is not None:
            for name in present_actors(scene, cast):
                role_tag = cast[name]
                role_entry = rmap.get("roles", {}).get(role_tag, {})
                if location_tag not in role_entry.get("spawn_marks", {}):
                    blocking.append({
                        "kind": "role_location", "name": name,
                        "role_tag": role_tag,
                        "character_id": role_entry.get("character_id"),
                        "source": "producer vocabulary sweep",
                        "detail": f"'{name}' is cast as role '{role_tag}' "
                                  f"but that role has no spawn_mark for "
                                  f"location '{location_tag}'"})

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

        if blocking and args.primitive_fallback:
            resolved_count = len(blocking)
            blocking, location_tag = primitive_fallback(blocking, rmap, cast, location_tag)
            resolved_count -= len(blocking)
            if resolved_count:
                print(f"[producer]    primitive-fallback: resolved "
                      f"{resolved_count}/{resolved_count + len(blocking)} blocker(s)")

        if blocking:
            tpath = tickets.write_ticket(episode, scene_id, blocking,
                                         script_ref=args.script)
            tickets.update_report(episode, scene_id, "NEEDS_ASSETS",
                                  ticket=os.path.basename(tpath))
            outcomes[scene_id] = ("NEEDS_ASSETS", None)
            print(f"[producer]    BLOCKED — {len(blocking)} missing; "
                  f"ticket written; continuing")
            continue

        if args.primitive_fallback and not present_actors(scene, cast):
            register_vehicle_placeholder(scene, cast, rmap, location_tag)

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
            if args.studio_chat_fallback:
                rough_draft = studio_chat_rough_draft(scene_id, scene, episode, args)
                if rough_draft is not None:
                    outcomes[scene_id] = ("ROUGH_DRAFT", rough_draft.get("review_url"))
                    print(f"[producer]    ROUGH_DRAFT via Studio Chat — "
                          f"{rough_draft.get('review_url')} (still ticketed; "
                          f"the deterministic asset is still wanted)")
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

    n = {"DELIVERED": 0, "NEEDS_ASSETS": 0, "FAILED": 0, "ROUGH_DRAFT": 0}
    for st, _ in outcomes.values():
        n[st] += 1
    report = {
        "episode": episode, "script": args.script,
        "scenes": {sid: {"status": st, "render": r}
                   for sid, (st, r) in outcomes.items()},
        "vocabulary": vocab_findings,
        "delivered": n["DELIVERED"], "blocked": n["NEEDS_ASSETS"],
        "failed": n["FAILED"], "rough_draft": n["ROUGH_DRAFT"],
        "episode_cut": cut,
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

    # PUBLISHING-PLAN hook: delivered episode cut → unlisted upload.
    # Publish problems are reported, never fatal to the production run.
    if args.publish and cut:
        pub = subprocess.run(
            [VENV_PY, "tools/upload_render.py", "--video", cut,
             "--episode", episode, "--report", rpath],
            stdin=subprocess.DEVNULL)
        if pub.returncode != 0:
            print(f"[producer] publish FAILED (exit {pub.returncode}) — "
                  f"render delivered; see upload_render output above")
    elif args.publish:
        print("[producer] publish skipped — no episode cut this run")

    print(f"[producer] SUMMARY: {n['DELIVERED']} delivered, "
          f"{n['NEEDS_ASSETS']} blocked, {n['ROUGH_DRAFT']} rough draft, "
          f"{n['FAILED']} failed — {rpath}")
    sys.exit(0 if n["FAILED"] == 0 else 1)


if __name__ == "__main__":
    main()
