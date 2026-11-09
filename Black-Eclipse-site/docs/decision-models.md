---
title: Decision models — typed judgments (System One-shaped)
status: Current
last-verified: 2026-11-07
---

# Decision models — typed judgments

**Who this is for:** anyone adding a "smart if-statement" to Eclipse — a
classification, route, score, or yes/no judgment whose answer code (or a graph)
will branch on.

## Why this is not a chat provider

A chat model returns text. A **decision model** returns a *typed answer*: which
option, which score, what probability — plus a confidence where the question type
supports it. TypeSafe's Jev is the reference example, but the layer is
vendor-neutral and also accepts an LLM constrained to a JSON schema, or a plain
rule engine.

Because it has no messages, tools, streaming or context window, a decision model
does **not** belong in `PROVIDER_CATALOG` / `build_chat_model` / `ModelRouter`.
It lives beside the Model Runtime in `python/harness/decisions/`.

## The contract (closed vocabulary)

`python/harness/decisions/contracts.py`

| Question | Returns | Use for |
|---|---|---|
| `choice` | `choice`, `probabilities`, `confidence` | routing, classification, picking one of N |
| `score` | `score`, `legend`, `probabilities`, `confidence` | ordered rubrics, severity |
| `noul` | `noul` (0–1) | yes/no probability |

```python
from harness.decisions import DecisionRequest, DecisionService

request = DecisionRequest.model_validate({
    "state": {"ticket": "...", "plan": "pro"},
    "questions": {
        "team": {
            "type": "choice",
            "instructions": "Which team should handle this?",
            "criteria": {"billing": "payment", "technical": "bug"},
        },
        "is_urgent": {
            "type": "noul",
            "instructions": "Does the message convey time-sensitivity?",
        },
    },
})
result = await DecisionService(store).ask(request, run_id=run_id)
```

`result.status` is the only field a caller should branch on:

| Status | Meaning |
|---|---|
| `answered` | every answer cleared the policy thresholds |
| `review` | at least one answer is inside the abstain band — a hint, not a decision |
| `unavailable` | no provider or no valid answer; **nothing is inferred** |

A partial answer set, a type mismatch, or a provider error is `unavailable`,
never a partial result.

## Confidence policy

`python/harness/decisions/policy.py` — `DecisionPolicy`:

- `min_confidence` (default 0.6) — the provider's own certainty.
- `min_probability` (default 0.6) — for `choice`, the selected option's
  probability; for `noul`, the answer must be outside the `0.4 … 0.6` abstain
  band.
- `require_confidence` (default `False`) — when `True`, an answer with no
  reported confidence goes to `review`. Off by default so deterministic rules
  (which are not probabilities) still work.

There is no "assume yes" path. A low-confidence answer only ever gets weaker.

## Providers

`python/harness/decisions/providers/`

| Provider | Status | Notes |
|---|---|---|
| `rules` | **built** | Deterministic `noul` / equality-`choice` from a declared `rule` against one state fact. Fully offline; no model. |
| `typesafe` | planned | `POST /v1/systemone`; `jev-latest`. Requires `TYPESAFE_API_KEY`. |
| `llm` | planned | Any configured chat model constrained by `model_runtime/structured.py`. Keeps zero-config working without a key. |

A provider is resolved by `DecisionRegistry` in registration order, with an
optional caller preference. An explicit preference is **never silently
substituted**: if that provider is missing or blocked, the request is
`unavailable`. **Privacy is enforced before a provider is called:** under
`ECLIPSE_PRIVACY=local-models`, a provider whose `local` flag is `False` is
never selected, even if it is the only one installed.

The rule provider is the honest zero-model path, not a Jev imitation. A question
without a declared rule, a missing fact, or a type mismatch raises
`DecisionUnavailable`; the service records that and returns `unavailable`.

```python
questions = {
    "is_risky": {
        "type": "noul",
        "instructions": "Is the margin ratio above the limit?",
        "rule": {"fact": "margin_ratio", "op": "gte", "value": 0.25},
    }
}
```

`rule` is an Eclipse-local extension of the question. Remote adapters drop it
before the wire; only the rule provider reads it.

## Audit and calibration

`store.py` writes one immutable `DecisionRecord` per request on the ONE
`agent-memory.db`: run/owner/conversation, provider + model, question-template
hash, state hash, status, policy snapshot, typed answers, usage, latency, tool and
reason. The id is deterministic (`run + provider + question hash + state hash +
tool`), so a resumed run never double-counts.

`DecisionOutcome` is appended later (`correct` / `incorrect` / `partial` /
`unknown`) and never rewrites the answer. `decision_scorecard` reports counts by
status/provider/outcome and accuracy over evaluated records — the substrate for
per-template calibration once real outcomes exist.

## Tools

All read-only, risk `none`:

- `decision_ask` — the only way a model requests a typed judgment.
- `decision_list` — the recorded requests and any appended outcome.
- `decision_scorecard` — counts + accuracy.

An answer is **information, never authorization**. It cannot approve an effect,
waive the Fiduciary Gate, or become a verified financial fact. Any surface that
shows one labels it a model judgment.

## Wiring

- `python/harness/decisions/bootstrap.py` — `install_decision_layer`, called once
  from `AgenticService.__init__`.
- `python/harness/service.py` — `_run_kwargs()["decision"]`.
- `python/harness/graph.py` — `execute_run(decision=…)` → `build_graph` →
  `ToolContext.decision_service`.
- `python/harness/agents.py` — `*DECISION_TOOLS` in the Eclipse agent allowlist.

Tests: `python/tests/test_decisions.py` (contracts, rules, policy, audit, privacy,
tools, boot).

## Adding a provider

1. Subclass `DecisionProvider` in `providers/`, declaring `name`, `local`,
   `models`.
2. Translate `DecisionRequest` → the vendor payload, and the vendor response →
   `DecisionResponse`; raise `DecisionUnavailable`/`DecisionUnsupported` instead
   of guessing.
3. Register it at boot (never implicitly) in `install_decision_layer`, behind the
   operator's configuration and key.
4. Add contract tests with a recorded/golden response; keep the privacy test.

## Workflow nodes

Graph Studio exposes the same layer as two nodes
(`python/harness/graph_runtime/decision_nodes.py`, editor contracts in
`src/lib/graph-studio/registry-decisions.ts`):

| Node | Class | Notes |
| --- | --- | --- |
| `decision.ask` | `model` | `state` + `questionsJson` in, typed `answers` / `status` / `summary` / `provider` / `recordId` / `reason` out. Honours the same provider preference, policy thresholds and privacy gate. |
| `decision.demo` | `local_write` | Zero-config demo. Deterministic rules, built-in sample state (a wired `state` overrides it), no key or network; still audited. |

They call `DecisionService.ask` directly — no second orchestration loop, no
separate provider registry. Branch on `status` (`answered` / `review` /
`unavailable`), never on whether `answers` is non-empty. The pack is registered
in `node_packs.py`; `bootstrap.py` binds `service.decision` to it at boot, so a
missing layer fails honestly instead of guessing. A workflow **test run** may
execute both nodes (the capability is in the reduced envelope); the per-node
"Test node" panel is narrower and refuses the demo's local audit write.

## Non-goals

- No chat, tool-calling, streaming or free text.
- No decision provider in the chat model picker.
- No low-confidence answer promoted to `answered`.
- No decision answer treated as a market fact or an authorization.
- No default remote calls; a missing key is `unavailable`, not a mock.
