#!/usr/bin/env python3
"""
tickets.py — the production office (PRODUCER-PLAN P1: ticketing).

Classifies pipeline failures into NEEDED tickets (missing library
vocabulary/assets — things a crew must BUILD) versus plain failures (bugs,
bad input — things a crew must FIX), writes the per-episode ticket files,
and maintains the episode's report.json index.

Layout (gitignored, derived state — script + library ⇒ tickets):
  out/production/<episode>/
    report.json                    episode index: scenes, statuses, open tickets
    tickets/NEEDED-<scene>.json    structured work request
    tickets/NEEDED-<scene>.md      one-glance human summary

Only missing-library error classes become tickets:
  resolver  E_UNMAPPED_LOCATION → location      E_UNMAPPED_ROLE → role
            E_UNMAPPED_TIME_OF_DAY → time_of_day_variant
            E_UNMAPPED_ASSET → asset            E_NO_CAMERA → framing
            E_MISSING_SUBJECT → framing
  validator unknown_clip → clip   unknown_mark → mark
            unknown_camera → camera             unknown_asset → asset
            unknown_audio → audio               missing_prop_asset → prop
Everything else (schema errors, duplicates, timing, tool crashes) is a
FAILED scene, not a NEEDED one — improvising the difference is exactly what
ticketing exists to prevent.
"""

import datetime
import json
import os
import re

RESOLVER_KINDS = {
    "E_UNMAPPED_LOCATION": "location",
    "E_UNMAPPED_TIME_OF_DAY": "time_of_day_variant",
    "E_UNMAPPED_ROLE": "role",
    "E_UNMAPPED_ASSET": "asset",
    "E_NO_CAMERA": "framing",
    "E_MISSING_SUBJECT": "framing",
}
VALIDATOR_KINDS = {
    "unknown_clip": "clip",
    "unknown_mark": "mark",
    "unknown_camera": "camera",
    "unknown_asset": "asset",
    "unknown_audio": "audio",
    "missing_prop_asset": "prop",
}
_DETAIL = re.compile(r"'([^']+)'")


def episode_dir(episode):
    return os.path.join("out", "production", episode)


def missing_from_resolver(stderr_text):
    """RESOLVE-ERROR lines → missing[] entries (ticketable classes only)."""
    missing = []
    for line in stderr_text.splitlines():
        m = re.match(r"RESOLVE-ERROR\s+(E_[A-Z_]+):\s*(.*)", line.strip())
        if not m:
            continue
        code, detail = m.group(1), m.group(2)
        kind = RESOLVER_KINDS.get(code)
        if kind is None:
            continue
        name = _DETAIL.search(detail)
        missing.append({
            "kind": kind,
            "name": name.group(1) if name else detail[:80],
            "source": f"resolver {code}",
            "detail": detail,
        })
    return missing


def missing_from_validation(report):
    """ValidationReport dict → missing[] entries (ticketable codes only)."""
    missing = []
    for finding in report.get("errors", []) + report.get("warnings", []):
        kind = VALIDATOR_KINDS.get(finding.get("code"))
        if kind is None:
            continue
        name = _DETAIL.search(finding.get("message", ""))
        missing.append({
            "kind": kind,
            "name": name.group(1) if name else finding.get("message", "")[:80],
            "source": f"validator {finding['code']}",
            "detail": finding.get("message", ""),
            "path": finding.get("path", ""),
        })
    return missing


def write_ticket(episode, scene_id, missing, script_ref=None):
    """Write NEEDED-<scene>.json/.md; return the json path."""
    tdir = os.path.join(episode_dir(episode), "tickets")
    os.makedirs(tdir, exist_ok=True)
    ticket = {
        "ticket": f"NEEDED-{scene_id}",
        "episode": episode,
        "scene_id": scene_id,
        "status": "NEEDS_ASSETS",
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "script_ref": script_ref,
        "missing": missing,
        "next_step": "Build/acquire the missing items into the asset library "
                     "(oeb.config.json / resolver map / camera grammar / "
                     "clip set), then re-run this scene.",
    }
    jpath = os.path.join(tdir, f"NEEDED-{scene_id}.json")
    with open(jpath, "w") as f:
        json.dump(ticket, f, indent=2)
        f.write("\n")

    lines = [f"# NEEDED — {scene_id} (episode {episode})", "",
             "This scene is BLOCKED. The script names things the asset "
             "library does not have:", ""]
    for m in missing:
        lines.append(f"- **{m['kind']}**: `{m['name']}`  ({m['source']})")
    lines += ["", f"Details: `{os.path.basename(jpath)}` alongside this file.",
              "Build the missing items, then re-run the scene.", ""]
    with open(os.path.join(tdir, f"NEEDED-{scene_id}.md"), "w") as f:
        f.write("\n".join(lines))
    return jpath


def update_report(episode, scene_id, status, **fields):
    """Merge one scene's outcome into the episode report.json; return path."""
    edir = episode_dir(episode)
    os.makedirs(edir, exist_ok=True)
    rpath = os.path.join(edir, "report.json")
    report = {"episode": episode, "scenes": {}}
    if os.path.exists(rpath):
        report = json.load(open(rpath))
    entry = {"status": status,
             "updated": datetime.datetime.now().isoformat(timespec="seconds")}
    entry.update({k: v for k, v in fields.items() if v is not None})
    report.setdefault("scenes", {})[scene_id] = entry
    report["open_tickets"] = sorted(
        e["ticket"] for e in report["scenes"].values()
        if e.get("status") == "NEEDS_ASSETS" and e.get("ticket"))
    report["updated"] = entry["updated"]
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return rpath
