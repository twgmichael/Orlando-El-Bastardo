---
title: Harness Resource Model Plan
created: 2026-08-16T00:00:00-04:00
updated: 2026-08-16T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: draft
canonical: true
canonical_for: harness_resource_model
wiki: true
wiki_group: Planning
wiki_page: Harness-Resource-Model-Plan
wiki_order: 203
---
# Harness Resource Model Plan

Recorded 2026-08-16. Status: **design discussion — decisions recorded
below, real open questions remain, nothing built.**

## Why this exists

Grew out of `docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s
local/cloud LLM interchangeability decision, then generalized: the same
"treat resources as interchangeable, coordinated by the harness" question
applies to render capacity too, not just LLM capacity — local Blender
workers today, a future cloud Blender-only render farm eventually. This
document is the harness-architecture-level answer; the Production Assembly
Pipeline and Producer Harness Render Dispatch plans are consumers of it,
not duplicates of it.

## Grounding fact this discussion started from

Local machines naturally co-locate Blender and a local LLM (`render-mac-01`
and `render-pc-01` both run Blender and Ollama today). A cloud render
resource would not — a cloud Blender container would only have render
capability, no local LLM sitting next to it. Confirmed 2026-08-16: **LLM
calls stay local-or-cloud explicitly, never co-located with a cloud render
container.** A cloud Blender-only worker never claims `llm.*` jobs; it
simply never advertises that capability. This means no tool needs to become
"network-aware" about where its LLM call runs — the existing
capability-based job routing already keeps LLM work and render work in
separate pools, as long as cloud LLM resources are registered with the
right capabilities and cloud render resources are not.

## Decisions (2026-08-16)

1. **Cloud LLM providers are modeled as workers, not a separate resource
   type — extended by one new field.** Add `job_limit` to worker
   registration: the maximum number of jobs a resource can hold
   concurrently. Local render machines (`render-mac-01`, `render-pc-01`,
   any future local Blender box) register with `job_limit: 1` — one job
   claimed, busy until it finishes, matching today's actual behavior
   exactly (this is a new explicit field for an existing implicit
   constraint, not a behavior change for existing workers). Cloud render
   resources may register with a higher limit. Cloud LLM providers (OpenAI
   API, Claude API) register as worker-like resources with a much higher
   limit (discussed as `job_limit: 100`) reflecting that a cloud API call
   is not a single-process physical constraint the way a local Blender
   render is.
2. **LLM and render capability pools stay strictly separate.** Per the
   grounding fact above — no worker advertises both a render capability and
   an LLM capability unless it's a today's-shape local machine that
   genuinely has both installed. This is not a new mechanism; it's the
   existing capability-based routing (`OllamaAdapter`'s `llm.*` set,
   `BlenderCLIAdapter`'s `blender.*`/`gpu.*` set — see
   `docs/planning/PRODUCER-HARNESS-RENDER-DISPATCH-PLAN.md`) applied
   consistently as new resource types are added.
3. **The harness's scheduler picks the backend, not the caller.** A job
   requests an abstract capability; the harness selects which registered
   resource fulfills it based on cost, availability, and a competence
   ranking among resources that satisfy the same capability — not a
   specific backend named by the caller. See "Needs reconciliation" below —
   this appears to change, not just extend, a decision already recorded in
   the Production Assembly Pipeline plan.
4. **The concrete bottleneck risk is per-resource backlog, not the harness
   coordination layer.** Confirmed: the harness's own job-queue mechanism
   (FastAPI + Postgres + independently polling workers) already proves
   asynchronous coordination of wildly different job durations today —
   casting jobs and scene renders already interleave across workers with no
   blocking. The actual risk is a specific finite-capacity resource (one
   local Ollama instance, one local GPU, one cloud API key's rate limit)
   accumulating more concurrent claims than it can actually serve.
   `job_limit` is the mechanism that addresses this directly: it lets the
   scheduler know each resource's real capacity and hold back additional
   claims instead of dispatching blindly into an overwhelmed resource.

## Resolved: the zero-budget default (2026-08-16)

This resolves the reconciliation gap between "harness scheduler picks the
backend" (decision 3 above) and "Producer explicitly routes its grouping
pass to cloud" (`docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`), and
answers open question 3 below. Recorded as a hard rule, not a default that
can be casually overridden in code:

**A budget of zero dollars is always assumed unless explicitly stated
otherwise — in the script, or provided by a human. No agent or software may
ever assume, or be allowed, a budget greater than zero on its own.**

This means decision 3's "harness picks the backend based on cost,
availability, and ranked competence" operates *inside* an authorized
budget, not instead of one. The scheduler is free to rank and choose among
resources that satisfy a capability, but every resource with nonzero cost
is simply unavailable to it — filtered out before ranking even happens —
unless the job carries an explicit, human- or script-authorized budget
greater than zero. Local/free resources have no such gate; they're always
eligible. This is the actual mechanism that keeps "the scheduler decides"
from being able to silently spend money: the default state of the entire
system is cloud-resources-excluded, not cloud-resources-deprioritized.

Producer's explicit "route this to cloud" request from the Production
Assembly Pipeline plan is exactly the kind of human/script-adjacent
authorization this rule describes — a specific, bounded budget grant for a
specific job, not a standing permission. The scheduler still picks *which*
cloud resource within that grant (decision 3); it can never grant itself
the budget in the first place.

**Command decision, 2026-08-16 — "in the script" means a per-script budget
line item.** A script with no budget line item runs entirely at $0 (this is
correct, intended behavior, not a gap — confirmed against the three
current test scripts, none of which carries one). When a human adds a
budget line item to a script, Producer is responsible for allocating that
total across the resource needs of that script's production run — see
`docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s "Per-script budget
model" for the worked example. Where the line item physically lives and
the allocation algorithm itself are both open — see that document's "New
open questions."

