---
title: Harness — Personal Memory (facts, transcript search, learned preferences)
status: Current
last-verified: 2026-10-28
---

# Personal Memory

Eclipse exposes one personal-memory product with three distinct pillars:

| Pillar | What it is | Owning module |
|---|---|---|
| **Durable facts** | Small, scoped, provenance-labelled declarative facts injected every turn. | `python/harness/eclipse_memory/{service,decision,retrieval,profile}.py` |
| **Transcript search** | On-demand search over prior sessions. Never injected; cited when used. | `python/harness/session_index.py` + `SessionMessage`/`SessionMessageFts` |
| **Learned preferences** | Style/format preferences inferred only from repeated, consistent behaviour; confirmed by the user before recall. | `python/harness/eclipse_memory/preferences.py` |

All three share one database (`eclipse-memory.db`) and one write gate
(`eclipse_memory/decision.py`). There is no second memory engine, no second
database and no new agent runtime.

## Learned preferences

A single request is a task instruction, not a preference. `preferences.infer()`
matches a closed vocabulary of style/format requests and records one bounded
evidence excerpt (the trigger phrase, never the whole transcript).

Dimensions are deliberately narrow and non-sensitive:

- `answer_format` — tables, bullets, prose, charts
- `answer_length` — concise, detailed
- `tone` — direct, casual, formal
- `research_depth` — quick, deep

The learner (`preferences.learn`) proposes a preference only when the same value
has at least `preference_min_observations` observations across
`preference_min_distinct_runs` distinct runs, with `preference_min_consistency`
agreement. An ambiguous turn (two opposite values in one dimension) is ignored.
`MemorySuggestion` stores the evidence counts in `structuredData` so the UI and
the agent can explain *why* an inference exists.

A proposal is **inert**. It is never injected into a run. Accepting it uses the
existing suggestion route and the shared gate, writing a user-scoped
`MemoryRecord` of type `preference`; the compact profile then recalls it like any
other standing preference. Dismissing it suppresses the same inference for
`preference_suppression_days` (default 30). An explicit user preference always
wins over an inferred one.

### Policy

| Key | Default | Meaning |
|---|---|---|
| `preference_learning_mode` | `ask` | `off` / `ask` / `auto`. `auto` still respects the memory gate's own mode. |
| `preference_min_observations` | `3` | Observations required per dimension/value. |
| `preference_min_distinct_runs` | `3` | Distinct runs required (same-run re-indexing is idempotent). |
| `preference_min_consistency` | `0.6` | Share of the dimension's observations that must agree. |
| `preference_confidence_threshold` | `0.6` | Minimum confidence to propose. |
| `preference_suppression_days` | `30` | Cooling-off after a dismissal. |
| `preference_dimensions` | `{}` | Per-dimension switches (absent = enabled). |

When memory is disabled (`memory_enabled=false`) or preference learning is
`off`, no evidence is collected at all.

## Surfaces

- Agent tool: `memory` with `action="preferences"` returns active preferences,
  pending inferences and evidence groups.
- REST: `GET /eclipse-memory/preferences?scopeId=` and
  `POST /eclipse-memory/preferences/learn` (operator-gated). Next.js proxies:
  `/api/eclipse-memory/preferences` and `/api/eclipse-memory/preferences/learn`.
- UI: Eclipse Memory → **Preferences** (`eclipse-memory-screen.tsx`): pending
  inferences, remembered preferences with Forget, evidence groups, thresholds and
  a "Scan evidence" action.
- Durable facts and transcript search keep their existing surfaces
  (Facts / Session Search).

## Safety invariants

1. Every durable write goes through `eclipse_memory/decision.py`; the learner can
   only create inert suggestions.
2. Observations never copy secrets, raw dumps or full transcripts. Only the
   matched trigger phrase (≤160 chars) is retained, and it is secret-screened.
3. No sensitive traits, identity, health, politics or current financial facts are
   inferred. Dimensions are style/format only.
4. Preferences are user-scoped and never become universal rules.
5. Explicit preferences win; a dismissal suppresses the same inference; a
   forgotten preference is archived, not silently deleted.

## Tests

- `python/tests/test_preference_learning.py` — inference, thresholds, idempotency,
  accept/dismiss, explicit override, policy off, disabled dimension, auto mode.
- `python/tests/test_preference_api.py` — read model and operator-gated learner.
- `python/tests/test_memory_tools.py` — the `memory` tool's preferences surface.
- `src/lib/harness/eclipse-memory-browser.test.ts` — client contracts.

## Non-goals

No semantic/embedding inference, no hosted accounts, no autonomous preference
writes, no second memory store.
