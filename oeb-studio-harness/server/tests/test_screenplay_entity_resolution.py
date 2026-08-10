import importlib.util
import os
import urllib.error
from pathlib import Path


def _find_tool_path(filename: str) -> Path:
    """Same resolution order as test_blueprint_interpreter.py's
    _find_tool_path: env override, the Docker container's read-only
    /tools mount, then walking up from this file to find a sibling
    tools/ directory (bare host checkout, any nesting depth).
    """
    env_override = os.environ.get("OEB_TOOLS_DIR")
    candidates = []
    if env_override:
        candidates.append(Path(env_override) / filename)
    candidates.append(Path("/tools") / filename)
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "tools" / filename)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not locate tools/{filename}. Set OEB_TOOLS_DIR to its "
        "containing directory if running outside the repo checkout or "
        "the oeb-studio-harness-local Docker stack."
    )


def load_module():
    spec = importlib.util.spec_from_file_location(
        "screenplay_entity_resolution_for_test",
        _find_tool_path("screenplay_entity_resolution.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_entity_candidates_matches_the_plan_example_line():
    module = load_module()
    line = "JB100 flies past chased by Ellipso Flyers and Ventradi cruiser"
    assert module.extract_entity_candidates(line) == ["JB100", "Ellipso Flyers", "Ventradi"]


def test_extract_entity_candidates_excludes_sentence_initial_stopwords():
    module = load_module()
    line = "The bar door creaks open as JB100 roars past."
    assert module.extract_entity_candidates(line) == ["JB100"]


def test_extract_entity_candidates_returns_empty_for_no_entities():
    module = load_module()
    assert module.extract_entity_candidates("A lone figure emerges from the shadows.") == []


def test_extract_entity_candidates_dedupes_case_insensitively_in_first_seen_order():
    module = load_module()
    line = "JB100 banks hard. jb100 pulls up."
    assert module.extract_entity_candidates(line) == ["JB100"]


def test_extract_entity_candidates_recognizes_alphanumeric_code_names():
    module = load_module()
    line = "JB5K trails behind JB100."
    assert module.extract_entity_candidates(line) == ["JB5K", "JB100"]


def test_extract_entity_candidates_captures_single_title_case_word_mid_sentence():
    module = load_module()
    assert module.extract_entity_candidates("Ellipso approaches slowly.") == ["Ellipso"]


def test_resolve_entity_candidate_reports_resolved(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module, "get_json",
        lambda url, token=None, timeout=30: {
            "needs_clarification": False,
            "resolved": {"canonical_id": "prop_jb100_A"},
            "score": 1.0,
        },
    )
    result = module.resolve_entity_candidate("http://harness", "token", "JB100")
    assert result == {
        "entity_text": "JB100",
        "outcome": "resolved",
        "resolved": {"canonical_id": "prop_jb100_A"},
        "score": 1.0,
        "fallback_tier": None,
        "ticket_path": None,
    }


def test_resolve_entity_candidate_reports_needs_clarification(monkeypatch):
    module = load_module()
    candidates = [{"asset": {"canonical_id": "prop_ellipso_flyer_A"}, "score": 0.9}]
    monkeypatch.setattr(
        module, "get_json",
        lambda url, token=None, timeout=30: {
            "needs_clarification": True,
            "clarification_question": "Multiple matches for 'flyer' — which one?",
            "candidates": candidates,
        },
    )
    result = module.resolve_entity_candidate("http://harness", "token", "flyer")
    assert result["outcome"] == "needs_clarification"
    assert result["candidates"] == candidates
    assert result["resolved"] is None


def test_resolve_entity_candidate_reports_fallback_created(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module, "get_json",
        lambda url, token=None, timeout=30: {
            "needs_clarification": False,
            "resolved": {"canonical_id": "placeholder_prop_motorcycle_A"},
            "score": 0.0,
            "fallback_tier": 2,
            "ticket_path": "/out/.../NEEDED-placeholder_prop_motorcycle_A.json",
        },
    )
    result = module.resolve_entity_candidate("http://harness", "token", "motorcycle", fallback=True)
    assert result["outcome"] == "fallback_created"
    assert result["fallback_tier"] == 2
    assert result["ticket_path"].endswith("NEEDED-placeholder_prop_motorcycle_A.json")


def test_resolve_entity_candidate_reports_no_match_on_404(monkeypatch):
    module = load_module()

    def raise_404(url, token=None, timeout=30):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(module, "get_json", raise_404)
    result = module.resolve_entity_candidate("http://harness", "token", "meanwhile")
    assert result == {"entity_text": "meanwhile", "outcome": "no_match", "resolved": None, "candidates": []}


def test_resolve_entity_candidate_reraises_non_404_http_errors(monkeypatch):
    module = load_module()

    def raise_500(url, token=None, timeout=30):
        raise urllib.error.HTTPError(url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr(module, "get_json", raise_500)
    try:
        module.resolve_entity_candidate("http://harness", "token", "JB100")
        assert False, "expected HTTPError to propagate"
    except urllib.error.HTTPError as exc:
        assert exc.code == 500


def test_resolve_screenplay_line_entities_resolves_each_extracted_candidate(monkeypatch):
    module = load_module()
    seen_candidates = []

    def fake_resolve(harness_url, admin_token, candidate, *, kind=None, fallback=False):
        seen_candidates.append(candidate)
        return {"entity_text": candidate, "outcome": "resolved", "resolved": None,
                "score": None, "fallback_tier": None, "ticket_path": None}

    monkeypatch.setattr(module, "resolve_entity_candidate", fake_resolve)
    line = "JB100 flies past chased by Ellipso Flyers and Ventradi cruiser"
    results = module.resolve_screenplay_line_entities("http://harness", "token", line)

    assert seen_candidates == ["JB100", "Ellipso Flyers", "Ventradi"]
    assert [r["entity_text"] for r in results] == ["JB100", "Ellipso Flyers", "Ventradi"]


def test_resolve_screenplay_line_entities_returns_empty_for_no_candidates(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "resolve_entity_candidate", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert module.resolve_screenplay_line_entities("http://harness", "token", "the door creaks open") == []
