# Harness Render Quality Language

status: adopted
date: 2026-07-20

The studio harness uses three user-facing render quality levels for assets and
scenes:

- `draft` — fastest render for blocking, timing, composition, and smoke checks.
- `preview` — middle quality for reviewable work-in-progress output.
- `final` — delivery-quality output candidate with full render settings.

Use this language in conversational requests, UI labels, CLI flags, and API
payloads:

```text
Send JB100-pirate-escape to render-pc-01 as a draft render.
Send JB100-pirate-escape to render-pc-01 as a preview render.
Send JB100-pirate-escape to render-pc-01 as a final render.
```

For harness APIs, the canonical field is:

```json
{
  "quality": "draft"
}
```

`quality` must be one of `draft`, `preview`, or `final`.

## Harness Mapping

Scene render jobs support all three quality levels:

- `draft` uses `blender.preview_render`, defaults to blocking mode, and writes
  `scene.draft_render` artifacts.
- `preview` uses `blender.preview_render` and writes `scene.preview_render`
  artifacts.
- `final` uses `blender.final_render` and writes `scene.final_render`
  artifacts.

Asset review jobs support all three quality levels:

- `draft` uses `blender.preview_render` with lower default resolution/samples.
- `preview` uses `blender.preview_render` with reviewable default
  resolution/samples.
- `final` uses `blender.final_render`; GPU Cycles can be requested when the
  target worker supports it.

Machine-facing capabilities remain `blender.preview_render` and
`blender.final_render`. User-facing requests should not ask for those
capability names directly unless debugging worker routing.

## CLI Examples

Scene:

```bash
python3 tools/submit_scene_render.py \
  --scene-name JB100-pirate-escape \
  --script tools/JB100-pirate-escape.py \
  --quality preview \
  --worker render-pc-01
```

Asset:

```bash
python3 tools/submit_asset_review_render.py \
  --asset-name JB100 \
  --quality draft \
  --preferred-worker-id render-pc-01
```
