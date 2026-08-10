#!/usr/bin/env python3
"""director.py -- the director role (docs/planning/DIRECTOR-ROLE-PLAN.md):
creative staging layer between factual scene extraction and SceneIntent
assembly. Replaces two heuristics tools/producer.py's build_intent() used
to own with real reasoning, constrained by schemas/directorplan.schema.json:

1. Camera framing/subject for sections with no author-specified shot
   heading, or whose heading names a subject not in the cast (previously:
   a static shot_headings dict lookup, blind "downgrade to establishing").
2. Actor arrival/departure blocking (previously: tools/screenplay.py's
   detect_arrivals()/detect_departures(), a fixed keyword regex that
   misses any phrasing outside "enters/walks in"/"exits/leaves/walks
   out" -- e.g. "flies into", "storms off").
3. Mid-scene relocation ("JB100 flies into the asteroid field"): the
   genuinely new gap DIRECTOR-ROLE-PLAN.md's 2026-08-10 discovery
   flagged -- previously nothing at all, arrives/departs only ever
   covered scene-start/scene-end walk-in/walk-out. Director picks a
   destination from the resolved location's own real marks (never an
   invented one) and informs SceneIntent.beats[].moves, which
   tools/resolve_intent.py resolves into a standard `move` SceneSpec
   cue -- the same cue type entrances/departures already use, no new
   exporter support needed.

DirectorPlan is a genuinely separate artifact (2026-08-10 decision, see
the plan doc) -- it informs SceneIntent's existing fields, it does not
replace them or change resolve_intent.py/SceneSpec's shape. An explicit
author shot heading's framing is never overridden by the director; the
director only fills gaps the screenplay itself left open, same
"deliberate author direction first" principle already established for
sluglines (docs/planning/SCREENPLAY-SLUGLINE-ACTOR-PRESENCE-GAP.md).

Same call/fallback discipline as tools/producer.py's llm_review(): a
constrained local-LLM call via the llama-completion CLI's --json-schema
grammar constraint, model output re-validated in Python past the schema
boundary (an LLM can only be constrained to valid *shape*, not to
referencing only this scene's actual cast), and a hard failure (timeout,
non-JSON, bad exit) returns (None, note) so the caller can fall back to
the deterministic heuristics -- a broken/unavailable LLM never blocks a
scene.
"""

from __future__ import annotations

import json
import subprocess

LLAMA = "llama-completion"
MODEL = "llm/qwen2.5-3b-instruct-q4_k_m.gguf"
DIRECTOR_SCHEMA = "schemas/directorplan.schema.json"

FRAMINGS = ("establishing", "two_shot", "close_on", "medium_on")

DIRECTOR_SYSTEM = (
    "You are the director for a deterministic 3D animation pipeline. "
    "You stage exactly what the teleplay already describes -- you never "
    "invent story events, dialogue, characters, or locations. For every "
    "numbered section you choose a camera framing from the fixed "
    "vocabulary (establishing, two_shot, close_on, medium_on); if the "
    "section already has an author-specified framing, keep it. For "
    "close_on/medium_on you name a subject_actor from the cast list "
    "given -- never anyone else. For every cast member present in this "
    "scene you decide, from the action text, whether they arrive on "
    "foot at the start or depart on foot at the end (most do neither -- "
    "default both to false). When you set arrives or departs true, copy "
    "the exact phrase from the action text into evidence that shows it; "
    "if you cannot quote real text supporting it, leave both false and "
    "evidence empty. If, and only if, a section's action text clearly "
    "describes an actor moving to a specific place mid-scene (not just "
    "arriving or departing), and one of the location's available marks "
    "given to you plausibly matches that place, set that section's move "
    "to name the actor, the exact mark from the list given, and a quoted "
    "phrase as evidence. Never invent a mark name not in the list given. "
    "If nothing matches, omit move entirely. Output only JSON.")


def _scene_prompt(scene_id, scene, present, location_marks):
    parts = [f"Cast present this scene: {', '.join(present) or '(none)'}",
             f"Location marks available (move destinations only, exact "
             f"names): {', '.join(location_marks) or '(none)'}", ""]
    for j, sec in enumerate(scene["sections"]):
        parts.append(f"SECTION {j}:")
        if sec["heading"]:
            hint = sec["framing"] or "none -- decide it"
            parts.append(f"(script shot heading: {sec['heading']!r}; "
                         f"author-specified framing: {hint})")
        parts.extend(sec["action"])
        for name, text in sec["dialogue"]:
            parts.append(f'{name}: "{text}"')
        parts.append("")
    return "\n".join(parts)


