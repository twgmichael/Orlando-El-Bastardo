from app.schemas.studio_chat import (
    STANDARD_REVIEW_VIEWS,
    StudioChatMessage,
    StudioChatOllamaRequest,
    StudioChatThreadCreateRequest,
)
from app.routers.studio_chat import _thread_title_from_prompt
from app.services import studio_chat
from app.services.studio_chat import (
    build_spec_from_assistant_response,
    build_spec_with_primitive_resolver,
    chat_with_ollama,
    list_ollama_models,
    ollama_chat_payload,
    parse_assistant_json,
    primitive_registry,
    resolve_primitive_spec,
    studio_chat_presets,
    validate_primitive_spec,
)


def test_lightweight_presets_include_oeb_translator_boundaries():
    presets = {preset.id: preset for preset in studio_chat_presets()}

    asset_builder = presets["asset_builder_translator"]
    primitive_resolver = presets["primitive_shape_resolver"]

    assert "strict JSON" in asset_builder.system_prompt
    assert "+X front" in asset_builder.system_prompt
    assert "Do not write Blender code" in asset_builder.system_prompt
    assert asset_builder.temperature == 0.2
    assert "PrimitiveRegistry v0.1" in primitive_resolver.system_prompt
    assert primitive_resolver.temperature == 0.1


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


def test_thread_create_request_normalizes_review_views():
    body = StudioChatThreadCreateRequest(review_views=["front", "back", "action", "front"])

    assert body.review_views == ["front", "rear", "action"]


def test_thread_title_from_prompt_is_short_and_readable():
    assert _thread_title_from_prompt("Build a yellow cone with a white sphere on top.") == (
        "Build a yellow cone with a white sphere"
    )


def test_parse_assistant_json_accepts_fenced_json():
    parsed = parse_assistant_json(
        """```json
{"action": "render_sphere", "build_job": {"type": "sphere"}}
```"""
    )

    assert parsed["action"] == "render_sphere"
    assert parsed["build_job"]["type"] == "sphere"


def test_build_spec_from_assistant_response_preserves_sphere_scene_object():
    spec, parsed = build_spec_from_assistant_response(
        "Render a sphere",
        """{
          "action": "render_sphere",
          "build_job": {
            "type": "sphere",
            "canonical_id": "prop_sphere_test_A",
            "name": "Sphere Test A",
            "asset_kind": "prop"
          }
        }""",
    )

    assert parsed["action"] == "render_sphere"
    assert spec.canonical_id == "prop_sphere_test_A"
    assert spec.kind == "prop"
    assert spec.components == ["sphere"]
    assert spec.scene_plan is not None
    assert spec.scene_plan.objects[0].category == "sphere"
    assert spec.scene_plan.objects[0].shape == {"primary_form": "sphere"}
    assert "asset_review_renders" in spec.deliverables


def test_validate_primitive_spec_normalizes_cube_alias_to_box():
    resolved = validate_primitive_spec(
        {
            "asset_kind": "prop",
            "canonical_id": "prop_cube_blue_A",
            "name": "Blue Cube",
            "primitives": [
                {
                    "id": "main_cube",
                    "type": "cube",
                    "material": "blue",
                    "transform": {"location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                }
            ],
        },
        "Build a blue cube.",
    )

    assert primitive_registry()["version"] == "0.1"
    assert resolved["primitives"][0]["type"] == "box"
    assert resolved["primitives"][0]["material"] == "blue"


def test_build_spec_with_primitive_resolver_prefers_assistant_primitives():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build a blue cube.",
        """{
          "action": "build",
          "build_job": {
            "canonical_id": "prop_cube_blue_A",
            "name": "Blue Cube",
            "primitives": [
              {"id": "main_cube", "type": "cube", "material": "blue"}
            ]
          }
        }""",
    )

    assert parsed["action"] == "build"
    assert resolver["source"] == "assistant_json"
    assert spec.primitives[0].type == "box"
    assert spec.primitives[0].material == "blue"
    assert spec.components == ["box"]


def test_malformed_multi_primitive_response_falls_back_to_compound_primitives():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build a yellow cone with a white sphere on top, keep both vertical.",
        """```json
{
  "action": "build",
  "build_job": {
    "type": "cone",
    "color": "yellow",
    "height": 2.0, // bad local-model comment
    "type": "sphere",
    "color": "white",
    "position": [0, 0, 2]
  }
}
```""",
    )

    assert parsed["action"] == "fallback_intent"
    assert resolver["source"] == "fallback_intent"
    assert spec.components == ["cone", "sphere"]
    assert [primitive.type for primitive in spec.primitives] == ["cone", "sphere"]
    assert [primitive.material for primitive in spec.primitives] == ["yellow", "white"]
    assert spec.primitives[1].transform.location[2] > spec.primitives[0].transform.location[2]


