---
title: Context Budget & Honest Overflow — Progress
status: In Progress
last-verified: 2026-09-29
---

# Context Budget & Honest Overflow — Progress

Implementation log for `docs/harness/context-budget-opencode-prompt.md`. The
prompt fixes three defects sharing one root cause: the runtime bounds history
with hardcoded constants and never measures the assembled request against the
resolved model's window (A), overflow is indistinguishable from any other
provider failure (B), and trimming is silent (C).

## Milestone 0 — Reproduction (GATING)

**Premise reproduces. The bug is real.**

Baseline fixture: `python/tests/test_context_budget_repro.py`.

- Small-window probe: a scripted model raises the canonical OpenAI-compatible
  context-length rejection (`Error code: 400 … context_length_exceeded`) once the
  assembled request exceeds a 4096-token window. History = 40 turns × 2000 chars.
- Large-window probe: a 40-turn history against a large-context model.
- Unknown-window probe: no catalog window (today's state).

Observed **before** the fix (verbatim):

```
=== REPRO small window ===
status: failed
error.code: PROVIDER_ERROR
error.message: Error code: 400 - {'error': {'message': "This model's maximum
  context length is 4096 tokens. However, your messages resulted in 18734
  tokens.", 'type': 'invalid_request_error', 'code': 'context_length_exceeded'}}
events: ['run.created', 'run.started', 'prompt.plan',
         'memory.dropped_context_extracted', 'model.requested', 'run.failed']
history_bounded event: False
```

- Terminal status: `failed`.
- Error code/message: generic `PROVIDER_ERROR` carrying the raw provider string;
  no `CONTEXT_OVERFLOW` code exists.
- Events emitted: none about length. The only dropped-context event is
  `memory.dropped_context_extracted` (from the pre-existing extraction seam),
  which says nothing about how much history was dropped at the bound.
- Retry: **none** — the exception falls straight to the generic handler.

Large-window probe:

```
=== REPRO large window ===
kept turns: 20 dropped turns: 20
```

The hardcoded `MAX_HISTORY_TURNS = 20` discards 20 turns a large-context model
could have held. Unknown-window probe: same hardcoded bound (no knowledge exists).

Command:

```
cd Black-Eclipse-site/python
../scripts/vendor/python/python.exe -m pytest tests/test_context_budget_repro.py -q -s
```

## Milestone 1 — Context-window knowledge (declared, not guessed)

**Done.** `ProviderSpec.context_window` (optional int) added in
`python/harness/models.py`, populated per provider with a **conservative floor**
and a provenance comment; a `MODEL_CONTEXT_WINDOWS` table adds model-specific
values (longest matching substring wins). `resolve_context_window(provider,
model)` is pure (no network), prefers model-specific → provider → `None`.

Declared values (floors, documented in code):

| Provider | Provider floor | Model-specific |
|---|---|---|
| openai | 128 000 | gpt-4o 128k, gpt-3.5-turbo 16 385 |
| anthropic | 200 000 | claude-3/4 200k |
| google | 1 000 000 | gemini-1.5/2.0 1M |
| mistral | 32 000 | mistral-large 128k |
| groq | 8 192 | llama-3.3/3.1-70b 128k |
| deepseek | 64 000 | deepseek-chat/reasoner 64k |
| xai | 131 072 | grok-2/3 131k |
| perplexity | 128 000 | — |
| together / fireworks | **unknown** | llama-3.3 128k / llama-v3p3 131k |
| ollama / lmstudio / openrouter / custom | **unknown** | — |

**Unknown-window policy (documented):** `UNKNOWN_WINDOW_POLICY =
"conservative_ceiling"` — an unknown window makes the budget *inert*
(`effective=False`, `window_known=False`) and the bound falls back to today's
`MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS`; every surface says "unknown". Unknown
is safe, never a guessed large window.

The estimator is the **existing** `eclipse_memory.profile.estimate_tokens`
(~4 chars/token), documented as an approximation; the budget keeps a 10% safety
margin because of that.

Tests: `python/tests/test_context_window.py` (5) — all pass.

## Milestone 2 — Measured, model-aware budgeting

**Done.** New `python/harness/context_budget.py`:
`compute_history_budget(...)` measures the **actual request** — resolved system
prompt, advertised tool schemas, every present per-run block (`profile`, skill
manifest, retrieved memory, dropped-context), the user turn, and a reserved
output allowance — then derives `window − overhead − reserved`, less a 10%
margin, in the estimator's unit. `MAX_HISTORY_CHARS` remains an **absolute
ceiling** even on a huge window.

Wired into `execute_run` **per run from the resolved model** (the same
convention as `memory_enabled` / `session_history_enabled`), never at import or
`__init__` time. The dropped-context block costs tokens, so the budget is
measured twice: once with an empty dropped block to extract, then re-derived
accounting for the block itself — two deterministic passes, no loop.

Because the dropped-context *block* also consumes the history allowance, a
larger window genuinely keeps more turns; the dropped-context seam is unchanged
in shape. Byte-stability of the system-prompt head and tool schema is preserved
(only the number of history messages varies).

**Safety property (verified):** unknown window → `_bounded_history` produces
exactly the same `(kept, dropped)` as before; a short conversation produces an
identical message list. Tests: `python/tests/test_context_budget.py` (8) — pass.

## Milestone 3 — Classify overflow as its own failure

**Done.** `CONTEXT_OVERFLOW` added to `HarnessErrorCode`
(`python/harness/schemas.py`). `classify_context_overflow(exc)` and
`context_overflow_error(...)` live in `models.py` beside the model layer. The
classifier requires a **specific** signal: a known structured code
(`context_length_exceeded`, `context_window_exceeded`, `string_above_max_length`,
…) or a bounded message pattern (`maximum context length`, `prompt is too long`,
`input token count … exceeds`, `reduce the length of the messages`, …). A
structured code that is clearly rate/auth/permission/timeout suppresses the
message match, so a false positive is refused. The graph's `agent_node`
classifies **before** its generic `except`, emitting `context.overflow` and
returning the specific error instead of `PROVIDER_ERROR`.

Tests: `python/tests/test_context_overflow.py` (classifier + recovery) — pass,
including rate-limit / timeout / auth / quota false-positive guards.

## Milestone 4 — Bounded recovery (one retry, then honest failure)

**Done.** On a classified `CONTEXT_OVERFLOW` from the **first** model call,
`execute_run` retries **once** with `tighter=True` (half the derived allowance).
If the tightened history is not actually smaller, no retry is attempted. After
recovery resolves, exactly one terminal status is persisted; an unrecovered
overflow emits one terminal `run.failed` and returns `CONTEXT_OVERFLOW` with a
message that states whether the retry actually happened. A cancellation during
the retry still cancels (`run.cancelled`, one status).

**Side effects:** recovery only triggers on a first-call overflow (`step <= 1`),
before any tool executed; an overflow after a tool ran is reported honestly with
no rebuild, so a side-effecting tool is never re-executed. Verified by test.

The tighter attempt re-extracts the (larger) dropped-context window and carries
it, so the retry is *materially* smaller than the first attempt, not a re-ask.
Every branch emits `context.overflow` / `context.retry` — no secrets, no raw
prompt contents.

Tests: `python/tests/test_context_overflow.py` — pass (retry→success, retry→
overflow→honest failure, exactly one terminal status, no tool re-execution,
cancellation).

## Milestone 5 — Make the trimming visible

**Done.** `memory.history_bounded` is emitted on the **success** path exactly
once when history was actually trimmed, with `keptTurns`, `droppedTurns`,
`droppedTokensEstimate`, `window`, `windowKnown`, `tighterRetry` — counts and
estimates only, never memory/dropped content (verified by a secret-leak test).
An untrimmed run emits none.

Surface: the generic streaming passthrough already carries activity items, so
`normalizeHarnessEvent` maps `memory.history_bounded` to one `bounded`
activity line ("Trimmed N older turns… · M kept · window") rendered by the
existing `ActivityItemRow` (new `Scissors` icon; no parallel event system). A
`CONTEXT_OVERFLOW` failure surfaces its **specific** message and remedy: the
front-door `client.final` now carries the structured `{code, message}` error and
`use-agent-run` records the code.

`RunResult` / `RunRecord` gain an additive optional `context` blob (Python
`schemas.py`, TS `types.ts`) and `persistence.py` gains an additive `context`
column (`_ADDED_COLUMNS`, `update_run`, `_run_row`). Absent for older rows and
untrimmed runs, so old clients are unaffected — verified by
`src/lib/harness/context-budget-contract.test.ts` (legacy run and record rows
compile and read) and `src/lib/agent/events.test.ts`.

Tests: `python/tests/test_history_bounded.py` (4), TS event + contract tests.

## Milestone 6 — Verification and documentation

Before/after on the Milestone 0 fixture:

| | BEFORE | AFTER |
|---|---|---|
| Small unknown-window overflow | `PROVIDER_ERROR` + raw provider string | `CONTEXT_OVERFLOW` + honest reason/remedy |
| Events | no length event | `context.overflow` + terminal `run.failed` |
| Large window, 40 turns | 20 kept / 20 dropped | 40 kept / 0 dropped |
| Known window overflow-prone run | 40 000-char history sent whole | measured trim + `memory.history_bounded` |

Checks (from `Black-Eclipse-site/`):

- `npx tsc --noEmit` — clean.
- `npx vitest run` — **147 files, 1828 tests passed**.
- `pytest python/tests -q` — **1429 passed**, including 37 new tests across the
  context suites (`test_context_window.py` 5, `test_context_budget.py` 8,
  `test_context_budget_repro.py` 4, `test_context_overflow.py` 16,
  `test_history_bounded.py` 4).
- `harness.eclipse_memory.eval` — **threshold gate PASS**, recallSupported 1.0,
  precision 0.727, leakage 0, forbidden 0 (unchanged).
- `harness.eclipse_memory.eval.contradictions_cli` — **gate PASS**,
  contradictionPrecision 0.906, leakage 0 (unchanged).
- `jdds.db` untouched (pre-existing working-tree modification, not by this work).

Docs: `docs/harness/context-budget-progress.md` (this file);
`docs/harness/decisions.md` ADR-H63 / ADR-H64; `docs/NAVIGATION.md` row already
present; `docs/CHANGELOG.md` entry.

### Known limitations

- **Unknown windows stay unknown:** `ollama`, `lmstudio`, `openrouter`,
  `together`. `fireworks`, and `custom` have no provider-level window (only a
  known model entry). For these the bound is today's conservative ceiling and
  every surface reports "unknown", never a guess.
- **Conservative floors:** `groq` (8 192) and `mistral` (32 000) are floors; a
  model not in `MODEL_CONTEXT_WINDOWS` gets the floor, which under-uses a larger
  model's window. This is deliberately safe.
- **The estimator is approximate:** `estimate_tokens` (~4 chars/token) is not a
  real tokenizer; the 10% margin and the absolute char ceiling absorb error.
- **Recovery is first-call only:** an overflow after a tool executed is reported
  honestly but not retried (to avoid re-running side effects). This is a
  deliberate, documented trade-off.
- **Not built (by design):** no summarization/compaction engine, no tokenizer
  dependency, no second estimator. The `context.overflow` / `context.retry` /
  `memory.history_bounded` data is what a future compaction ladder would build on.