def direct_scene(scene_id, scene, present, location_marks=(), temp="0.0", seed="1"):
    """Constrained director call. *present* is the list of cast names
    (lowercase dialogue-cue keys) already confirmed present in this
    scene -- same present_actors() result build_intent() uses.
    *location_marks* is the resolved location's real mark names
    (data/resolver_map.json's locations[location_tag]["marks"]) -- the
    only destinations a mid-scene move may target. Returns
    (DirectorPlan|None, note); None on any failure, caller falls back
    to the deterministic heuristics.
    """
    prompt = (f"<|im_start|>system\n{DIRECTOR_SYSTEM}<|im_end|>\n"
              f"<|im_start|>user\nDirect scene {scene_id} "
              f"({scene['slugline']}).\n" +
              _scene_prompt(scene_id, scene, present, location_marks) +
              "<|im_end|>\n<|im_start|>assistant\n")
    cmd = [LLAMA, "-m", MODEL, "-p", prompt,
           "--json-schema", open(DIRECTOR_SCHEMA).read(),
           "--temp", temp, "--seed", seed,
           "-n", "1024", "-c", "4096", "--no-display-prompt"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=600, stdin=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"director failed: {exc}"
    if run.returncode != 0:
        return None, f"director exit {run.returncode}"
    raw = run.stdout.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None, "director: no JSON in output"
    try:
        plan = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        return None, f"director: bad JSON ({exc})"
    return sanitize_plan(plan, scene, present, location_marks), "ok"


def sanitize_plan(plan, scene, present, location_marks=()):
    """Re-validate past the schema boundary: a JSON-schema grammar
    constrains *shape* (order is an int, framing is one of four
    strings) but not *this scene's* actual cast or section count --
    those are per-call facts the grammar can't see. Any shot/blocking
    entry referencing something outside this scene's real data is
    dropped rather than trusted; same safety margin build_intent()'s
    old hand-written heuristics already applied to their own inputs.
    """
    present_lower = {n.lower() for n in present}
    n_sections = len(scene["sections"])
    scene_text = " ".join(
        p for sec in scene["sections"] for p in sec["action"]).lower()
    marks_available = set(location_marks)

    shots = {}
    for shot in plan.get("shots", []):
        order = shot.get("order")
        if not isinstance(order, int) or not (0 <= order < n_sections):
            continue
        framing = shot.get("framing")
        if framing not in FRAMINGS:
            framing = "establishing"
        subject = (shot.get("subject_actor") or "").strip().lower() or None
        if framing in ("close_on", "medium_on") and subject in present_lower:
            pass
        elif framing in ("close_on", "medium_on"):
            framing, subject = "establishing", None
        else:
            subject = None

        # Same grounding discipline as blocking: an evidence quote must
        # be a real substring of this scene's own action text, and
        # to_mark must be exactly one of the location's real marks --
        # never a name the model made up. Either check failing drops
        # the move entirely (None), same safe-degrade as a shot whose
        # framing/subject didn't check out.
        move = None
        raw_move = shot.get("move")
        if isinstance(raw_move, dict):
            move_actor = (raw_move.get("actor") or "").strip().lower()
            move_mark = (raw_move.get("to_mark") or "").strip()
            move_evidence = (raw_move.get("evidence") or "").strip().lower()
            if (move_actor in present_lower and move_mark in marks_available
                    and move_evidence and move_evidence in scene_text):
                move = {"actor": move_actor, "to_mark": move_mark}

        shots[order] = {
            "framing": framing, "subject_actor": subject,
            "purpose": shot.get("purpose", ""),
            "motion_note": shot.get("motion_note", ""),
            "move": move,
        }

    blocking = {}
    for b in plan.get("blocking", []):
        actor = (b.get("actor") or "").strip().lower()
        if actor not in present_lower:
            continue
        # Grounding check: a claimed arrives/departs must come with an
        # evidence quote that's an actual substring of this scene's own
        # action text -- catches hallucinated flags (nothing constrains
        # the LLM to be *right*, only to shape) without falling back to
        # a fixed keyword list, so phrasing the old regex-based
        # detect_arrivals()/detect_departures() missed still counts as
        # long as it's genuinely quoted from the text.
        evidence = (b.get("evidence") or "").strip().lower()
        grounded = bool(evidence) and evidence in scene_text
        blocking[actor] = {"arrives": bool(b.get("arrives")) and grounded,
                           "departs": bool(b.get("departs")) and grounded}

    return {
        "dramatic_intent": plan.get("dramatic_intent", ""),
        "shots": shots,          # {order: {...}}, order already int-keyed
        "blocking": blocking,    # {actor_name: {...}}
    }
