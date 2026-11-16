---
title: No Dead Ends (capability gaps and offers)
status: Current
last-verified: 2026-11-16
---

# No Dead Ends

**Who this is for:** anyone changing what Eclipse does when a request cannot be
completed: the failure taxonomy, the durable gap record, the user offer, or the
acquisition hand-off.

## The rule

A run may fail. It may **not** leave the user without a next step.

When a run cannot finish, Eclipse either:

1. completes the request, or
2. names the exact missing piece **and** offers the one permitted route:
   *"I can't do X here because Y. I can Z. Want me to?"*

A safety denial is the only deliberate exception. It is explained, never
offered as a bypass.

This is not "ignore the context". Context decides **how** the request is done
(chat tool, code task, profile, setup), never **whether** the user may ask.
An approval is still required for every effectful step; an offer is not an
authorization.

## Bounded answer recovery (before the offer)

A gap record answers "the capability is missing". A **blocked route** is a
different shape: the capability exists, the model tried it, and it replied with
a bare "UNAVAILABLE" without trying the next rung. `answer_guard.py` handles
that shape **inside the graph loop**, before the answer seam:

1. `is_bare_refusal` classifies a short, route-specific give-up. A substantive
   partial answer that mentions one missing figure is NOT recovered; neither is
   a policy refusal ("I can't give investment advice").
2. `sources_restricted` refuses to route around the user's own rule ("only the
   attached filing", "no web").
3. `recovery_reason` permits at most **2** extra model turns, only while the run
   has steps left and at least one permitted route is untried.
4. `build_recovery_instruction` names the untried routes (filtered to the bound
   surface), names what already returned UNAVAILABLE, and asks for one of: the
   next route, a best-effort partial with its exact gap, or a computation from
   held data.
5. After the bound is spent, the refusal stands: an explicit `UNAVAILABLE` is a
   valid final answer once the permitted routes are exhausted.

Events: `answer.recovery_started`, `answer.recovered`,
`answer.recovery_exhausted`; `run_outcome.answerRecovery` records attempts,
recovered/exhausted and the suggested routes. The graph state carries
`tools_used`/`unavailable_tools` so a route is never suggested twice. The
settlement lives in `final_answer.py` (extracted from `graph.py`).
`RunSpec.dispatch_allowed` carries the pre-disclosure surface, so a hidden
read-only tool stays callable even though its schema is not advertised.

The per-run `render_fallback_block` also puts the concrete ladder next to the
user turn (structured provider → official/primary page or filing → web
extraction → scraper → computation). It names only tools on this run's surface.

A precise series/macro request can opt into `webFallback`: WEB is then appended
as the LAST route and the result is `PARTIAL` (page-sourced), never `OK` and
never a verified structured series. The default remains structured-only.

## The taxonomy

`python/harness/gaps/taxonomy.py` classifies one failure. Only the first three
classes are offerable.

| Class | Meaning | Offer |
|---|---|---|
| `capability_missing` | no tool/recipe/skill exists | the existing builder (`capability_build`, `bot_create`, `skill_create`, `scaffold_kit`, `create_goal`, …) |
| `context_denied` | it exists, this run cannot use it | the permitted surface: chat bot/skill, or a code task with a workspace |
| `not_configured` | a runtime piece is off | the existing setup/doctor step |
| `malformed` | bad arguments | self-repair; no offer |
| `transient` | timeout/rate limit | `recovery/hotpath.py` retry/backoff |
| `safety_denied` | protected path, secret, finance guardrail, network/security floor | explain and give the safe alternative; **never** offer to bypass |
| `user_denied` | the operator said no | stay quiet |
| `unknown` | unclassified | no offer (do not nag on noise) |

The classifier reads the stable tool code first, then a narrow reason heuristic.
A tool refusal that returns `{"status": "refused", "code": ...}` is a real gap
even though the tool call itself succeeded; `graph.py` checks that payload.

## The gap record

`python/harness/gaps/` owns one durable row on `agent-memory.db`:

```
CapabilityGap(gapId, runId, signature, need, kind, code, tool, reason,
              taskId, state, createdAt, updatedAt)
state: open | offered | accepted | declined | suppressed | resolved
```

- The signature is stable (`sha256(kind, code, tool, need)`), so the same wall
  is not re-offered in every run.
