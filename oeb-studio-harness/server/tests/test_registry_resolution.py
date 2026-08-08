from types import SimpleNamespace

from app.services.registry_resolution import detect_load_command, is_ambiguous, score_candidates


def test_detect_load_command_recognizes_load_verb():
    assert detect_load_command("load jb100") == "jb100"


def test_detect_load_command_recognizes_other_trigger_verbs():
    assert detect_load_command("open the pirate escape scene") == "pirate escape scene"
    assert detect_load_command("switch to jb100") == "jb100"
    assert detect_load_command("work on the latest pirate escape") == "pirate escape"
    assert detect_load_command("pull up jb100") == "jb100"


def test_detect_load_command_is_case_insensitive_and_strips_punctuation():
    assert detect_load_command("Load JB100.") == "JB100"


def test_detect_load_command_returns_none_for_a_build_request():
    assert detect_load_command("Build a two-wheeled motorcycle with a low frame.") is None


def test_detect_load_command_returns_none_for_empty_query():
    assert detect_load_command("load") is None
    assert detect_load_command("load   ") is None


def fake_asset(canonical_id, name=None, tags=None):
    return SimpleNamespace(canonical_id=canonical_id, name=name, tags=tags or [])


def test_exact_canonical_id_scores_highest():
    jb100 = fake_asset("prop_jb100_A", name="JB100")
    other = fake_asset("prop_jb5k_A", name="JB5K")

    matches = score_candidates("prop_jb100_A", [jb100, other])

    assert matches[0].asset is jb100
    assert matches[0].score == 1.0
    assert not is_ambiguous(matches)


def test_tag_match_resolves_a_nickname():
    jb100 = fake_asset("prop_jb100_A", name="JB100", tags=["jb100", "hero ship"])
    other = fake_asset("prop_jb5k_A", name="JB5K", tags=["jb5k"])

    matches = score_candidates("jb100", [jb100, other])

    assert matches[0].asset is jb100
    assert not is_ambiguous(matches)


def test_multi_word_tag_query_resolves_a_scene():
    pirate = fake_asset(
        "scene_pirate_escape_A",
        tags=["pirate escape", "jb100", "ellipso flyer", "ventradi cruiser", "chase"],
    )
    title = fake_asset("scene_oeb_title_A", tags=["oeb title", "title sequence"])

    matches = score_candidates("pirate escape", [pirate, title])

    assert matches[0].asset is pirate
    assert not is_ambiguous(matches)


def test_close_scores_are_ambiguous_and_present_a_chooser():
    flyer_a = fake_asset("prop_ellipso_flyer_A", tags=["ellipso flyer", "flyer"])
    flyer_b = fake_asset("prop_ellipso_flyer_B", tags=["ellipso flyer", "flyer"])

    matches = score_candidates("flyer", [flyer_a, flyer_b])

    assert len(matches) == 2
    assert is_ambiguous(matches)


def test_no_match_returns_empty():
    jb100 = fake_asset("prop_jb100_A", tags=["jb100"])

    matches = score_candidates("something completely unrelated", [jb100])

    assert matches == []


def test_single_match_is_not_ambiguous():
    only = fake_asset("prop_jb100_A", tags=["jb100"])

    matches = score_candidates("jb100", [only])

    assert not is_ambiguous(matches)
