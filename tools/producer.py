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
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screenplay  # noqa: E402
import tickets     # noqa: E402
import director    # noqa: E402
import motion_library  # noqa: E402
from script_desk import find_ffmpeg, find_slate_font, slate_drawtext  # noqa: E402
from producer_studio_chat_client import build_scene_via_studio_chat  # noqa: E402
import placeholder_blueprint  # noqa: E402
from screenplay_entity_resolution import extract_entity_candidates  # noqa: E402
import llm_asset_match  # noqa: E402

CONFIG_PATH = "oeb.config.json"
RESOLVER_MAP_PATH = "data/resolver_map.json"
STANDINS_PATH = "data/standins.json"
PLACEHOLDER_ASSETS_ROOT = "assets/placeholders"

VENV_PY = ".venv/bin/python"
HARNESS_URL_ENV = "OEB_HARNESS_URL"
HARNESS_ADMIN_TOKEN_ENV = "API_ADMIN_TOKEN"
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
                 departures, descriptions, director_plan=None):
    """SceneIntent assembly from parsed structure. *arrivals*/*departures*
    (tools/screenplay.py keyword detection) and each section's parsed
    shot-heading framing/subject are the deterministic fallbacks; when
    *director_plan* is given (tools/director.py, already sanitized
    against this scene's actual cast/section count), its per-shot
    framing/subject decisions fill sections the screenplay itself left
    open (an explicit author shot heading's framing type is never
    overridden -- only a missing/invalid subject on it gets filled in).

    Blocking is a UNION, not a replacement: an actor arrives/departs if
    EITHER the keyword regex OR the director's (evidence-grounded) plan
    says so. Live testing against the local 3B director model showed
    it isn't reliable enough on its own to safely replace the regex --
    both false positives (asserting an arrival with no textual basis)
    and, with a stricter grounding prompt, false negatives (missing an
    arrival the regex catches cleanly) were observed. The union keeps
    the regex as a reliability floor while still letting the director
    add coverage for phrasing the regex misses ("storms off" etc.).
    See docs/planning/DIRECTOR-ROLE-PLAN.md's 2026-08-10 decision.
    """
    present = present_actors(scene, cast)
    # SceneIntent's actor_id must match ^[a-z][a-z0-9_]*$ -- a raw
    # dialogue-cue speaker name can contain a space ("SHIP AI"), so the
    # id used everywhere below is a slug, not the cast key itself.
    slug = {name: _role_tag_for(name) for name in present}
    plan_blocking = (director_plan or {}).get("blocking", {})
    plan_shots = (director_plan or {}).get("shots", {})

    actors = []
    for name in present:
        actor = {"actor_id": slug[name], "role_tag": cast[name]}
        pb = plan_blocking.get(name)
        arr = name in arrivals or (pb is not None and pb["arrives"])
        dep = name in departures or (pb is not None and pb["departs"])
        if arr:
            actor["arrives"] = True
        if dep:
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
        plan_shot = plan_shots.get(j)
        # Mid-scene move (docs/planning/DIRECTOR-ROLE-PLAN.md): director's
        # move, already validated against this scene's real cast and the
        # location's real marks in director.sanitize_plan(); nothing
        # deterministic feeds this, no move without a director decision.
        if plan_shot and plan_shot.get("move"):
            mv = plan_shot["move"]
            beat["moves"] = [{"actor_id": slug[mv["actor"]], "to_mark": mv["to_mark"]}]
        beats.append(beat)

        framing = sec["framing"]
        subject = (sec["subject_raw"] or "").lower() or None
        si = {"order": j, "beat_orders": [j]}
        if framing in ("close_on", "medium_on"):
            # Explicit author heading -- framing type is authoritative,
            # never overridden; the director may only supply a subject
            # when the screenplay's own subject_raw didn't resolve.
            if subject in cast:
                si["framing"] = framing
                si["subject_actor_id"] = slug[subject]
            elif plan_shot is not None and plan_shot["subject_actor"]:
                si["framing"] = framing
                si["subject_actor_id"] = slug[plan_shot["subject_actor"]]
            else:
                si["framing"] = "establishing"   # fallback, noted upstream
        elif framing is None and plan_shot is not None:
            si["framing"] = plan_shot["framing"]
            if plan_shot["framing"] in ("close_on", "medium_on") and plan_shot["subject_actor"]:
                si["subject_actor_id"] = slug[plan_shot["subject_actor"]]
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