- A later success on the same tool closes the run's open gaps (`resolved`).
- `suppressed` is permanent for that signature; `declined` is per gap.
- Recording is fail-open: a store error never breaks a run.

The record exists because a bot or a scheduled task has no chat card to click:
the gap is the durable "needs your decision" item.

## The offer

At the answer seam (`graph.py`, after the guardrail/answer gates) the runtime:

1. reads the run's pending gaps;
2. emits one `capability.offer` event per gap (bounded to the first three in the
   visible sentence);
3. appends one short sentence to the answer so every client (chat, bot, CLI,
   channel) shows the same ask.

The event is card-compatible (`status: gap | handoff_required`, `surface`,
`nextTool`, `steps`, `missing`, `actionLabel`, `actionPrompt`, `offer: true`),
so the existing `CapabilityCard` renders it and its button sends
`actionPrompt` as the next user turn.

A short first-person refusal with **no tool call** is also caught
(`looks_like_bare_refusal`) and routed to the capability builder. The check is
deliberately narrow: a long analysis that mentions a limitation is not
relabelled.

## Context offers

The same record covers "the tool exists, this run cannot use it":

- `WORKSPACE_UNBOUND` → `create_goal` ("run this as a code task").
- `PROFILE_DENIED` / `TOOL_FORBIDDEN` → `bot_create` or `skill_create` when the
  need names one; otherwise a code task with `code.write`.
- `ANALYSIS_NOT_ENABLED` / `SANDBOX_UNAVAILABLE` → the setup step.
- `KIT_UNKNOWN` → the capability builder.

The offer never grants the permission. It starts the surface that owns it.

## Operator API

Routes live in `python/harness/routers/capabilities.py` and are proxied by
`/api/capabilities/*`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/capabilities/gaps?state=&runId=` | durable gap queue with its offer |
| `GET` | `/capabilities/gaps/summary` | counts by state and class |
| `GET` | `/capabilities/gaps/{id}` | one gap + its offer |
| `POST` | `/capabilities/gaps/{id}/accept` | mark accepted; returns the exact `actionPrompt` / `nextTool` |
| `POST` | `/capabilities/gaps/{id}/decline` | not now |
| `POST` | `/capabilities/gaps/{id}/suppress` | never ask for this signature again |

Mutations require the operator token. Accepting does not run the build; the
caller runs the returned prompt, which reaches the existing surface and its
approval. If the gap carries a `taskId`, accepting also asks the existing
`resume_original_task` path to resume that parked task from its checkpoint; a
task that is not parked is reported as not resumed, never rewound.

The Capability Studio's Generated section shows the open queue
(`gaps-section.tsx`) with Accept / Not now / Never.

## Safety and anti-nagging

- No effectful build, install or enable without the existing single-use
  approval; the offer itself authorizes nothing.
- `safety_denied` and `user_denied` are terminal for the offer path.
- Max one offer per gap signature per run; suppression is durable.
- Gap text and reason go through the same bounded/redacted fields as other
  runtime records.
- Zero-config stays honest: a missing runtime is a `not_configured` offer, not
  a fake build.

## Files

- `python/harness/gaps/` — `taxonomy.py`, `model.py`, `store.py`, `service.py`
- `python/harness/answer_guard.py` — bounded answer recovery + the fallback block
- `python/harness/final_answer.py` — final-answer settlement on the ONE loop
- `python/harness/tool_disclosure.py` — the schema budget / query-focused surface
- `python/harness/run_scope.py` — `dispatch_allowed` (advertised vs dispatchable)
- `python/harness/graph.py` — records tool refusals, runs recovery, emits offers at the answer seam
- `python/harness/run_outcome.py` — the envelope's `capabilityGap` reads the offer
- `python/harness/prompts.py` — "never end with a bare refusal"
- `python/harness/routers/capabilities.py` — the operator API
- `src/lib/agent/events.ts` — `capability.offer` → the capability card
- `src/components/chat/capability-card.tsx` — the offer action
- `src/components/chat/chat-history.tsx` — renders the card
- `src/components/screens/capability-studio/gaps-section.tsx` — the queue
- `src/lib/harness/capabilities-client.ts` — the client
- Tests: `python/tests/test_capability_gaps.py`,
  `python/tests/test_no_dead_ends.py`, `python/tests/test_capabilities_api.py`,
  `src/lib/agent/events.test.ts`,
  `src/components/chat/capability-card.test.tsx`
