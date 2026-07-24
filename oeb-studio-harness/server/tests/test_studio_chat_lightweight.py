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

    assert "valid JSON asset intent" in asset_builder.system_prompt
    assert "Do not collapse objects into generic boxes unless the user explicitly asks for a box" in asset_builder.system_prompt
    assert "small buildable primitive jobs" not in asset_builder.system_prompt
    assert "asset_intent may be rich and descriptive" in asset_builder.system_prompt
    assert "+X front" in asset_builder.system_prompt
    assert "Do not write Blender code" in asset_builder.system_prompt
    assert asset_builder.temperature == 0.2
    assert "Preserve asset intent" in primitive_resolver.system_prompt
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


def test_validate_primitive_spec_expands_quantity_with_stable_offsets():
    resolved = validate_primitive_spec(
        {
            "asset_kind": "prop",
            "canonical_id": "prop_spheres_blue_A",
            "name": "Blue Spheres",
            "primitives": [
                {
                    "id": "sphere",
                    "type": "sphere",
                    "material": "blue",
                    "quantity": 2,
                    "transform": {"location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                }
            ],
        },
        "Build 2 blue balls.",
    )

    assert [primitive["id"] for primitive in resolved["primitives"]] == ["sphere_1", "sphere_2"]
    assert [primitive["material"] for primitive in resolved["primitives"]] == ["blue", "blue"]
    assert [primitive["type"] for primitive in resolved["primitives"]] == ["sphere", "sphere"]
    assert resolved["primitives"][0]["transform"]["location"] == [0.0, -0.625, 0.5]
    assert resolved["primitives"][1]["transform"]["location"] == [0.0, 0.625, 0.5]


def test_validate_primitive_spec_coerces_primitive_kind_and_top_level_transform_aliases():
    resolved = validate_primitive_spec(
        {
            "asset_kind": "primitive",
            "canonical_id": "ship_letter_a_A",
            "name": "A Letter Start",
            "primitives": [
                {
                    "id": "draft_mark",
                    "type": "cone",
                    "size": [0.5, 2, 0.5],
                    "position": [-1, -1, 0.75],
                    "rotation": [3.141592654, 0, 0],
                }
            ],
        },
        "We are going to build a spaceship. Start with the letter A on the vertical.",
    )

    assert resolved["asset_kind"] == "vehicle"
    assert resolved["asset_intent"]["asset_kind"] == "primitive"
    assert resolved["primitives"][0]["transform"]["location"] == [-1.0, -1.0, 0.75]
    assert resolved["primitives"][0]["transform"]["scale"] == [0.5, 2.0, 0.5]


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


def test_broad_asset_intent_skips_geometry_resolver_and_preserves_letter_a_vertical(monkeypatch):
    def fail_if_called(url, payload, token=None, timeout=60):
        raise AssertionError("broad asset prompt should not call the geometry resolver")

    monkeypatch.setattr(studio_chat, "post_json", fail_if_called)

    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "We are going to build a spaceship. Start with the letter A on the vertical.",
        """```json
{
  "action": "build",
  "confidence": 1,
  "clarification_question": null,
  "escalation_reason": null,
  "build_job": {
    "type": "primitive",
    "size": [0.5, 2, 0.5],
    "position": [-1, -1, 0.75],
    "rotation": [3.141592654, 0, 0]
  }
}
```""",
        ollama_url="http://ollama.test",
        model="oeb-qwen2.5-3b",
    )

    assert parsed["action"] == "build"
    assert resolver["source"] == "asset_intent_normalizer"
    assert spec.kind == "vehicle"
    assert spec.asset_intent["type"] == "primitive"
    assert spec.scene_plan is not None
    scene_object = spec.scene_plan.objects[0]
    assert scene_object.category == "vehicle"
    assert scene_object.shape["silhouette"] == "letter_a"
    assert "letter_a_silhouette" in scene_object.required_features
    assert scene_object.orientation == {"axis": "vertical", "direction": "+Z"}
    assert any("letter_a" in component for component in spec.components)


def test_construction_graph_compiles_generic_letter_z_from_data():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build the letter Z.",
        """```json
{
  "action": "build",
  "confidence": 1,
  "clarification_question": null,
  "escalation_reason": null,
  "asset_intent": {
    "name": "Block letter Z",
    "construction_graph": {
      "units": "relative",
      "elements": [
        {"id": "top_stroke", "kind": "stroke", "from": [0, -0.55, 1.4], "to": [0, 0.55, 1.4], "thickness": 0.14, "material": "neutral"},
        {"id": "diagonal_stroke", "kind": "stroke", "from": [0, 0.55, 1.4], "to": [0, -0.55, 0.2], "thickness": 0.14, "material": "neutral"},
        {"id": "bottom_stroke", "kind": "stroke", "from": [0, -0.55, 0.2], "to": [0, 0.55, 0.2], "thickness": 0.14, "material": "neutral"}
      ],
      "construction_notes": "A block Z made from top, diagonal, and bottom strokes."
    }
  }
}
```""",
        ollama_url="http://ollama.test",
        model="oeb-qwen2.5-3b",
    )

    assert parsed["action"] == "build"
    assert resolver["source"] == "asset_intent_normalizer"
    assert [primitive.id for primitive in spec.primitives] == ["top_stroke", "diagonal_stroke", "bottom_stroke"]
    assert [primitive.type for primitive in spec.primitives] == ["box", "box", "box"]
    assert spec.primitives[1].transform.rotation[0] < 0
    assert "diagonal_stroke" in spec.components
    assert "asset_review_renders" in spec.deliverables


