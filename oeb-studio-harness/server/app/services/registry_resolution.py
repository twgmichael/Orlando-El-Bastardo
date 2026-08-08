"""Tag/keyword resolution for "load X" against the asset/scene registry.

docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 6: "no need to
guess when the registry itself can answer the question directly" --
resolution is a direct lookup against each Asset's `tags`/`canonical_id`/
`name`, not embedding similarity or open-ended LLM judgment. Multiple
ambiguous matches are meant to present a chooser backed by each
candidate's own hero/review render (see review_placeholders.html /
review_scenes.html for the equivalent list-with-thumbnail pattern this
would extend).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass
class ResolutionMatch:
    asset: Asset
    score: float


def score_candidates(query: str, candidates: list[Asset]) -> list[ResolutionMatch]:
    """Pure scoring function -- no DB access -- so it's directly unit
    testable. `candidates` is normally every registry entry the caller
    cares about (assets, scenes, or both); this just ranks them.

    Scoring, highest first:
      1.0  exact canonical_id match
      0.9  full query string appears as one of the asset's own tags
      0.5 + overlap fraction  token overlap between query and
           tags/canonical_id/name (e.g. "pirate escape" partially
           matching a "pirate escape" tag split across tokens)
    Anything scoring 0 is dropped entirely, not just ranked last.
    """
    query_norm = query.strip().lower()
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    matches: list[ResolutionMatch] = []
    for asset in candidates:
        if asset.canonical_id.lower() == query_norm:
            matches.append(ResolutionMatch(asset=asset, score=1.0))
            continue

        tags = [str(tag).strip().lower() for tag in (asset.tags or [])]
        if query_norm in tags:
            matches.append(ResolutionMatch(asset=asset, score=0.9))
            continue

        haystack_tokens: set[str] = set()
        for tag in tags:
            haystack_tokens |= _tokenize(tag)
        haystack_tokens |= _tokenize(asset.canonical_id)
        if asset.name:
            haystack_tokens |= _tokenize(asset.name)

        overlap = query_tokens & haystack_tokens
        if overlap:
            fraction = len(overlap) / len(query_tokens)
            matches.append(ResolutionMatch(asset=asset, score=0.5 + 0.4 * fraction))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


AMBIGUOUS_SCORE_GAP = 0.15
"""If the top two matches score within this gap of each other, treat the
result as ambiguous (needs a chooser) rather than auto-picking the
higher one -- avoids confidently guessing between two near-equal ties.
"""


def is_ambiguous(matches: list[ResolutionMatch]) -> bool:
    if len(matches) < 2:
        return False
    return (matches[0].score - matches[1].score) < AMBIGUOUS_SCORE_GAP


async def resolve_reference(
    db: AsyncSession, query: str, *, kind: str | None = None
) -> list[ResolutionMatch]:
    """Resolve a natural-language "load X" query against the registry.
    Returns ranked matches (empty if nothing scores > 0); the caller
    decides what to do with 0 / 1 / >1 results -- see is_ambiguous().
    """
    stmt = select(Asset)
    if kind:
        stmt = stmt.where(Asset.kind == kind)
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())
    return score_candidates(query, candidates)


_LOAD_COMMAND_PATTERN = re.compile(
    r"^\s*(?:load|open|switch to|work on|pull up)\s+(?:the\s+|latest\s+)*(.+?)\s*[.!]?\s*$",
    re.IGNORECASE,
)


def detect_load_command(text: str) -> str | None:
    """Recognize a "load X" style chat message and return the bare query
    to resolve, or None if `text` doesn't look like a load command.

    Deliberately a fixed set of literal trigger verbs (load/open/switch
    to/work on/pull up), not fuzzy intent classification -- consistent
    with section 6's "no need to guess when the registry itself can
    answer the question directly": recognizing the *command* is a
    simple pattern match; only resolving *what* it refers to goes
    through the registry.
    """
    match = _LOAD_COMMAND_PATTERN.match(text)
    if not match:
        return None
    query = match.group(1).strip()
    return query or None