## Uniform job envelope and confidence levels (raised 2026-08-16)

Every LLM-touching job request — Producer's grouping pass, Casting
Director, Director, Production Designer — should use one **uniform
request envelope**: a task plus a requested confidence/capability level,
not a specific backend named by the caller. This mirrors how render jobs
are already interchangeable to the harness, and it's the concrete
mechanism this document's decision 3 (harness picks the backend) already
called for.

**This reframes the earlier "Producer's grouping pass routes to cloud"
decision** (`docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md` decision
1): hardwiring Producer to a specific frontier model was a symptom of not
yet having this envelope, not a real architectural decision. Producer
should request a confidence level; the harness picks the resource that
satisfies it.

**Confidence level is a spectrum, not a local/cloud binary.** Worked
example from discussion:

- **Level 0** — fully deterministic, no model call at all. E.g. Director
  needs exactly one specific asset/character identified; resolve by exact
  match, gracefully fall back to a stand-in placeholder if no match. This
  isn't hypothetical — it's the existing `resolve_role()`/
  `resolve_location()` mechanism in `casting_director.py`/`set_designer.py`
  (and `screenplay_entity_resolution.py`'s registry-resolve call), which
  the master/resolved script work in
  `docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md` extends to Director.
- **Level 5** — complex reasoning, e.g. a full scene-build/layout
  direction call that may need Sonnet- or GPT-tier capability.

**A separately maintained benchmark system grades competence at each
level.** Not a static preference table — an ongoing, revised grading of
each resource (local model, Claude, OpenAI) against each task
type/confidence level, evidence-driven the same way the local-vs-Haiku
discussion already established. This is the concrete mechanism for open
question 2 below ("who defines ranked competence, and how").

**Still strictly inside the zero-budget-by-default rule.** Requested
confidence level and available budget are two separate axes that can
conflict — see open question 5 below.

## New requirement (2026-08-16): pre-job cost and time estimates

Raised alongside the budget rule, as a named "big win" feature: the
harness should be able to produce a cost estimate — and, since time and
cost trade against each other, a set of cost-for-timeframe estimates — for
a job's resource needs (render, LLM, audio, and other resource types)
**before the job starts**, not just track actual cost after the fact.

- Time estimates matter independently of budget: if a job is marked
  urgent, the system should be able to answer "what would this cost at
  different turnaround times" (e.g. cheaper-but-slower vs.
  faster-but-costlier), not just a single number.
