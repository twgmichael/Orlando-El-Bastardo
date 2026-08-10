#!/usr/bin/env python3
"""
screenplay_entity_resolution.py -- section 6's "automatic composition"
entity-resolution half: for a screenplay/action line like "JB100 flies
past chased by Ellipso Flyers and Ventradi cruiser", extract each
named/described entity mention and resolve it independently against
the registry, over HTTP against the same `GET /api/v1/registry/resolve`
endpoint the chat "load X" chooser (section 6's other half) and
Producer already use -- no second resolution mechanism invented.

Deliberately NOT the other half of section 6/8: turning the resolved
set into "import" primitives in a scene-scoped Blueprint with
spatial/motion relationships. This module only answers "what does each
mention refer to" -- entity_text -> resolved asset / ambiguous
candidates / no match / fallback placeholder. Composing that into a
Blueprint is a separate, not-yet-built step.

Extraction is deliberately simple, consistent with section 6's own
"resolution is tag/keyword lookup... not fuzzy guessing" stance:
- Alphanumeric code names with a digit (JB100, JB5K) -- this project's
  own naming convention for hero ships, unambiguous regardless of
  sentence position.
- Runs of consecutive Title-Case words, excluding a small stopword
  list (articles/pronouns/conjunctions/prepositions) so ordinary
  sentence-initial capitalization ("The bar door creaks open") doesn't
  get treated as an entity mention.

Over-extraction is fine by design for candidates the registry actually
matches (score 0 = silently dropped by score_candidates, not
escalated) -- but auto-registering a tier-2 placeholder (section 7) for
every stray capitalized word a screenplay line happens to contain (a
transition adverb, a scene-heading fragment) would be genuinely noisy,
not "no need to guess." `resolve_screenplay_line_entities` therefore
defaults `fallback=False`: unmatched candidates report outcome
"no_match" rather than silently minting a placeholder+ticket. A caller
that has already decided a specific candidate is a real staged entity
(the not-yet-built Blueprint-assembly half) opts in explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "so", "yet",
    "he", "she", "it", "they", "we", "i", "you",
    "his", "her", "its", "their", "our", "your", "my",
    "this", "that", "these", "those",
    "in", "on", "at", "by", "for", "of", "to", "with", "from", "as",
}

_CODE_NAME_RE = r"[A-Z]{1,6}[0-9]{1,4}[A-Z]{0,3}"
_TOKEN_PATTERN = re.compile(rf"{_CODE_NAME_RE}\b|[A-Za-z']+")
_CODE_NAME_PATTERN = re.compile(_CODE_NAME_RE)


def extract_entity_candidates(line: str) -> list[str]:
    """Return candidate entity phrases from *line*, in first-seen order,
    deduplicated case-insensitively. See module docstring for the
    (deliberately simple, over-generating-by-design) extraction rule.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)

    run: list[str] = []

    def flush_run() -> None:
        if run:
            add(" ".join(run))
            run.clear()

    for token_match in _TOKEN_PATTERN.finditer(line):
        token = token_match.group(0)
        if _CODE_NAME_PATTERN.fullmatch(token):
            flush_run()
            add(token)
            continue
        if token[0].isupper() and token.lower() not in _STOPWORDS:
            run.append(token)
        else:
            flush_run()
    flush_run()

    return candidates


def get_json(url: str, token: str | None = None, timeout: int = 30) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_entity_candidate(
    harness_url: str,
    admin_token: str,
    candidate: str,
    *,
    kind: str | None = None,
    fallback: bool = False,
) -> dict:
    """One candidate through `GET /api/v1/registry/resolve` -- the same
    endpoint and outcome shapes (`needs_clarification` / a direct
    resolution / a tier-2 fallback registration) the chat "load X"
    chooser already uses, so a screenplay-driven mention and a
    human-typed "load X" behave identically once they reach the
    registry.
    """
    params = {"q": candidate}
    if kind:
        params["kind"] = kind
    if fallback:
        params["fallback"] = "true"
    url = f"{harness_url.rstrip('/')}/api/v1/registry/resolve?{urllib.parse.urlencode(params)}"
    try:
        response = get_json(url, token=admin_token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"entity_text": candidate, "outcome": "no_match", "resolved": None, "candidates": []}
        raise

    if response.get("needs_clarification"):
        return {
            "entity_text": candidate,
            "outcome": "needs_clarification",
            "resolved": None,
            "candidates": response.get("candidates", []),
        }
    return {
        "entity_text": candidate,
        "outcome": "fallback_created" if response.get("fallback_tier") else "resolved",
        "resolved": response.get("resolved"),
        "score": response.get("score"),
        "fallback_tier": response.get("fallback_tier"),
        "ticket_path": response.get("ticket_path"),
    }


def resolve_screenplay_line_entities(
    harness_url: str,
    admin_token: str,
    line: str,
    *,
    kind: str | None = None,
    fallback: bool = False,
) -> list[dict]:
    """Extract every candidate entity mention in *line* and resolve each
    one independently -- section 6's "each named/described entity in
    the sentence resolves independently to the closest matching
    registered asset (or triggers the fallback in section 7)".
    """
    return [
        resolve_entity_candidate(harness_url, admin_token, candidate, kind=kind, fallback=fallback)
        for candidate in extract_entity_candidates(line)
    ]


def parse_args():
    parser = argparse.ArgumentParser(prog="screenplay_entity_resolution")
    parser.add_argument("--line", required=True, help="screenplay/action line to resolve entities in")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL"))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN"))
    parser.add_argument("--kind", default=None)
    parser.add_argument(
        "--fallback", action="store_true",
        help="register a tier-2 placeholder for any candidate that doesn't match (see module docstring)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.harness_url or not args.admin_token:
        print("[screenplay_entity_resolution] ERROR: set OEB_HARNESS_URL and API_ADMIN_TOKEN", file=sys.stderr)
        return 2
    results = resolve_screenplay_line_entities(
        args.harness_url, args.admin_token, args.line, kind=args.kind, fallback=args.fallback,
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