def test_construction_graph_compiles_generic_diagonal_strokes():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build a capital letter V.",
        """```json
{
  "action": "build",
  "confidence": 1,
  "clarification_question": null,
  "escalation_reason": null,
  "asset_intent": {
    "name": "Block letter V",
    "construction_graph": {
      "units": "relative",
      "elements": [
        {"id": "left_stroke", "kind": "stroke", "from": [0, -0.5, 1.4], "to": [0, 0, 0.2], "thickness": 0.14},
        {"id": "right_stroke", "kind": "stroke", "from": [0, 0.5, 1.4], "to": [0, 0, 0.2], "thickness": 0.14}
      ]
    }
  }
}
```""",
        ollama_url="http://ollama.test",
        model="oeb-qwen2.5-3b",
    )

    assert parsed["action"] == "build"
    assert resolver["source"] == "asset_intent_normalizer"
    assert [primitive.id for primitive in spec.primitives] == ["left_stroke", "right_stroke"]
    assert spec.primitives[0].transform.rotation[0] > 0
    assert spec.primitives[1].transform.rotation[0] < 0
    assert spec.scene_plan is not None
    assert spec.scene_plan.objects[0].shape["construction_graph"]["elements"][0]["id"] == "left_stroke"


def test_rich_asset_intent_construction_graph_preserves_parts_and_compiles():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build the letter C.",
        """```json
{
  "action": "build",
  "confidence": 0.92,
  "clarification_question": null,
  "escalation_reason": null,
  "asset_intent": {
    "name": "capital letter C",
    "kind": "asset",
    "description": "A freestanding block-style capital C with the open side facing right.",
    "construction_graph": {
      "units": "relative",
      "elements": [
        {"id": "left_spine", "kind": "stroke", "from": [0, -0.5, 1.4], "to": [0, -0.5, 0.2], "thickness": 0.14},
        {"id": "upper_stroke", "kind": "stroke", "from": [0, -0.5, 1.4], "to": [0, 0.45, 1.4], "thickness": 0.14},
        {"id": "lower_stroke", "kind": "stroke", "from": [0, -0.5, 0.2], "to": [0, 0.45, 0.2], "thickness": 0.14}
      ]
    },
    "materials": [{"target": "whole_asset", "material": "neutral"}],
    "parts": [
      {"id": "left_spine", "role": "vertical spine"},
      {"id": "upper_stroke", "role": "top horizontal stroke"},
      {"id": "lower_stroke", "role": "bottom horizontal stroke"}
    ],
    "relationships": [
      {"subject": "upper_stroke", "relation": "attached_to", "target": "left_spine"},
      {"subject": "lower_stroke", "relation": "attached_to", "target": "left_spine"}
    ],
    "construction_notes": "Compile semantic letter intent into deterministic strokes downstream."
  }
}
```""",
        ollama_url="http://ollama.test",
        model="oeb-qwen2.5-3b",
    )

    assert parsed["action"] == "build"
    assert resolver["source"] == "asset_intent_normalizer"
    assert spec.asset_intent["construction_graph"]["elements"][0]["id"] == "left_spine"
    assert spec.asset_intent["parts"][0]["id"] == "left_spine"
    assert [primitive.id for primitive in spec.primitives] == ["left_spine", "upper_stroke", "lower_stroke"]
    assert all(primitive.type == "box" for primitive in spec.primitives)
    assert spec.scene_plan is not None
    assert spec.scene_plan.objects[0].shape["construction_graph"]["elements"][0]["id"] == "left_spine"
    assert "asset_review_renders" in spec.deliverables