def _find_existing_job(harness_url, admin_token, title, scene_number=None):
    """Best-effort lookup: is there already a pending or running job
    with this exact *title* on the queue? Found live 2026-08-13: with
    no dedup check, three repeated triage runs over the same still-
    blocked scenes piled up dozens of duplicate jobs per blocker (one
    role hit 34) -- each duplicate independently re-triggers
    trigger_continuation() once resolved, which was stacking up
    multiple concurrent real renders of the same scene. Checks
    "pending" and "running" only (not "completed"/"failed") --
    job_status has no OR filter server-side, so this is two GETs, not
    one.

    *scene_number*, when given, also requires the candidate's own
    `--scene-number` script arg to match: a casting-director title is
    keyed on speaker_name alone (`casting-director: waitress`), but the
    same speaker can legitimately need a fresh job for a *different*
    scene/location (register_placeholder_role() there just extends
    that role's spawn_marks) -- title-only matching would wrongly
    suppress that. set-designer jobs don't pass this: a location tag
    resolves once, globally, regardless of which scene asked first.

    Returns the first match's summary dict, or None (also on any
    lookup failure -- this must never block enqueueing outright; a
    failed dedup check just means an occasional duplicate, the
    original failure mode, not a lost job).
    """
    for status in ("pending", "running"):
        req = urllib.request.Request(
            harness_url.rstrip("/") + f"/api/v1/jobs?job_status={status}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                jobs = json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError):
            return None
        for job in jobs:
            if job.get("title") != title:
                continue
            if scene_number is not None:
                args = (job.get("payload") or {}).get("script_args") or []
                if str(scene_number) not in args:
                    continue
            return job
    return None


def enqueue_set_designer_job(location_name, script, episode, scene_number, int_ext=None,
                             location_context=None):
    """Best-effort: POST a job to the harness worker queue
    (docs/planning/WORKER-AGENT-PLAN.md) for tools/set_designer.py to
    pick up via the *existing* BlenderCLIAdapter's script_file payload
    mode -- no new adapter, per the 2026-08-10 decision to extend the
    existing worker system rather than build a separate one. Silently
    skipped if the harness isn't configured (OEB_HARNESS_URL/
    API_ADMIN_TOKEN unset) -- Producer stays usable standalone; the
    NEEDED ticket this accompanies is always written regardless and
    remains the source of truth for what's blocked.

    *location_context* (docs/planning/LLM-ASSET-MATCHING-PLAN.md) is
    the scene's own action text, threaded through to
    set_designer.py's tier-1.5 LLM match as grounding evidence -- None
    just means tier-1.5 is skipped for this job, same tier-1 -> tier-2
    behavior as before it existed.
    """
    harness_url = os.environ.get(HARNESS_URL_ENV)
    admin_token = os.environ.get(HARNESS_ADMIN_TOKEN_ENV)
    if not harness_url or not admin_token:
        return None

    title = f"set-designer: {location_name}"
    existing = _find_existing_job(harness_url, admin_token, title)
    if existing:
        print(f"[producer]    set-designer job already {existing.get('status')} "
              f"(id={existing.get('id')}) for location '{location_name}'; not re-enqueuing")
        return existing

    payload = {
        "title": title,
        "description": (
            f"Resolve unmapped location '{location_name}' for "
            f"{episode} scene {scene_number} (stand-in match, else "
            f"primitive placeholder), then continue production."
        ),
        "required_capabilities": ["blender.command_line"],
        "payload": {
            "script_file": "tools/set_designer.py",
            "cwd": "{workspace_root}",
            "script_args": [
                "--location-name", location_name,
                "--script", script,
                "--episode", episode,
                "--scene-number", str(scene_number),
            ] + (["--int-ext", int_ext] if int_ext else [])
              + (["--location-context", location_context] if location_context else []),
        },
    }
    req = urllib.request.Request(
        harness_url.rstrip("/") + "/api/v1/jobs",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {admin_token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[producer]    set-designer job enqueue FAILED ({exc}); "
              f"ticket written, no auto-follow-up")
        return None


def enqueue_casting_director_job(speaker_name, location_tag, script, episode,
                                 scene_number, depends_on_job_id=None,
                                 scene_context=None):
    """Best-effort: POST a job to the harness worker queue for
    tools/casting_director.py to pick up, same convention as
    enqueue_set_designer_job() -- dispatched through the *existing*
    BlenderCLIAdapter, no new adapter, silently skipped if the harness
    isn't configured (ticket is always written regardless).

    *depends_on_job_id*, when given (a location job just enqueued for
    this same scene), is set on the created job so the harness never
    offers it to a worker until that location job's status is
    "completed" -- docs/planning/CASTING-DIRECTOR-PLAN.md Open
    Question #1: casting can't anchor a spawn_mark until the location
    this scene names actually exists.

    *scene_context* (docs/planning/LLM-ASSET-MATCHING-PLAN.md) is the
    scene's own dialogue/action text, threaded through to
    casting_director.py's tier-1.5 alias/real-asset matching as
    grounding evidence -- None just means tier-1.5 is skipped for this
    job, same exact-match-or-build behavior as before it existed.
    """
    harness_url = os.environ.get(HARNESS_URL_ENV)
    admin_token = os.environ.get(HARNESS_ADMIN_TOKEN_ENV)
    if not harness_url or not admin_token:
        return None

    title = f"casting-director: {speaker_name}"
    existing = _find_existing_job(harness_url, admin_token, title, scene_number=scene_number)
    if existing:
        print(f"[producer]    casting-director job already {existing.get('status')} "
              f"(id={existing.get('id')}) for role '{speaker_name}' scene {scene_number}; "
              f"not re-enqueuing")
        return existing

    payload = {
        "title": title,
        "description": (
            f"Resolve unmapped speaking role '{speaker_name}' for "
            f"{episode} scene {scene_number} (principal or shared "
            f"background placeholder), then continue production."
        ),
        "required_capabilities": ["blender.command_line"],
        "payload": {
            "script_file": "tools/casting_director.py",
            "cwd": "{workspace_root}",
            "script_args": [
                "--speaker-name", speaker_name,
                "--location-tag", location_tag,
                "--script", script,
                "--episode", episode,
                "--scene-number", str(scene_number),
            ] + (["--scene-context", scene_context] if scene_context else []),
        },
    }
    if depends_on_job_id:
        payload["depends_on_job_id"] = depends_on_job_id
    req = urllib.request.Request(
        harness_url.rstrip("/") + "/api/v1/jobs",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {admin_token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[producer]    casting-director job enqueue FAILED ({exc}); "
              f"ticket written, no auto-follow-up")
        return None


# A small, closed vocabulary of common vehicle nouns -- same "reuse
# existing rails, no new judgment-call vocabulary" discipline as
# tools/casting_director.py's FUNCTIONAL_LABEL_KEYWORDS. Only used to
# find a subject already present in a scene's own action text (see
# _generic_vehicle_subject()) -- never invented, never written into
# the scene.
VEHICLE_NOUN_KEYWORDS = (
    "ship", "probe", "shuttle", "fighter", "cruiser", "vessel", "craft",
    "freighter", "transport", "station", "drone", "satellite", "pod",
    "fleet", "carrier", "frigate",
)


def _generic_vehicle_subject(text):
    """A common vehicle noun literally present in *text* -- fixed
    2026-08-13 after an invented generic name ("unnamed vehicle")
    silently failed present_actors()'s own requirement that a cast
    member's name actually appear in the scene text (names_in()'s
    word-boundary regex): registering the role succeeded, but the
    scene's actors list stayed empty anyway since nothing in the text
    ever matched the made-up name. Picks the earliest VEHICLE_NOUN_KEYWORDS
    match by text position (deterministic) so the result is guaranteed
    to be a real substring of the scene. None if nothing matches --
    caller leaves the scene FAILED rather than inventing an ungrounded
    subject.
    """
    lowered = text.lower()
    matches = []
    for kw in VEHICLE_NOUN_KEYWORDS:
        m = re.search(rf"\b{kw}\b", lowered)
        if m:
            matches.append((m.start(), kw))
    if not matches:
        return None
    matches.sort()
    return matches[0][1]


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

    Fixed 2026-08-13: some actor-less shots never name their vehicle at
    all ("the red ship breaks free...") -- no proper noun anywhere, so
    extract_entity_candidates() found nothing and the scene just stayed
    FAILED on the schema's non-empty-actors check forever. Falls back to
    a common vehicle noun already present in the scene's own text
    (_generic_vehicle_subject()) in that case, rather than giving up.
    Must be an actual substring of the scene -- present_actors() (below,
    via names_in()) only includes a cast member whose name literally
    appears in the scene text; an earlier attempt at this fix used an
    invented name ("unnamed vehicle") that registered fine but never
    satisfied that check, so the scene stayed FAILED anyway.

    Returns the registered speaker-name key (already added to *cast*
    in place) or None if no location was available to anchor marks
    against, or no candidate/vehicle noun was found at all -- never
    fatal, the scene just stays FAILED on the empty-actors schema error
    exactly as it did before this existed.
    """
    text = scene_action_text(scene)
    # No "already in cast" pre-filter here (removed 2026-08-13, see
    # docs/planning/VEHICLE-DISCOVERY-PLAN.md Discovery 4's second bug):
    # this function only ever runs when not present_actors(scene, cast),
    # and present_actors() checks every cast member's name against this
    # exact same scene_action_text(scene) via names_in() -- so a cast
    # member actually named in this scene's text would already have
    # been caught there, making the caller skip this function entirely.
    # Filtering candidates against *cast* here was therefore dead code
    # for its apparent protective intent, and its only live effect was
    # silently dropping an already-cast VEHICLE's name before the
    # already-cast branch below ever got a chance to extend it --
    # falling through to the generic-noun fallback instead, as if the
    # scene had never named it at all.
    candidates = extract_entity_candidates(text)

    location_set_id = rmap.get("locations", {}).get(location_tag or "", {}).get("set_id")
    if location_set_id is None:
        print("[producer]    primitive-fallback: no location to anchor vehicle "
              "placeholder marks against; skipping")
        return None

    if candidates:
        # Prefer the most-repeated candidate, not just the first-seen
        # one: a genuine recurring subject (e.g. a ship named throughout
        # the scene) gets mentioned more than once; a one-off
        # capitalized scene-opener word ("Black.", describing the void
        # before the stars appear) doesn't. Confirmed live 2026-08-09 --
        # first-seen alone picked "Black" over "JourneyBlaster" for
        # exactly this scene.
        lowered = text.lower()
        candidates.sort(key=lambda c: lowered.count(c.lower()), reverse=True)
        subject = candidates[0]
    else:
        subject = _generic_vehicle_subject(text)
        if subject is None:
            return None

    speaker_name = subject.lower()

    if speaker_name in cast:
        # Already registered -- from an earlier scene's fallback (the
        # shared generic subject), or resolved some other way. Just
        # extend it to this location, same merge behavior every other
        # already-cast role relies on.
        role_tag = cast[speaker_name]
        canonical_id = rmap.get("roles", {}).get(role_tag, {}).get("character_id")
        if not canonical_id:
            return None
        try:
            placeholder_blueprint.register_placeholder_role(
                RESOLVER_MAP_PATH, role_tag, canonical_id, location_tag, location_set_id)
            rmap["roles"][role_tag] = json.load(open(RESOLVER_MAP_PATH))["roles"][role_tag]
            cast[speaker_name] = role_tag
            print(f"[producer]    primitive-fallback: extended vehicle placeholder "
                  f"'{subject}' -> {canonical_id} to location '{location_tag}'")
            return speaker_name
        except Exception as exc:  # noqa: BLE001 -- must not crash the run
            print(f"[producer]    primitive-fallback: FAILED extending vehicle "
                  f"'{subject}' ({exc}); scene stays as-is")
            return None

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
    config = json.load(open(CONFIG_PATH))
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
    # docs/planning/LLM-ASSET-MATCHING-PLAN.md: real (non-placeholder)
    # props already in the library -- built once, not per scene, since
    # config doesn't change during a run. Checked against an "unknown
    # item" before it becomes a ticket note, so a real prop the script
    # describes differently than its registered name doesn't generate
    # an avoidable note every single time it's mentioned.
    real_props = [
        {"id": aid, "display_name": aid, "description": ""}
        for aid, a in config.get("assets", {}).items()
        if a.get("kind") == "prop" and not a.get("placeholder")
    ]

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

        # Location: direct match, stand-in match, or blocked. Stand-in
        # matching and primitive-placeholder building both moved to
        # tools/set_designer.py (docs/planning/PRODUCTION-DESIGNER-PLAN.md,
        # 2026-08-10 discovery) -- Producer's job is strictly to notice
        # the gap and ticket it, never to resolve it itself, per
        # PRODUCER-PLAN.md's own charter. A tier-1 stand-in match
        # (set_designer.py's resolve_location()) deliberately never
        # writes a resolver_map.json locations[] entry under the raw
        # scripted tag -- only tier-2 (a fresh primitive build) does
        # that. Without checking data/standins.json's location_standins
        # here too (fixed 2026-08-13 -- casting_director.py's
        # resolve_role() already had this same fix), any location that
        # only ever resolves via a pre-existing stand-in match was
        # permanently stuck: every pass re-blocked it, set_designer.py's
        # tier-1 branch is a no-op against an already-satisfied mapping,
        # so nothing on disk ever changed and the scene could never
        # deliver. loc stays the raw tag for enqueue_casting_director_job
        # below (it resolves the stand-in internally); only
        # *location_tag*, used for everything else downstream, needs
        # the resolved value.
        loc = scene["location_tag"]
        standin = vocab.get("location_standins", {}).get(loc)
        if standin and standin in rmap.get("locations", {}):
            location_tag = standin
        elif loc in rmap.get("locations", {}):
            location_tag = loc
        else:
            location_tag = None
            blocking.append({
                "kind": "location", "name": loc,
                "source": "producer vocabulary sweep",
                "detail": f"location '{loc}' is not in the resolver map"})

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
                # Tier 1.5 (docs/planning/LLM-ASSET-MATCHING-PLAN.md):
                # does this "unknown" item actually match a real prop
                # already in the library under a different name?
                # Reuses this scene's own review as grounding evidence
                # -- no extra LLM call beyond the match itself.
                matched = False
                if real_props:
                    scene_evidence = scene_action_text(scene)
                    match_result = llm_asset_match.match_existing_asset(
                        item.strip(), scene_evidence, real_props, "prop")
                    if match_result["matched_id"] and llm_asset_match.grounded(
                            match_result["evidence"], scene_evidence):
                        known_items.add(norm)
                        vocab.setdefault("known_items", []).append(item.strip())
                        placeholder_blueprint._write_json(STANDINS_PATH, vocab)
                        matched = True
                if not matched:
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
        else:
            tickets.clear_ticket(episode, f"{scene_id}_vocab")

        if blocking:
            tpath = tickets.write_ticket(episode, scene_id, blocking,
                                         script_ref=args.script)
            tickets.update_report(episode, scene_id, "NEEDS_ASSETS",
                                  ticket=os.path.basename(tpath))
            # Location dispatch first so a same-scene role blocker can
            # depend on it (docs/planning/CASTING-DIRECTOR-PLAN.md Open
            # Question #1) -- casting can't anchor a spawn_mark until
            # the location this scene names actually exists.
            location_job_id = None
            for item in blocking:
                if item["kind"] == "location":
                    job = enqueue_set_designer_job(
                        item["name"], args.script, episode, number,
                        int_ext=scene.get("int_ext"),
                        location_context=f"{scene['slugline']}\n{scene_action_text(scene)}")
                    if job:
                        location_job_id = job.get("id")
                        print(f"[producer]    set-designer job enqueued "
                              f"(id={job.get('id')}) for location "
                              f"'{item['name']}'")
            for item in blocking:
                if item["kind"] in ("role", "role_location"):
                    job = enqueue_casting_director_job(
                        item["name"], loc, args.script, episode, number,
                        depends_on_job_id=location_job_id,
                        scene_context=f"{scene['slugline']}\n{scene_action_text(scene)}")
                    if job:
                        dep_note = f" (depends on location job {location_job_id})" \
                            if location_job_id else ""
                        print(f"[producer]    casting-director job enqueued "
                              f"(id={job.get('id')}) for role "
                              f"'{item['name']}'{dep_note}")
            outcomes[scene_id] = ("NEEDS_ASSETS", None)
            print(f"[producer]    BLOCKED — {len(blocking)} missing; "
                  f"ticket written; continuing")
            continue
        else:
            # Scene isn't blocked in this run -- if an earlier run left a
            # NEEDED ticket for it (e.g. set_designer's continuation
            # trigger re-invoking this exact scene after resolving its
            # location), that ticket is now stale; clear it rather than
            # let it pile up on disk indefinitely.
            tickets.clear_ticket(episode, scene_id)

        if args.primitive_fallback and not present_actors(scene, cast):
            register_vehicle_placeholder(scene, cast, rmap, location_tag)

        arrivals = screenplay.detect_arrivals(scene, list(cast))
        departures = screenplay.detect_departures(scene, list(cast))
        vocab_findings[scene_id]["arrivals"] = sorted(arrivals)
        vocab_findings[scene_id]["departures"] = sorted(departures)

        # Director: creative staging (docs/planning/DIRECTOR-ROLE-PLAN.md).
        # Runs after location/casting are resolved (this scene reached
        # here only because it isn't blocked) and before SceneIntent
        # assembly. On any LLM failure director_plan stays None and
        # build_intent() falls back to the deterministic heuristics
        # exactly as before this role existed -- a broken/unavailable
        # local LLM never blocks a scene.
        present_now = present_actors(scene, cast)
        location_entry = rmap.get("locations", {}).get(location_tag, {}) if location_tag else {}
        # Collision avoidance (docs/planning/CAMERA-SHOT-SCALE-PLAN.md):
        # filter to marks a real object of this scene's largest present
        # actor's registered radius could occupy without overlapping a
        # registered obstacle -- Director only ever sees safe move
        # destinations, so it never has to reason about geometry in
        # text at all. Actors/locations with no registered radius/
        # obstacles degrade to the full unfiltered marks list (backward
        # compatible with every scene registered before this existed).
        mover_radius = 0.0
        for name in present_now:
            role_tag = cast.get(name)
            char_id = rmap.get("roles", {}).get(role_tag, {}).get("character_id")
            radius = config.get("assets", {}).get(char_id, {}).get("radius_m")
            if radius:
                mover_radius = max(mover_radius, radius)
        location_marks = motion_library.clear_marks_for_mover(location_entry, mover_radius) \
            if mover_radius else location_entry.get("marks", [])
        director_plan, director_note = director.direct_scene(
            scene_id, scene, present_now, location_marks=location_marks,
            temp=args.temp, seed=args.seed)
        print(f"[producer]    director: {director_note}")
        if director_plan is not None:
            with open(os.path.join(sdir, "director_plan.json"), "w") as f:
                json.dump(director_plan, f, indent=2)
                f.write("\n")

        intent = build_intent(scene_id, scene, cast, location_tag,
                              arrivals, departures, descriptions,
                              director_plan=director_plan)
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

    # Merge into any existing report rather than overwrite it outright
    # (fixed 2026-08-13): a --scenes-scoped continuation run
    # (trigger_continuation() in casting_director.py/set_designer.py,
    # re-invoking producer.py for just the one now-unblocked scene)
    # only ever populates `outcomes` for that single scene -- writing
    # a report built from `outcomes` alone was clobbering the whole
    # episode's report down to one scene every time a single blocker
    # resolved. Found live: a full 81-scene run's report (66 delivered)
    # got reduced to "delivered: 1" by the very next casting job that
    # completed.
    rpath = os.path.join(edir, "production_report.json")
    scenes = {}
    vocabulary = {}
    existing_cut = None
    if os.path.exists(rpath):
        try:
            with open(rpath) as f:
                existing = json.load(f)
            scenes = existing.get("scenes", {})
            vocabulary = existing.get("vocabulary", {})
            existing_cut = existing.get("episode_cut")
        except (OSError, ValueError):
            pass
    # Never regress an already-DELIVERED scene (fixed 2026-08-14, found
    # live): a long full-episode pass holds its per-scene outcomes in
    # memory for its *entire* run -- tens of minutes once LLM-matching
    # tier-1.5 calls (docs/planning/LLM-ASSET-MATCHING-PLAN.md) stack on
    # top of the existing per-scene LLM calls. A concurrent worker-run
    # continuation (trigger_continuation()) can resolve and DELIVER that
    # same scene, and write its own fresher report, *while* the long
    # pass is still working through later scenes -- when the long pass
    # finally finishes and writes its own outcome for that scene (still
    # NEEDS_ASSETS, from when *it* evaluated that scene, possibly an
    # hour earlier), an unconditional overwrite silently clobbers the
    # fresher DELIVERED status back to blocked. A scene delivering is
    # never a worse outcome than "this run's own possibly-stale read
    # didn't know that yet" -- so a DELIVERED already on disk always
    # wins over anything this run's own outcomes dict says for the same
    # scene, regardless of which write happens last.
    for sid, (st, r) in outcomes.items():
        if scenes.get(sid, {}).get("status") == "DELIVERED" and st != "DELIVERED":
            continue
        scenes[sid] = {"status": st, "render": r}
    vocabulary.update(vocab_findings)

    n = {"DELIVERED": 0, "NEEDS_ASSETS": 0, "FAILED": 0, "ROUGH_DRAFT": 0}
    for entry in scenes.values():
        n[entry["status"]] += 1
    report = {
        "episode": episode, "script": args.script,
        "scenes": scenes,
        "vocabulary": vocabulary,
        "delivered": n["DELIVERED"], "blocked": n["NEEDS_ASSETS"],
        "failed": n["FAILED"], "rough_draft": n["ROUGH_DRAFT"],
        # A --scenes-scoped run never produces a real cut (it's always
        # --no-render, per trigger_continuation()'s own fix) -- keep
        # whatever cut an earlier full run already made instead of
        # blanking it out.
        "episode_cut": cut or existing_cut,
    }
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
