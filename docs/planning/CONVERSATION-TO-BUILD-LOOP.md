---
title: Conversation To Build Loop
created: 2026-07-14T20:07:21-04:00
updated: 2026-07-16T17:46:50-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: active
canonical: true
canonical_for: conversation_to_build_loop
wiki: true
wiki_group: Planning
wiki_page: Conversation-To-Build-Loop
wiki_order: 130
---
# Conversation-to-Build Loop

Recorded 2026-07-14. Status: **PARTIALLY BUILT — first vertical slice in progress.**

## Goal

Build the shortest useful path from a creative conversation to a visible 3D
production result:

`conversation -> clarified build spec -> harness job -> Blender build/render -> local review page -> chatbot link/embed`

The point is not to build a perfect chat product first. The point is to let a
human talk naturally with a local production-designer LLM, turn that discussion
into structured work, and quickly see rendered progress on the local network.

## Product shape

The production-designer chatbot should behave like a practical collaborator:

1. Listen to the creative request.
2. Ask only the clarifying questions needed to make the job buildable.
3. Produce a structured build or scene spec.
4. Submit that spec to the studio harness as a job.
5. Link to a review page showing job status, preview renders, output files, and
   notes.

Escalation to stronger assistants remains available when the local LLM cannot
resolve a creative, technical, or planning ambiguity on its own.

## Interface-agnostic API

Open WebUI is a logical next step for the production-designer chatbot UI, but
it should be treated as one client of the studio harness, not as the harness
architecture. The reusable surface should be API endpoints and review URLs that
any interface can call or embed:

- Open WebUI
- command-line proving tools
- local harness dashboard pages
- menu bar apps
- future custom studio interfaces

`tools/studio_chat.py` is only the first proving client. The durable behavior
belongs in harness endpoints for conversation intake, spec proposal/approval,
job submission, artifact lookup, and review-page linking. UI-specific glue
should stay thin so the same build loop can work from any chat surface.

## First vertical slice

Start with a thin command-line conversation/intake tool before building a web
chat UI:

`tools/studio_chat.py`

Minimum behavior:

- Accept one creative request as text.
- Submit the prompt to the configured studio endpoint in `OEB_HARNESS_URL`.
- Let that harness perform scene-plan intake, repair, primitive-spec creation,
  and job submission.
- Have an eligible worker claim the Blender-capable render job.
- Print the job ID, review URL, trace URL, and canonical ID.

Example:

```bash
OEB_HARNESS_URL=<local or staging harness URL> \
API_ADMIN_TOKEN=<matching harness admin token> \
python3 tools/studio_chat.py "Build me a fast, beat-up pirate space fighter from primitive shapes."
```

## First job type: primitive asset build

The best first asset-building demo is a primitive-kitbash ship. It avoids
external asset dependencies and proves that conversation can create a new
production object.

Example conversation outcome:

```json
{
  "canonical_id": "ship_pirate_fighter_A",
  "name": "Pirate Fighter A",
  "kind": "ship",
  "style": "fast scrappy pirate craft",
  "build_method": "blender_primitives",
  "components": [
    "wedge nose",
    "compact dark cockpit",
    "low main hull",
    "two swept wings",
    "two large rear engines",
    "crooked tail fin",
    "asymmetric greebles"
  ],
  "deliverables": [
    "glb",
    "preview_render",
    "review_page"
  ]
}
```

Harness job payload shape:

```json
{
  "title": "Build ship_pirate_fighter_A primitive pirate fighter",
  "description": "Create a fast, beat-up pirate space fighter from Blender primitives.",
  "required_capabilities": ["blender.command_line"],
  "policy": "run_anywhere",
  "payload": {
    "tool": "primitive_asset_builder",
    "asset_kind": "ship",
    "canonical_id": "ship_pirate_fighter_A",
    "output_path": "assets/ships/ship_pirate_fighter_A.glb",
    "preview": true,
    "spec": {
      "style": "fast scrappy pirate craft",
      "components": [
        "wedge nose",
        "compact dark cockpit",
        "low main hull",
        "two swept wings",
        "two large rear engines",
        "crooked tail fin",
        "asymmetric greebles"
      ]
    }
  }
}
```

`output_path` is a logical project-relative artifact path. Runtime workers must
resolve it through configured roots or environment variables. No absolute local
machine paths belong in committed code or examples.

## Review page

Each submitted build job should have a local-network review page. The first
version can be a simple job-specific build card, not a full gallery.

Minimum fields:

- Job title, status, worker, timestamps.
- Original creative request.
- Clarified structured spec.
- Preview render image when available.
- Output artifacts: GLB, logs, render files.
- Notes or failure reason.

This gives the production-designer chatbot a concrete URL to link or embed when
showing progress.

Example URL shape:

```text
/review/jobs/{job_id}
```

## Local LLM responsibilities

The local LLM should:

- Clarify vague creative requests.
- Map conversational names to known production concepts where possible.
- Emit strict structured JSON.
- Prefer small buildable jobs over broad vague jobs.
- Ask for escalation when it cannot safely decide.

The local LLM should not silently invent unavailable assets or bypass the
pipeline. If the request requires missing assets, it should produce a needed
asset/build job instead.

## Deterministic worker responsibilities

The worker should:

- Build from the structured spec, not from free-form chat.
- Use Blender primitives for the first asset builder.
- Export a GLB artifact.
- Render at least one preview image.
- Register artifacts with the harness.
- Update job status so the review page reflects progress.

## Out of scope for the first slice

- Full browser chat UI.
- Long-term conversation memory.
- Multi-user collaboration.
- Full asset registry administration.
- Sophisticated mesh generation.
- Automatic public publishing.
- Perfect visual quality.

The first slice succeeds when a human can type one creative request, approve or
clarify the spec, submit a harness job, and open a local review page with a
rendered preview.

## Build checklist

- [x] `tools/studio_chat.py` CLI intake
- [x] Interface-agnostic conversation/spec/job endpoints
- [x] Tiny intake JSON schema
- [x] Local Ollama prompt for strict JSON
- [x] Job payload adapter for primitive asset builds
- [x] `primitive_asset_builder` Blender worker path
- [x] Preview render artifact registration
- [x] Job-specific review page at `/review/jobs/{job_id}`
- [x] Chatbot response includes review URL
- [ ] Security sweep passes with no absolute local paths