def test_asset_intent_feedback_loop_repairs_directional_intent_to_construction_graph(monkeypatch):
    requests = []

    def fake_post_json(url, payload, token=None, timeout=60):
        requests.append(payload)
        return {
            "message": {
                "content": """{
                  "construction_graph": {
                    "units": "relative",
                    "elements": [
                      {"id": "top_stroke", "kind": "stroke", "from": [0, -0.55, 1.4], "to": [0, 0.55, 1.4], "thickness": 0.14},
                      {"id": "diagonal_stroke", "kind": "stroke", "from": [0, 0.55, 1.4], "to": [0, -0.55, 0.2], "thickness": 0.14},
                      {"id": "bottom_stroke", "kind": "stroke", "from": [0, -0.55, 0.2], "to": [0, 0.55, 0.2], "thickness": 0.14}
                    ],
                    "construction_notes": "A Z made from top, diagonal, and bottom strokes."
                  },
                  "parts": [
                    {"id": "top_stroke", "role": "top stroke"},
                    {"id": "diagonal_stroke", "role": "diagonal stroke"},
                    {"id": "bottom_stroke", "role": "bottom stroke"}
                  ]
                }"""
            },
            "done": True,
        }

    monkeypatch.setattr(studio_chat, "post_json", fake_post_json)

    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build the letter Z.",
        """{
          "action": "build",
          "asset_intent": {
            "name": "Z-shaped structure",
            "parts": [
              {"name": "top", "orientation": {"x": 0, "y": 1, "z": 0}},
              {"name": "diagonal", "orientation": {"x": 0, "y": -1, "z": -1}},
              {"name": "bottom", "orientation": {"x": 0, "y": 1, "z": 0}}
            ],
            "construction_notes": "Directional-part geometry for a Z.",
            "semantic_geometry": {
              "top": {"x": 0, "y": 1, "z": 0},
              "diagonal": {"x": 0, "y": -1, "z": -1},
              "bottom": {"x": 0, "y": 1, "z": 0}
            }
          },
          "clarification_question": null,
          "escalation_reason": null,
          "confidence": 1
        }""",
        ollama_url="http://ollama.test",
        model="oeb-qwen2.5-3b",
        resolver_retries=1,
    )

    assert parsed["action"] == "build"
    assert resolver["ok"] is True
    assert resolver["source"] == "asset_intent_feedback_loop"
    assert len(resolver["attempts"]) == 1
    assert "Normalize this asset_intent into a compiler-friendly construction graph" in (
        requests[0]["messages"][1]["content"]
    )
    assert spec.asset_intent["semantic_geometry"]["diagonal"] == {"x": 0, "y": -1, "z": -1}
    assert spec.asset_intent["construction_graph"]["elements"][1]["id"] == "diagonal_stroke"
    assert spec.asset_intent["parts"][0]["name"] == "top"
    assert spec.asset_intent["compiler_parts"][0]["id"] == "top_stroke"
    assert [primitive.id for primitive in spec.primitives] == ["top_stroke", "diagonal_stroke", "bottom_stroke"]
    assert "asset_review_renders" in spec.deliverables