- This is a harness/resource-model-level capability (it needs real data —
  `job_limit`, per-resource pricing, typical render/LLM/audio duration —
  that lives at this layer), even though Producer is the consumer that
  requests estimates as part of its planning role. See
  `docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s Producer role
  definition, where estimating and budget-checking are folded in as the
  production-planning side of that role.
- Not scoped here: what the estimate is actually computed from (a fixed
  per-resource pricing table, historical job duration data, both), or what
  precision is realistic before any real usage data exists to estimate
  from. Flagging as real scoping work, not deciding it now.

## Open questions

1. ~~Is `job_limit` a hard cap the harness server enforces, or a
   target/hint a worker manages internally?~~ **Resolved 2026-08-17:
   hard cap, server-enforced.** The harness's own job-claim logic tracks
   how many jobs each worker currently holds and refuses (or queues) a
   new claim once that count reaches `job_limit` — real state and a real
   check added to the dispatch path, not delegated to the worker/adapter.
   For local render workers this changes nothing observable (`job_limit:
   1` was already a physical constraint either way). For cloud LLM
   resources, this makes the number itself load-bearing: it must track
   the provider's actual rate-limit tier reasonably closely, or the
   harness either leaves real capacity unused (set too low) or dispatches
   past what the provider will accept (set too high, failing downstream
   anyway). **Follow-on, still open**: should `job_limit` therefore be
   configurable per provider/tier rather than a fixed number recorded in
   this plan? Not decided — a natural consequence of choosing hard-cap
   enforcement, not answered by it.
2. **Who defines "ranked competence" among resources that satisfy the same
   capability, and how?** A static preference table (e.g. "for
   `llm.grouping`, prefer claude-opus, then claude-sonnet, then local"), or
   something benchmark-driven — tying back to the local-vs-Haiku
   discussion's "let evidence decide, don't guess" position? These imply
   different build work: a config file vs. a feedback loop off a real
   results log. **Owning plan doc: `docs/planning/LLM-COMPETENCE-BENCHMARK-PLAN.md`**
   (2026-08-17 — corrects an earlier reference to
   `docs/planning/benchmarks/results.jsonl`, which turned out to already
   be owned by the unrelated Studio Chat visual-variety benchmark; this
   work gets its own file, `docs/planning/benchmarks/llm_competence_results.jsonl`).
   **2026-08-16:** this now has a concrete first test case — whether a
   local-only, chunked/windowed full-script grouping pass can substitute
   for a single large cloud call at acceptable quality; see
   `docs/planning/PRODUCTION-ASSEMBLY-PIPELINE-PLAN.md`'s "Open concern:
   is a paid call a hard default for the full-script grouping pass?".
3. ~~Does an abstract-capability job request carry a cost ceiling, or is
   cost-awareness purely relative?~~ **Resolved 2026-08-16** — see "Resolved:
   the zero-budget default" above. Every job's effective ceiling is zero
   unless explicitly authorized by script or human; "pick the cheapest
   available" only ever operates among resources that clear that gate.
4. **What does registering a cloud LLM provider as a worker actually run?**
   A real lightweight process somewhere that polls/heartbeats like
   `render-mac-01`/`render-pc-01` do today (and if so, on which machine is
   it hosted?), or a server-side-only virtual resource entry with no
   physical process, where the harness's own job-claim logic special-cases
   it? This is an implementation-shape question, not just a schema one —
   the two answers lead to different code.
5. **What happens when a requested confidence level and the zero-budget
   default conflict?** A level-5 request with no zero-cost resource able to
   satisfy it — does the job fail outright, silently degrade to the best
   zero-cost resource available, or queue pending explicit budget
   authorization? Not decided; the zero-budget rule's "filter out
   nonzero-cost resources" mechanism defaults to silent degrade by
   omission, which may not be the right call for a request that explicitly
   asked for high confidence.
6. **Is a level-0 (fully deterministic) call dispatched through the
   harness as a uniform job at all, or handled as a direct code path
   outside the job system?** Keeping it a uniform job (envelope in,
   envelope out, even though it resolves instantly and for free) is more
   consistent for observability and cost-estimate tracking; bypassing the
   harness for it is simpler but breaks the "uniform envelope" property
   above. Not decided.

## Not built

Nothing in this document has been implemented. No `job_limit` field exists
on any worker record today; no cloud LLM resource is registered anywhere;
the scheduler has no capability-ranking, cost-awareness, or budget-gating
logic; no pre-job cost/time estimate capability exists for any resource
type.