def test_explicit_cone_pointing_down_overrides_zero_rotation():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build a yellow cone pointing down with a white sphere on top.",
        """```json
{
  "action": "build",
  "build_job": {
    "type": "cone",
    "color": "#FFFF00", // Yellow
    "position": [0, 0, -2],
    "scale": [1, 1, 1]
  },
  "build_job": {
    "type": "sphere",
    "color": "#FFFFFF", // White
    "position": [0, 0.5, -2],
    "scale": [1, 1, 1]
  }
}
```""",
    )

    assert parsed["action"] == "fallback_intent"
    assert resolver["resolved"]["primitives"][0]["orientation"]["direction"] == "down"
    assert spec.primitives[0].type == "cone"
    assert spec.primitives[0].transform.rotation == [3.141592654, 0.0, 0.0]
    assert spec.primitives[1].type == "sphere"
    assert spec.primitives[1].transform.rotation == [0.0, 0.0, 0.0]


def test_resolver_output_cone_pointing_down_is_normalized_even_when_model_misses_rotation():
    resolved = validate_primitive_spec(
        {
            "asset_kind": "prop",
            "canonical_id": "prop_cone_down_A",
            "name": "Cone Down",
            "primitives": [
                {
                    "id": "cone_1",
                    "type": "cone",
                    "material": "yellow",
                    "transform": {"location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                    "params": {"depth": 1},
                }
            ],
        },
        "Build a yellow cone pointing down.",
    )

    assert resolved["primitives"][0]["transform"]["rotation"] == [3.141592654, 0.0, 0.0]
    assert resolved["primitives"][0]["orientation"]["source"] == "creative_request"


def test_resolve_primitive_spec_retries_once_after_invalid_output(monkeypatch):
    calls = []

    def fake_post_json(url, payload, token=None, timeout=60):
        calls.append(payload)
        content = (
            '{"version":"0.1","primitives":[{"type":"imaginary"}]}'
            if len(calls) == 1
            else '{"version":"0.1","asset_kind":"prop","canonical_id":"prop_cone_yellow_A","name":"Yellow Cone","primitives":[{"id":"main_cone","type":"cone","material":"yellow"}]}'
        )
        return {"message": {"role": "assistant", "content": content}, "done": True}

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)

    resolved = resolve_primitive_spec(
        "http://ollama.test",
        "oeb-qwen2.5-3b",
        "Build a yellow cone.",
        '{"action":"build","build_job":{"type":"cone"}}',
        max_retries=1,
    )

    assert resolved["ok"] is True
    assert len(calls) == 2
    assert "validation_error" in calls[1]["messages"][1]["content"]
    assert resolved["attempts"][0]["request"] == calls[0]
    assert resolved["attempts"][0]["raw"]["message"]["content"] == '{"version":"0.1","primitives":[{"type":"imaginary"}]}'
    assert resolved["attempts"][1]["request"] == calls[1]
    assert resolved["attempts"][1]["raw"]["done"] is True
    assert resolved["attempts"][1]["content"].startswith('{"version":"0.1"')
    assert resolved["resolved"]["primitives"][0]["type"] == "cone"


def test_build_spec_falls_back_from_malformed_json_for_blue_cube():
    spec, parsed = build_spec_from_assistant_response(
        "Make the cube blue.",
        '{"action":"edit_asset","build_job":{"type":"cube" "materials":{"primary":"blue"}}}',
        messages=[],
    )

    assert parsed["action"] == "fallback_intent"
    assert parsed["fallback_reason"] == "assistant_json_invalid"
    assert spec.canonical_id == "prop_box_blue_A"
    assert spec.kind == "prop"
    assert spec.components == ["box"]
    assert spec.scene_plan is not None
    assert spec.scene_plan.objects[0].category == "box"
    assert spec.scene_plan.objects[0].materials == {"primary": "blue"}
    assert "blue" in spec.scene_plan.objects[0].style_details


def test_build_spec_fallback_uses_recent_context_for_pronoun_edit():
    spec, parsed = build_spec_from_assistant_response(
        "Make it blue.",
        "not json",
        messages=[
            StudioChatMessage(role="user", content="Build a cube."),
            StudioChatMessage(role="assistant", content='{"action":"render_cube","build_job":{"type":"cube"}}'),
        ],
    )

    assert parsed["action"] == "fallback_intent"
    assert parsed["build_job"]["type"] == "box"
    assert spec.canonical_id == "prop_box_blue_A"
    assert spec.scene_plan is not None
    assert spec.scene_plan.objects[0].category == "box"
    assert spec.scene_plan.objects[0].materials == {"primary": "blue"}


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