def test_asset_intent_without_style_gets_defensive_defaults_and_preserves_fields():
    spec, parsed = build_spec_from_assistant_response(
        "Build a strange green usable item with asymmetric greebles.",
        """{
          "action": "build",
          "build_job": {
            "type": "primitive",
            "size": "small",
            "materials": {"primary": "green"},
            "features": ["handle", "asymmetric greebles"]
          }
        }""",
    )

    assert parsed["action"] == "build"
    assert spec.style == "Build a strange green usable item with asymmetric greebles."
    assert spec.kind == "asset"
    assert spec.asset_intent["type"] == "primitive"
    assert spec.asset_intent["materials"] == {"primary": "green"}
    assert spec.scene_plan is not None
    assert spec.scene_plan.objects[0].materials == {"primary": "green"}
    assert "handle" in spec.scene_plan.objects[0].required_features
    assert "asymmetric greebles" in spec.scene_plan.objects[0].required_features
    assert spec.components


def test_asset_intent_parts_compile_to_scene_components_before_build_ops():
    spec, parsed = build_spec_from_assistant_response(
        "Build a small repair drone with two side arms and a lens.",
        """{
          "action": "build",
          "build_job": {
            "asset_kind": "prop",
            "name": "Repair Drone",
            "materials": {"primary": "metal"},
            "parts": [
              {"id": "body", "label": "compact body", "shape": {"primary_form": "rounded_box"}},
              {"id": "side_arm", "label": "side arm", "count": 2, "materials": {"primary": "metal"}},
              {"id": "lens", "label": "front lens", "materials": {"primary": "glass"}}
            ],
            "features": ["usable handle"]
          }
        }""",
    )

    assert parsed["action"] == "build"
    assert spec.name == "Repair Drone"
    assert spec.style == "Build a small repair drone with two side arms and a lens."
    assert spec.scene_plan is not None
    assert [obj.id for obj in spec.scene_plan.objects] == ["body", "side_arm", "lens"]
    assert spec.scene_plan.objects[1].count == 2
    assert spec.scene_plan.objects[2].materials == {"primary": "glass"}
    assert len(spec.components) == 3


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


def test_malformed_quantity_response_keeps_count_and_color():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build 2 blue balls.",
        """```json
{
    "action": "build",
    "confidence": 1,
    "clarification_question": null,
    "escalation_reason": null,
    "build_job": {
        "type": "sphere",
        "size": 0.5, // local model comment
        "color": "#006400", // mislabeled blue
        "quantity": 2
    }
}
```""",
    )

    assert parsed["action"] == "fallback_intent"
    assert resolver["source"] == "fallback_intent"
    assert spec.components == ["sphere", "sphere"]
    assert [primitive.type for primitive in spec.primitives] == ["sphere", "sphere"]
    assert [primitive.material for primitive in spec.primitives] == ["blue", "blue"]


def test_malformed_compound_prompt_preserves_count_color_and_layout():
    spec, parsed, resolver = build_spec_with_primitive_resolver(
        "Build two blue spheres with a yellow tube between them and a red ball on the right.",
        """```json
{
  "action": "build",
  "confidence": 90,
  "clarification_question": null,
  "escalation_reason": null,
  "build_job": {
    "jobs": [
      {
        "type": "sphere",
        "color": "#0066CC", // Blue
        "scale": [1, 1, 1],
        "position": [-2.5, -0.5, 0]
      },
      {
        "type": "tube",
        "start_color": "#FFD700", // Yellow
        "end_color": "#FFD700",
        "scale": [0.3, 1, 0.1],
        "position": [-2.5, -0.8, 0]
      },
      {
        "type": "sphere",
        "color": "#FF69B4", // Red
        "scale": [1, 1, 1],
        "position": [2.5, -0.5, 0]
      }
    ]
  }
}
```""",
    )

    assert parsed["action"] == "fallback_intent"
    assert resolver["source"] == "fallback_intent"
    assert spec.components == ["sphere", "sphere", "cylinder", "sphere"]
    assert [primitive.material for primitive in spec.primitives] == ["blue", "blue", "yellow", "red"]
    assert [primitive.transform.location for primitive in spec.primitives] == [
        [0.0, -1.25, 0.5],
        [0.0, 1.25, 0.5],
        [0.0, 0.0, 0.5],
        [0.0, 2.5, 0.5],
    ]
    assert spec.primitives[2].transform.rotation == [1.570796327, 0.0, 0.0]
    assert spec.primitives[2].params == {"radius": 0.16, "depth": 2.5}


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
