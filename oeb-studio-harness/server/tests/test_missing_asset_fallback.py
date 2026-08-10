import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.asset import Asset
from app.services.missing_asset_fallback import (
    build_needed_ticket,
    default_placeholder_blueprint,
    normalize_via_standins,
    resolve_missing_asset,
    resolve_needed_ticket,
    slugify_placeholder_id,
    write_needed_ticket,
)

FAKE_STANDINS = {
    "location_standins": {
        "orbital_station_lounge": "small_bar_interior",
    },
    "cast": {
        "hero": "protagonist",
    },
}


def test_normalize_via_standins_matches_location():
    assert normalize_via_standins("orbital_station_lounge", FAKE_STANDINS) == "small_bar_interior"


def test_normalize_via_standins_is_punctuation_and_case_insensitive():
    assert normalize_via_standins("Orbital Station Lounge!", FAKE_STANDINS) == "small_bar_interior"


def test_normalize_via_standins_returns_none_for_unknown_query():
    assert normalize_via_standins("something never seen before", FAKE_STANDINS) is None


def test_slugify_placeholder_id_is_deterministic_and_reusable():
    a = slugify_placeholder_id("motorcycle", "prop")
    b = slugify_placeholder_id("Motorcycle!!", "prop")
    assert a == b == "placeholder_prop_motorcycle_A"


def test_default_placeholder_blueprint_is_deliberately_crude():
    bp = default_placeholder_blueprint("placeholder_prop_cup_A", "prop", "cup")
    assert bp["canonical_id"] == "placeholder_prop_cup_A"
    assert len(bp["primitives"]) == 1
    assert bp["operations"] == []


def test_needed_ticket_carries_the_placeholder_canonical_id_both_ways():
    ticket = build_needed_ticket("placeholder_prop_cup_A", "cup", "prop", requested_by="test-producer")
    assert ticket["placeholder_canonical_id"] == "placeholder_prop_cup_A"
    assert ticket["missing"][0]["name"] == "cup"
    assert ticket["status"] == "NEEDS_ASSET"


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class FakeSession:
    """Minimal db double: `execute` returns pre-set Asset rows (tier-1
    candidates), `add`/`flush` behave like a real AsyncSession for the
    one new placeholder tier-2 creates.
    """

    def __init__(self, existing_assets):
        self.existing_assets = existing_assets
        self.added = []

    async def execute(self, _stmt):
        return _FakeResult(self.existing_assets)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(timezone.utc)
                obj.updated_at = datetime.now(timezone.utc)


def fake_existing_asset(canonical_id, kind, tags):
    return Asset(
        id=uuid.uuid4(), canonical_id=canonical_id, kind=kind, status="available",
        tags=tags, asset_metadata={}, provenance=None,
    )


@pytest.mark.anyio
async def test_tier1_standin_resolves_to_existing_asset_no_ticket():
    bar = fake_existing_asset("set_bar_small_A", "set", ["small_bar_interior", "bar"])
    db = FakeSession([bar])

    outcome = await resolve_missing_asset(
        db, "orbital_station_lounge", "set", standins=FAKE_STANDINS,
    )

    assert outcome.tier == 1
    assert outcome.asset is bar
    assert outcome.ticket_path is None
    assert db.added == []


@pytest.mark.anyio
async def test_tier1_direct_registry_match_without_standin():
    jb100 = fake_existing_asset("prop_jb100_A", "prop", ["jb100"])
    db = FakeSession([jb100])

    outcome = await resolve_missing_asset(db, "jb100", "prop", standins={})

    assert outcome.tier == 1
    assert outcome.asset is jb100


@pytest.mark.anyio
async def test_tier2_creates_unapproved_placeholder_with_linked_ticket(tmp_path, monkeypatch):
    import app.services.missing_asset_fallback as fallback_module
    monkeypatch.setattr(fallback_module, "_tickets_root", lambda: tmp_path / "out" / "production" / "studio_chat_placeholders" / "tickets")

    db = FakeSession([])  # nothing in the registry at all

    outcome = await resolve_missing_asset(
        db, "motorcycle", "prop", requested_by="test-producer", standins={},
    )

    assert outcome.tier == 2
    assert outcome.created is True
    assert outcome.asset.status == "unapproved"
    assert outcome.asset.canonical_id == "placeholder_prop_motorcycle_A"
    assert outcome.ticket_path is not None
    assert outcome.asset.asset_metadata["needed_ticket"] == outcome.ticket_path
    assert (tmp_path / "out" / "production" / "studio_chat_placeholders" / "tickets"
            / "NEEDED-placeholder_prop_motorcycle_A.json").is_file()
    assert db.added == [outcome.asset]


def _write_fixture_ticket(tmp_path):
    ticket = build_needed_ticket("placeholder_prop_cup_A", "cup", "prop", "test-producer")
    ticket_path = write_needed_ticket(ticket, tickets_root=tmp_path)
    return ticket_path


def test_resolve_needed_ticket_marks_status_resolved(tmp_path):
    ticket_path = _write_fixture_ticket(tmp_path)

    resolve_needed_ticket(ticket_path)

    resolved = json.loads((tmp_path / "NEEDED-placeholder_prop_cup_A.json").read_text())
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolution"] == "promoted_to_tier1"
    assert "resolved_at" in resolved


def test_resolve_needed_ticket_appends_note_to_markdown(tmp_path):
    ticket_path = _write_fixture_ticket(tmp_path)

    resolve_needed_ticket(ticket_path)

    md = (tmp_path / "NEEDED-placeholder_prop_cup_A.md").read_text()
    assert "RESOLVED" in md
    assert "placeholder_prop_cup_A" in md


def test_resolve_needed_ticket_is_idempotent(tmp_path):
    ticket_path = _write_fixture_ticket(tmp_path)

    resolve_needed_ticket(ticket_path)
    first_resolved_at = json.loads(Path(ticket_path).read_text())["resolved_at"]
    resolve_needed_ticket(ticket_path)
    second_resolved_at = json.loads(Path(ticket_path).read_text())["resolved_at"]

    assert first_resolved_at == second_resolved_at
    md = (tmp_path / "NEEDED-placeholder_prop_cup_A.md").read_text()
    assert md.count("RESOLVED") == 1


def test_resolve_needed_ticket_missing_file_is_a_noop(tmp_path):
    resolve_needed_ticket(str(tmp_path / "NEEDED-does-not-exist.json"))
