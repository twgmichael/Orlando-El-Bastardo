from app.schemas.studio_chat import (
    STANDARD_REVIEW_VIEWS,
    StudioChatMessage,
    StudioChatOllamaRequest,
)
from app.services import studio_chat
from app.services.studio_chat import (
    chat_with_ollama,
    list_ollama_models,
    ollama_chat_payload,
    studio_chat_presets,
)


def test_lightweight_presets_include_oeb_translator_boundaries():
    presets = {preset.id: preset for preset in studio_chat_presets()}

    asset_builder = presets["asset_builder_translator"]

    assert "strict JSON" in asset_builder.system_prompt
    assert "+X front" in asset_builder.system_prompt
    assert "Do not write Blender code" in asset_builder.system_prompt
    assert asset_builder.temperature == 0.2


def test_ollama_chat_payload_keeps_system_prompt_and_history_visible():
    body = StudioChatOllamaRequest(
        model="oeb-qwen2.5-3b",
        system_prompt="System boundary",
        messages=[
            StudioChatMessage(role="user", content="Build a small ship."),
            StudioChatMessage(role="assistant", content='{"action":"clarify"}'),
            StudioChatMessage(role="user", content="Use two engines."),
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    payload = ollama_chat_payload(body)

    assert payload["model"] == "oeb-qwen2.5-3b"
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.1, "num_predict": 1024}
    assert payload["messages"][0] == {"role": "system", "content": "System boundary"}
    assert payload["messages"][1]["role"] == "user"
    assert payload["messages"][-1]["content"] == "Use two engines."


def test_ollama_chat_payload_adds_review_view_shortcut_context():
    body = StudioChatOllamaRequest(
        model="oeb-qwen2.5-3b",
        system_prompt="System boundary",
        messages=[StudioChatMessage(role="user", content="Render a sphere.")],
        review_views=STANDARD_REVIEW_VIEWS,
    )

    payload = ollama_chat_payload(body)
    system_message = payload["messages"][0]["content"]

    assert "OEB review-view shortcut is active" in system_message
    assert '"review_views": ["top", "bottom", "left", "right", "front", "rear", "action"]' in system_message
    assert 'especially "action", is invalid' in system_message
    assert "Do not emit axis/side pairs" in system_message


def test_review_views_normalize_back_to_rear():
    body = StudioChatOllamaRequest(
        model="oeb-qwen2.5-3b",
        messages=[StudioChatMessage(role="user", content="Render review views.")],
        review_views=["front", "back", "action", "front"],
    )

    assert body.review_views == ["front", "rear", "action"]


def test_list_ollama_models_sorts_names_and_ignores_malformed_entries(monkeypatch):
    def fake_get_json(url, timeout=10):
        assert url == "http://ollama.test/api/tags"
        return {
            "models": [
                {"name": "zeta:latest"},
                {"bad": "entry"},
                {"name": "alpha:latest"},
            ]
        }

    monkeypatch.setattr(studio_chat, "get_json", fake_get_json)

    assert list_ollama_models("http://ollama.test") == ["alpha:latest", "zeta:latest"]


def test_chat_with_ollama_returns_message_and_raw_metadata(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, token=None, timeout=60):
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {
            "model": "oeb-qwen2.5-3b",
            "message": {"role": "assistant", "content": "ready"},
            "done": True,
            "eval_count": 12,
        }

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)

    body = StudioChatOllamaRequest(
        model="oeb-qwen2.5-3b",
        messages=[StudioChatMessage(role="user", content="hello")],
    )
    response = chat_with_ollama("http://ollama.test", body, timeout=9)

    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["timeout"] == 9
    assert response.message.content == "ready"
    assert response.raw["request"] == captured["payload"]
    assert response.raw["response"]["eval_count"] == 12
