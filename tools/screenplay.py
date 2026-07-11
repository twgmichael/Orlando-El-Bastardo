#!/usr/bin/env python3
"""
screenplay.py — deterministic industry-screenplay parser (Producer P3).

Parses standard screenplay conventions with NO LLM involvement (the P2
lesson: structure is script metadata, the translator gets no vote):

  sluglines     INT./EXT. LOCATION - TIME   → scene boundary + facts
  shot headings WIDE SHOT / MEDIUM SHOT - X → shot boundary + framing intent
  transitions   CUT TO: etc.                → section separator
  act markers   TEASER / ACT ONE / ...      → metadata
  character cue indented ALL-CAPS line followed by indented speech
  action        column-0 prose paragraphs

Output shape (parse()):
  {"acts": [...], "scenes": [ {
      "slugline", "location_raw", "location_tag", "time_of_day",
      "sections": [ {"heading", "framing", "subject_raw",
                     "action": [para, ...], "dialogue": [(NAME, text), ...]} ]
  } ]}

Framings and subjects come from the shot-heading vocabulary in
data/standins.json; unknown headings are preserved raw with framing=None so
the producer can ticket them.
"""

import re

SLUG_RE = re.compile(r"^(INT|EXT|INT/EXT)[.\s]+(.+?)\s*[-–]\s*([A-Z ]+)\s*$")
TRANSITION_RE = re.compile(
    r"^\s*(?:[A-Z][A-Z .]*TO:|FADE (?:IN|OUT|TO BLACK)[.:]?)\s*$")
ACT_RE = re.compile(
    r"^\s*(TEASER|COLD OPEN|TAG|ACT\s+[A-Z]+|END OF [A-Z ]+)\s*$")
TIME_MAP = {
    "MORNING": "morning", "DAY": "day", "AFTERNOON": "day",
    "EVENING": "evening", "DUSK": "evening", "NIGHT": "night",
    "LATER": None, "CONTINUOUS": None,
}


def _norm_tag(raw):
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")


def _is_shot_heading(line, vocab):
    """Return (framing|None, subject_raw|None, matched) for a bare line."""
    s = line.strip()
    if not s or s != s.upper() or line.startswith((" ", "\t")):
        return None, None, False
    # "MEDIUM SHOT - BARTENDER" / "MEDIUM SHOT - HERO (FROM BEHIND)"
    m = re.match(r"^([A-Z][A-Z /-]*?(?:SHOT|UP|ON))(?:\s*[-–]\s*(.+))?$", s)
    if not m:
        return None, None, False
    head, subj = m.group(1).strip(), m.group(2)
    framing = vocab.get("shot_headings", {}).get(head)
    subject_raw = None
    if subj:
        subject_raw = re.sub(r"\(.*?\)", "", subj).strip()  # drop (FROM BEHIND)
    return framing, subject_raw, True


def parse(text, vocab):
    """Parse screenplay text → {"acts": [...], "scenes": [...]}."""
    lines = text.splitlines()
    acts = []
    scenes = []
    scene = None
    section = None
    last_time = "day"
    i = 0

    def new_section(heading=None, framing=None, subject_raw=None):
        nonlocal section
        section = {"heading": heading, "framing": framing,
                   "subject_raw": subject_raw, "action": [], "dialogue": []}
        scene["sections"].append(section)

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue

        am = ACT_RE.match(line)
        if am:
            acts.append(am.group(1).strip())
            i += 1
            continue

        sm = SLUG_RE.match(s)
        if sm and not line.startswith(" "):
            loc_raw = sm.group(2).strip()
            tod = TIME_MAP.get(sm.group(3).strip(), None)
            if tod is None:
                tod = last_time
            last_time = tod
            scene = {"slugline": s, "location_raw": loc_raw,
                     "location_tag": _norm_tag(loc_raw), "time_of_day": tod,
                     "sections": []}
            scenes.append(scene)
            section = None
            i += 1
            continue

        if scene is None:
            i += 1   # prose before any slugline (title page etc.)
            continue

        if TRANSITION_RE.match(line):
            i += 1
            continue

        framing, subject_raw, is_shot = _is_shot_heading(line, vocab)
        if is_shot:
            new_section(heading=s, framing=framing, subject_raw=subject_raw)
            i += 1
            continue

        # Character cue: indented ALL-CAPS name, speech on following
        # indented lines until a blank line.
        if line.startswith(" ") and s == s.upper() \
                and re.match(r"^[A-Z][A-Z '.\-]+(\s*\(.*\))?$", s):
            name = re.sub(r"\s*\(.*\)$", "", s).strip()
            i += 1
            speech = []
            while i < len(lines) and lines[i].strip() \
                    and lines[i].startswith(" "):
                speech.append(lines[i].strip())
                i += 1
            if speech:
                if section is None:
                    new_section()
                section["dialogue"].append((name, " ".join(speech)))
            continue

        # Action paragraph: gather until blank line
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() \
                and not lines[i].startswith(" ") \
                and not SLUG_RE.match(lines[i].strip()) \
                and not _is_shot_heading(lines[i], vocab)[2] \
                and not TRANSITION_RE.match(lines[i]):
            para.append(lines[i].strip())
            i += 1
        if section is None:
            new_section()
        section["action"].append(" ".join(para))

    return {"acts": acts, "scenes": scenes}


def detect_arrivals(scene, cast_names):
    """Deterministic entrance detection: an actor 'enters' / 'walks in'
    in the scene's action text → arrives. Returns a set of cast names."""
    arrivals = set()
    text = " ".join(p for sec in scene["sections"] for p in sec["action"])
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\b(enters?|walks?\s+in)\b", sentence, re.I):
            for name in cast_names:
                if re.search(rf"\b{re.escape(name)}\b", sentence, re.I):
                    arrivals.add(name)
    return arrivals


def detect_departures(scene, cast_names):
    """Deterministic exit detection: an actor 'exits' / 'leaves' /
    'walks out' in the scene's action text → departs."""
    departures = set()
    text = " ".join(p for sec in scene["sections"] for p in sec["action"])
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\b(exits?|leaves?|walks?\s+(?:out|off))\b",
                     sentence, re.I):
            for name in cast_names:
                if re.search(rf"\b{re.escape(name)}\b", sentence, re.I):
                    departures.add(name)
    return departures


def audio_directions(scene, keywords):
    """Deterministic audio sweep: sentences in action text containing an
    audio keyword. Returns [sentence, ...]."""
    hits = []
    kw = {k.lower() for k in keywords}
    for sec in scene["sections"]:
        for para in sec["action"]:
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                words = {w.strip(".,;:!?'\"()").lower()
                         for w in sentence.split()}
                if words & kw:
                    hits.append(sentence.strip())
    return hits
