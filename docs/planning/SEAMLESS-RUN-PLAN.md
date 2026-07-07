# Seamless runs — why prompts persist, and the plan to end them

Discovery recorded 2026-07-06. Goal: script in → render out, zero permission
prompts. Status: **EXECUTED AND PROVEN 2026-07-06** — `tools/run_pipeline.py`
built (Tier 1); permission rules applied, 34 dead exact entries pruned
(Tier 2); proof run passed: one command, brief → LLM → resolve → validate →
Blender/Godot/USD → MP4, exit 0, zero prompts, fully unattended
(`renders/reviews/pipeline_proof.mp4`).

## The discovery

"Always allow" in the harness permission UI saves the **exact command
string**, not a pattern. This pipeline almost never runs the same string
twice, so the allowlist grows (~60 frozen entries in the local settings file
to date) while prompts keep coming. Three patterns defeat exact-match
allowing structurally:

1. **Argument churn.** Every export/render/verify call embeds varying
   arguments — `--spec`, `--out`, seeds, scene IDs, filenames. Each variant
   is a new string → new prompt, and the saved rule is dead on arrival.
2. **Compound shell.** `cd X && A && B`, `for` loops, `VAR=$(...)` command
   substitution, heredocs. The permission matcher evaluates the whole
   compound; any unmatched segment prompts.
3. **Inherently unique one-liners.** Verification snippets passed inline
   (`--python-expr "..."`, `python -c "..."`) differ every time by nature —
   they can never be pre-allowed individually.

A few broad prefix rules exist (e.g. `.venv/bin/python *`), which is why
some steps flow; the heavy binaries (Blender, Godot, llama-completion,
ffmpeg, md5, cp) accumulated only exact-match entries.

## The remedy (two tiers)

### Tier 1 — architectural (the real fix)

One pipeline entry point: `tools/run_pipeline.py --intent <path>` (or
`--brief` for the LLM front end), which internally subprocesses
resolver → validator → exporter(s) → render → encode. Then a SINGLE prefix
permission rule covers the entire script-in/render-out path permanently:

```
Bash(.venv/bin/python tools/run_pipeline.py *)
```

Child processes of an allowed command do not re-prompt, so everything the
entry point invokes rides on that one rule. This also matches the pipeline
philosophy: one deterministic front door, machine-checkable behavior, and a
deterministic *permission surface*.

### Tier 2 — allowlist hygiene (covers ad-hoc work)

Replace the dead exact entries with a handful of prefix rules for the
pipeline binaries:

```
Bash(/Applications/Blender.app/Contents/MacOS/Blender *)
Bash(/Applications/Godot.app/Contents/MacOS/Godot *)
Bash(llama-completion *)
Bash(md5 *)
Bash(cp *)
Bash(diff *)
```

The harness's `/fewer-permission-prompts` skill can generate this list from
transcript history. Compound commands still prompt unless every segment
matches — prefer single-command invocations (or the Tier-1 entry point)
over `&&` chains where prompt-free operation matters.

## Notes

- The local settings file is personal/gitignored; this doc records the
  finding and plan, not the settings themselves.
- Worker-agent runs inherit the same mechanics: profiles that stick to
  `.venv/bin/python` + repo-relative paths prompt least. The Tier-1 entry
  point would let a worker run the whole pipeline under one rule too.
- Unattended/scheduled runs (the AGENT-WORKFLOW-PLAN Phase B idea) require
  Tier 1 — an unattended session cannot answer prompts at all.
