#!/usr/bin/env python3
"""llm_asset_match.py -- shared constrained asset/character matching
helper (docs/planning/LLM-ASSET-MATCHING-PLAN.md). Every deterministic
discovery mechanism in this pipeline (data/standins.json's
location_standins/cast, data/camera_grammar.json's subject_marks) is
an exact-match lookup against a flat, human-curated table; a miss
falls straight to placeholder generation, blind to whatever real,
already-built assets exist in oeb.config.json. This module adds one
more tier before that fallback: a constrained LLM match against a
*finite* list of real candidates, never a free-text guess.

Same llama-completion / --json-schema / temp=0 convention
tools/producer.py's llm_review() and tools/director.py already use --
no new LLM infrastructure, just a new call site. The candidate id
enum is embedded directly in the schema, so the model is structurally
unable to emit an id that wasn't offered -- there is no trust placed
in the model beyond picking (or declining to pick) from the list it
was given.

Callers MUST still perform their own grounding check (grounded())
before trusting a match -- this module does not verify its own
"evidence" field is real; it only enforces that matched_id is either
one of the given candidates or the literal string "none".
"""

from __future__ import annotations

import json
import re
import subprocess

LLAMA = "llama-completion"
MODEL = "llm/qwen2.5-3b-instruct-q4_k_m.gguf"

MATCH_SYSTEM = (
    "You match a name or phrase from a screenplay to the correct "
    "existing asset from a list of candidates, quoting the scene text "
    "that supports your choice. Use matched_id \"none\" only when no "
    "candidate is plausibly the same thing."
)


def match_existing_asset(
    subject_text: str,
    scene_evidence: str,
    candidates: list[dict],
    kind: str,
    *,
    temp: str = "0.0",
    seed: str = "1",
) -> dict:
    """Ask the local LLM whether *subject_text* (a name/phrase found in
    a screenplay) refers to one of *candidates* -- real, already
    registered entries only, never placeholders.

    *candidates*: list of {"id": str, "display_name": str,
    "description": str}. *kind*: "character" | "vehicle" | "location" |
    "camera" | "prop" -- descriptive only, not schema-enforced.

    Returns {"matched_id": str|None, "evidence": str|None}. matched_id
    is guaranteed to be either one of candidates[]["id"] or None -- the
    --json-schema enum makes any other value structurally impossible,
    so this function does not need to (and does not) second-guess that
    part of the model's output. evidence is NOT verified here; call
    grounded(evidence, scene_evidence) before trusting the match.

    Never fatal: any failure (no candidates, model unavailable, bad
    JSON, timeout) returns {"matched_id": None, "evidence": None},
    identical in shape to a confident "no match" -- callers fall
    through to their existing placeholder-build path unchanged either
    way.
    """
    if not candidates:
        return {"matched_id": None, "evidence": None}

    ids = [c["id"] for c in candidates]
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "oeb:assetmatch:1.0.0",
        "title": "AssetMatch",
        "type": "object",
        "additionalProperties": False,
        "required": ["matched_id", "evidence"],
        "properties": {
            "matched_id": {
                "enum": ids + ["none"],
                "description": (
                    "One of the given candidate ids, or the literal "
                    "string 'none' if no candidate is a genuine match."
                ),
            },
            "evidence": {
                "type": "string",
                "description": (
                    "An exact phrase copied from the scene text "
                    "supporting the match; empty string if matched_id "
                    "is 'none'."
                ),
            },
        },
    }

    lines = [
        f"A screenplay mentions a {kind}: \"{subject_text}\"",
        "",
        "Scene text:",
        scene_evidence,
        "",
        "Candidates (existing library assets -- pick one only if it is "
        "genuinely the same thing, otherwise answer 'none'):",
    ]
    for c in candidates:
        desc = c.get("description", "")
        lines.append(f"- id: {c['id']} | name: {c.get('display_name', c['id'])}"
                     + (f" | {desc}" if desc else ""))

    prompt = (f"<|im_start|>system\n{MATCH_SYSTEM}<|im_end|>\n"
              f"<|im_start|>user\n" + "\n".join(lines) +
              "<|im_end|>\n<|im_start|>assistant\n")

    cmd = [LLAMA, "-m", MODEL, "-p", prompt,
           "--json-schema", json.dumps(schema),
           "--temp", temp, "--seed", seed,
           "-n", "512", "-c", "4096", "--no-display-prompt"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=120, stdin=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        return {"matched_id": None, "evidence": None}
    if run.returncode != 0:
        return {"matched_id": None, "evidence": None}

    raw = run.stdout.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {"matched_id": None, "evidence": None}
    try:
        result = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return {"matched_id": None, "evidence": None}

    matched_id = result.get("matched_id")
    if matched_id not in ids:  # covers "none" and any grammar slip
        return {"matched_id": None, "evidence": None}
    return {"matched_id": matched_id, "evidence": result.get("evidence") or None}


_WS_PUNCT_RE = re.compile(r"[\s,]+")


def _normalize(text: str) -> str:
    """Collapse whitespace and commas to single spaces -- the model
    reliably quotes real scene text word-for-word, but freely
    substitutes a comma for a newline (confirmed live 2026-08-14: a
    correct match's evidence read "...WIDE, Orlando..." for source
    text "...WIDE\\nOrlando..."). Normalizing keeps the check strict
    on actual words/order while tolerant of that formatting drift.
    """
    return _WS_PUNCT_RE.sub(" ", text).strip().lower()


def grounded(evidence: str | None, scene_evidence: str) -> bool:
    """True iff *evidence* is an actual substring of *scene_evidence*,
    modulo whitespace/comma normalization -- the caller-side half of
    the grounding requirement (docs/planning/LLM-ASSET-MATCHING-PLAN.md:
    "a claimed flag whose evidence isn't an actual substring of the
    scene text is discarded"). match_existing_asset() does not call
    this itself -- every call site must, before persisting a match.
    """
    if not evidence or not scene_evidence:
        return False
    return _normalize(evidence) in _normalize(scene_evidence)
