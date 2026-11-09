---
title: Harness — Personal Memory (facts, transcript search, learned preferences)
status: Current
last-verified: 2026-11-08
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
wins over an inferred one, and while any preference for a dimension is active the
learner does not propose a competing value for that dimension.

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
`off`, no evidence is collected at all. `memory_mode=off` also blocks automatic
preference prompts (even inert suggestions); an explicit "remember this" still
works through the turn gate.

## Control Room layout

The Eclipse Memory screen renders **seven** top-level tabs. Each owns a related
cluster of views; daily browsing is separated from configuration and one-off
operations:

| Tab | Contains |
|---|---|
| **Overview** | Exact totals only (facts, active, skills, pending suggestions, learning candidates, corrections, providers, recent sessions). |
| **Facts** | Browse (filter/search/detail/save/archive) and Lifecycle (state counts + named views). |
| **Sessions** | Named sessions and full-text transcript search. |
| **Review** | Inert memory suggestions and the automatic-learning review queue. |
| **Preferences** | Learned preferences and the compact context snapshot injected into runs. |
| **Settings** | Policies, memory providers, and named profiles. |
| **Maintenance** | Retention/usage/contradiction/compaction diagnostics, activity (retrieval probe, corrections, mistakes), Markdown files, and database health/export/import/reset. |

Legacy deep links (`memory.lifecycle`, `memory.history`, `memory.health`, …) are
kept as tab aliases and resolve to the correct tab + internal section. The
screen previously exposed 16 top-level tabs, which duplicated the same records
across Facts/Lifecycle, Sessions/Session Search, Preferences/Suggestions and
Files/Health.

### Pagination contract

Every list route returns a page plus an exact total:

```
GET /eclipse-memory/memories?memoryType=&status=&q=&limit=&offset=
→ { memories, total, limit, offset, hasMore }

GET /eclipse-memory/lifecycle?view=&limit=&offset=
→ { counts, views, budget, memories, total, limit, offset, hasMore }

GET /session-search?q=&limit=&offset=
→ { engine, results, hasMore, offset }

GET /sessions?limit=&offset=
→ { sessions, total, limit, offset, hasMore }

GET /learning-review?limit=&offset=
→ { reviews, total, limit, offset, hasMore }

GET /eclipse-memory/suggestions?status=&scopeId=&limit=&offset=
→ { suggestions, total, limit, offset, hasMore }
GET /eclipse-memory/corrections?limit=&offset=
→ { corrections, total, limit, offset, hasMore }
GET /eclipse-memory/mistakes?runId=&limit=&offset=
→ { mistakes, total, limit, offset, hasMore }
```

`list` and `total` share one filter definition server-side, so a page can never
disagree with its count. The browser client exposes `listMemoriesPage()`,
`listChatSessionsPage()`, `listLearningReviewsPage()`, `listSuggestionsPage()`,
`listCorrectionsPage()` and `listMistakesPage()` for paged views, and keeps the
array-returning wrappers for callers (files, graph memory nodes) that need a
bounded batch. The shared `ServerPaginationFooter` renders "Showing X–Y of N" and
prev/next controls; the Session Search tab uses a **Load more** control because
its ranked result set has no cheap total.

## Surfaces

- Agent tool: `memory` with `action="preferences"` returns active preferences,
  pending inferences and evidence groups.
- REST: `GET /eclipse-memory/preferences?scopeId=` and
  `POST /eclipse-memory/preferences/learn` (operator-gated). Next.js proxies:
  `/api/eclipse-memory/preferences` and `/api/eclipse-memory/preferences/learn`.
- UI: Eclipse Memory → **Preferences** (`preferences-panel.tsx`): pending
  inferences, remembered preferences with Forget, evidence groups, thresholds, a
  "Scan evidence" action, the learning-mode switch (off / ask / auto) and
  per-dimension on/off switches. Generic policy controls for these keys are
  hidden from the Settings → Policies view because Preferences owns them.
- Durable facts and transcript search keep their existing surfaces
  (Facts / Sessions → Search history).

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
