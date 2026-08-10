from types import SimpleNamespace

import pytest

from app.services.placeholder_review import apply_decision


def fake_asset(status, provenance=None):
    return SimpleNamespace(status=status, provenance=provenance, updated_at=None)


def test_reject_moves_unapproved_to_rejected():
    asset = fake_asset("unapproved")
    apply_decision(asset, "reject")
    assert asset.status == "rejected"


def test_draft_fallback_moves_unapproved_to_draft_fallback():
    asset = fake_asset("unapproved")
    apply_decision(asset, "draft_fallback")
    assert asset.status == "draft_fallback"


def test_promote_moves_unapproved_to_available():
    asset = fake_asset("unapproved")
    apply_decision(asset, "promote")
    assert asset.status == "available"


def test_promote_moves_draft_fallback_to_available():
    asset = fake_asset("draft_fallback")
    apply_decision(asset, "promote")
    assert asset.status == "available"


def test_promote_records_provenance():
    asset = fake_asset("unapproved", provenance={"source": "missing_asset_fallback", "tier": 2})
    apply_decision(asset, "promote")
    assert asset.provenance["promoted_from"] == "tier2_placeholder"
    assert asset.provenance["source"] == "missing_asset_fallback"


def test_reject_rejects_a_draft_fallback():
    with pytest.raises(ValueError):
        apply_decision(fake_asset("draft_fallback"), "reject")


def test_reject_is_terminal_no_further_decisions():
    with pytest.raises(ValueError):
        apply_decision(fake_asset("rejected"), "reject")
    with pytest.raises(ValueError):
        apply_decision(fake_asset("rejected"), "promote")


def test_unknown_decision_rejected():
    with pytest.raises(ValueError):
        apply_decision(fake_asset("unapproved"), "discard_forever")
