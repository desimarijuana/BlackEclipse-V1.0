---
title: W3 — Tool Execution (Detailed Plan)
status: Implemented (core)
last-verified: 2026-11-12
owner: Agent runtime
parent: docs/harness/roadmap/hermes-inspired-improvement-plan.md
baseline: docs/harness/baselines/w0-0a7ec906-2026-11-12.json
scope: implementation landed — see §15 for the live surface and deliberate gaps
---

# W3 — Tool Execution

W3 changes **how many tool calls run at once, when the runtime stops a loop,
and how the long tail of tools is advertised**. It does not add a second tool
loop, registry, scheduler, approval path or event bus. `graph.tools_node`
remains the only place a model-issued tool call is dispatched, and
`ToolRegistry.execute` remains the only handler seam.

**Shape before W3 (measured 2026-11-12):**

- sibling calls in one model turn run **sequentially** (`for call in calls`,
  `graph.py:996`);
- progressive discovery is **opt-in** via a raw `HARNESS_LAZY_TOOLS` env read
  (`tool_surface.py:39`) and uses a small lexical scorer (`tool_surface.py:78`);
- there is **no success-signature cycle/stall controller** — only per-turn
  duplicate suppression, the hard tool budget, and the failure-based
  `ProgressTracker` in `recovery/progress.py`.

**Target (copying Hermes):** parallel read-only batches, a warn-first guardrail
controller, and default-on progressive disclosure after eval parity. All three
land behind flags, shadow-first.

**Duration:** 2–3 engineer-weeks.
**Dependencies:** W0 flag registry (landed), W2 context budget/prune (landed).

---

## 1. Goals

1. **Cut sibling-call latency without changing semantics.** Six independent
   200 ms read calls should finish in roughly one call's latency, with the
   model still seeing results in the order it issued them.
2. **Stop expensive loops honestly.** Three identical successful calls, a short
   repeating cycle, or a failure streak should produce a model-readable
   directive — and, past the threshold, a controlled stop — instead of burning
   the run budget.
3. **Advertise less, discover more.** When bound tool schemas exceed the
   context budget, bind the effectful tools plus the discovery core, list the
   rest cheaply, and make the hidden tail findable with BM25.
4. **Keep every existing safety invariant.** Effect ordering, at-most-once
   effects, resume idempotency, approval, per-tool timeout, the hard tool
   budget, and the run deadline all still hold.

## 2. Non-goals

- No parallel execution of effectful or interactive tools.
- No parallel path around `ToolRegistry.execute`.
- No concurrency inside a single tool handler (the tool owns that decision).
- No new agent loop, task queue, scheduler, retry engine or approval store.
- No new database file and no new durable table.
- No `tool_invoke` for effectful tools. The graph owns budget, idempotency,
  effects and approval; a second dispatch path for writes would bypass them.
- No model call from the guardrail controller. It is deterministic.
- No disclosure of effectful tools. They are always bound.
- No change to the response contract or financial semantics.

---

## 3. Why these three pieces, and why now

| Hermes behaviour | Eclipse today | W3 decision | Why |
|---|---|---|---|
| Parallel sibling tools (8 workers, ordered results) | Sequential `for` loop | **Adopt**, read-only only, contiguous batches | Six-source retrieval pays 6× latency; long turns risk the run deadline |
| Identical-call / cycle / result-stub guardrails with controlled halt | Per-turn duplicate suppression only; failure tracker only | **Adopt**, warn-first, success signatures | Repeated *successful* calls are invisible to the failure tracker |
| Default-on progressive disclosure, BM25, tiers | Lexical search, opt-in, no tiers | **Adopt**, shadow → auto | >1,000 tools inflate every prompt; the long tail is undiscoverable |

The three interact. Parallel batches make a loop cheaper to run, so the
guardrail must land in the same release; disclosure changes which tools are
bound, so the parallel partition must be computed from the **resolved** surface,
not the raw registry.

---

## 4. Current path

```
agent_node
  └─ model returns N tool_calls
       └─ tools_node                         graph.py:961
            for call in calls:               graph.py:996   ← sequential
              budget check                   graph.py:1005
              tool.requested                 graph.py:1028
              per-turn duplicate key         graph.py:1034 / 1053
              resume idempotency             graph.py:1039
              plugin before hook             graph.py:1065
              effect begin / at-most-once    graph.py:1089
              run_tool_with_recovery         graph.py:1114
              artifact/gap/event writes      graph.py:1124–1192
              ToolMessage                    graph.py:1194
            prune old tool output            graph.py:1201
            checkpoint tool_results          graph.py:1215
```

`run_tool_with_recovery` (`recovery/hotpath.py:112`) already retries one
read-only failure and records a `ProgressTracker` on the context. That tracker
is **failure-based**: it cannot see three successful identical calls.

Discovery path:

```
resolve_surface_run                    graph.py:1581
  → apply_intent_surfaces              graph.py:1591
  → lazy_tool_surface                  graph.py:1599   ← raw HARNESS_LAZY_TOOLS
  → registry.schemas(allowed)          context_budget.py / graph.py:2487
  → tool_search / tool_invoke          tool_surface.py:96
```

---

## 5. Target path

```
tools_node(state)
  ├─ resolve surface (already done by agent_node)
  ├─ plan = plan_batches(calls, registry, mode)
  │    contiguous runs of parallel-safe calls → one batch
  │    effectful / interactive calls          → one serial slot each
  ├─ pre-flight EVERY call in original order
  │    budget, duplicate, resume, plugin before, effect begin
  ├─ for each batch/slot in original order
  │    parallel-safe batch → asyncio.gather(Semaphore(N))
  │    serial slot         → await one call
  │    results written into their ORIGINAL index
  ├─ guardrail observe (after each result, in original order)
  │    allow | warn (append directive) | halt (controlled stop)
  ├─ append ToolMessage list in original order
  ├─ prune old output once (W2)
  └─ checkpoint tool_results once
```

No handler is called outside `ToolRegistry.execute`; no result is appended
outside the original order; the prune and checkpoint still happen once per
turn.

---

## 6. Contracts

### 6.1 Parallel partition

Extend `ToolDefinition` (`tools.py:427`) with two additive fields:

```python
#: A tool that waits for a human (clarify, approval, ask_user). Always serial.
interactive: bool = False

#: Whether this tool may share a batch with other parallel-safe calls.
#: None = derive from the registry policy (see below), never a handler guess.
parallel_safe: Optional[bool] = None
```

Resolution (`tool_turn.resolve_parallel_safe(registry, name)`):

1. `interactive` → **False**.
2. `permission != "read"` or `effect` is set → **False**.
3. `parallel_safe is False` → **False**.
4. `parallel_safe is True` → **True** (an explicit operator override).
5. otherwise → **False** in W3.1. Phase 2 may flip the default to True for
   `permission == "read"` after the audit in §9.2.

The first release ships an **explicit allowlist**, not "all read tools". Many
read tools still write caches/stores or share a rate-limited provider; treating
"read" as "concurrency-safe" is how the sqlite/cache races in §10 happen.

Partition rules:

- Only a **contiguous** run of parallel-safe calls becomes a batch. Given
  `[read A, write B, read C]`, A and C must not overlap: B may depend on A and
  C may depend on B. Batches are `[[A], [B], [C]]`, not `[[A, C], [B]]`.
- A batch never spans a turn, a plan step, or an interactive call.
- One failed call does not cancel its siblings; it gets an error slot.
- A batch's deadline is `min(run_deadline, now + HARNESS_TOOL_BATCH_TIMEOUT_S)`.
- `HARNESS_TOOL_CONCURRENCY` (1..12, default 6) bounds the semaphore. `1`
  is a valid kill switch and must reproduce sequential behaviour exactly.

### 6.2 Per-call context

`ToolContext` is a mutable dataclass carrying per-call fields
(`tool_timeout_ms`, `effect_authorized_digest`, `effect_token`) and shared
services/stores. A batch must not share one instance across tasks.

- Each batch call gets `dataclasses.replace(ctx)` (a shallow clone). Shared
  services/stores stay shared **by reference** on purpose.
- Per-call fields are set on the clone before dispatch.
- The clone must not copy the per-run recovery counters: `_recovery_hotpath`,
  `_recovery_progress`, and the guardrail state are attached to the **parent**
  context and accessed under the tools-node's single-threaded result loop, not
  from worker tasks.
- A read tool that mutates the context beyond per-call fields is a bug; the
  audit in §9.2 must record the fields it touches.

### 6.3 Execution order and result slots

Pre-flight runs **sequentially in original order** for every call, whether or
not it is in a batch:

```
slot[i] = { call, name, args, call_id, key, outcome: pending }
budget check        → slot gets TOOL_BUDGET_EXCEEDED, no dispatch
resume idempotency  → slot gets the recorded result, no dispatch
duplicate (turn)    → slot gets TOOL_FORBIDDEN, no dispatch
plugin veto         → slot gets the plugin refusal, no dispatch
effect begin        → only for an effectful slot, immediately before dispatch
```

Then the batches execute in slot order. Results are written back by index, so
`out_messages` is always `[slot[0].message, slot[1].message, ...]`.

Effectful invariants that must remain true:

- `effects.begin` runs before its dispatch and `effects.finish` after it, in
  the same slot; no effect slot is ever inside a batch.
- `lineage.mark_tool_executed` records the same `(runId, stepIndex, toolCallId)`
  key; a resumed batch reuses results exactly as today.
- The tool budget is decremented in pre-flight order, so `[read, read, read]`
  with one unit left executes the first and refuses the other two.

### 6.4 Guardrail controller

New `python/harness/tool_guardrails.py` — **pure**, no I/O, no model, no
registry access. It reuses `attempt_digest` from `recovery/progress.py` so the
runtime has one canonical argument hash.

```python
@dataclass(frozen=True)
class ToolSignature:
    name: str
    args_hash: str
    result_hash: str | None       # None until the result is known

@dataclass(frozen=True)
class GuardrailDecision:
    action: str                   # allow | warn | halt
    rule: str                     # identical_call | cycle | failure_streak | budget
    count: int
    message: str
```

State lives on the run context (`ctx._tool_guard`), created per attempt. It
survives the whole run, not one turn: the point is a call the model keeps
re-issuing across turns.

Rules (evaluated after a result, never before the first occurrence):

| Rule | Signal | Threshold | Action at threshold |
|---|---|---|---|
| `identical_call` | same name + canonical args + **same result hash** | 2 completed identical observations | the 3rd identical call is halted **before dispatch** |
| `cycle` | repeated signature sequence, period 2–4, in the last 64 observations | 2 full repetitions | halt the next call in the cycle |
| `failure_streak` | consecutive failed calls with no intervening success and no state change | 4 | halt the next call |
| `budget` | existing hard budget | existing | existing refusal, not a guardrail halt |

- A call whose signature has never been seen is **never** halted.
- `warn` mode appends one plain directive to the result text:
  `"[guardrail] This exact call has already returned the same result 2 times.
  Use the earlier result or change the arguments."`
- `halt` mode does **not** execute the offending call. `tools_node` returns a
  controlled stop: `state["guardrail_halt"] = decision`, a deterministic final
  text naming the tool, rule and count, and `route_after_tools` returns END.
  The halt message is a stop notice, never fabricated data.
- Repeatable allowlist (never count toward `identical_call`):
  `read_tool_output`, `process_manage`, `clarify`, and names ending in
  `_get_result`, `_poll`, `_status` (pollers are meant to repeat).
- `HARNESS_TOOL_GUARDRAILS=off` disables observation entirely and must produce
  byte-identical behaviour to today's loop.

**Not a second loop guard.** The existing controls stay and are not replaced:

- per-turn `seen_calls` duplicate suppression (`graph.py:994`);
- `ProgressTracker` failure/stuck detection (`recovery/progress.py`);
- the hard `max_tool_calls` budget;
- the `stalled` signal feeding the bounded replan (`graph.py:1199`,
  `should_replan`) — it is a *prompt* signal, not a guardrail halt.

The controller observes **successes**; the tracker observes **failures**.

### 6.5 Disclosure contract

Extend `ToolDefinition` with two optional discovery fields:

```python
tags: tuple[str, ...] = ()     # synonyms / task words, e.g. ("option", "iv")
domain: str = ""               # e.g. "market", "browser", "quant"
```

Both are additive, default-empty, and appear in neither `input_schema` nor the
model-facing `schemas()` output.

New `python/harness/tool_bm25.py`:

- pure Python, no dependency, no import of `eclipse_memory/hybrid.py`;
- tokenise: lowercase, split non-alphanumerics, split `snake_case`/`camelCase`,
  drop stopwords, keep tokens of length ≥ 2;
- fields and weights: name ×4, tags ×2, description ×1, domain ×1;
- BM25 `k1=1.2`, `b=0.75`;
- exact name match ranks first unconditionally; name prefix next;
- deterministic tie-break by tool name.

Activation (`tool_disclosure.py` or an extension of `tool_surface.py`):

```
mode = HARNESS_TOOL_DISCLOSURE            # auto | on | off, default auto after W3.4
on   → always narrow
auto → narrow only when toolSchemaTokens / windowTokens >= thresholdPct/100
off  → never narrow (today's behaviour)
window unknown → auto stays eager (never guess)
```

When narrow:

- bind effectful tools, `interactive` tools, `LAZY_CORE_TOOLS`, and any tool with
  `parallel_safe is False` that the surface declares;
- hide the read-only long tail behind `tool_search`/`tool_invoke`;
- never widen: a tool the agent's surface did not allow cannot appear through
  search or invoke.

Tiered catalogue block (new prompt block, byte-stable for the run):

| Tier | Content | Budget |
|---|---|---|
| 1 | name + one-line description, grouped by domain | 4,000 tokens |
| 2 | names only, grouped by domain | 2,000 tokens |
| 3 | `domain: N tools` summary only | 500 tokens |

The block is built deterministically after surface resolution and appended to
the system head beside the response-contract digest. It must be identical for
the whole run (prompt-cache stability); a registry change takes effect on the
next run.

`tool_search` additions:

- `availableSources` / `hint` when there is no match: the domains and counts
  that exist, never a fabricated tool name;
- `matchCount`, `returned`, `schemasOmitted` (existing);
- bounded response: 12 results and 18,000 schema chars (existing).

`tool_invoke` stays read-only and refuses effectful tools, recursion and
unknown names. It is not a second effect path.

### 6.6 Flags

| Flag | Default | Values | Kill switch |
|---|---|---|---|
| `HARNESS_PARALLEL_TOOLS` | `off` | `shadow|on|off` | `off` or concurrency `1` |
| `HARNESS_TOOL_CONCURRENCY` | `6` | 1..12 | `1` forces serial |
| `HARNESS_TOOL_BATCH_TIMEOUT_S` | `120` | 10..600 | batch deadline |
| `HARNESS_TOOL_GUARDRAILS` | `warn` | `warn|halt|off` | `off` |
| `HARNESS_TOOL_DISCLOSURE` | `auto` | `auto|on|off` | `off` keeps eager tools |
| `HARNESS_TOOL_DISCLOSURE_THRESHOLD_PCT` | `8` | 1..50 | `50` effectively disables auto |

`shadow` for parallel means: compute the batch plan and emit it, execute
strictly sequentially, and record what a real batch would have saved. It is
the measurement mode, not a half-parallel mode.

`HARNESS_LAZY_TOOLS` becomes a **deprecated alias**: `HARNESS_TOOL_DISCLOSURE`
wins when set; otherwise `HARNESS_LAZY_TOOLS=1` maps to `on`. Remove the alias
after two green weeks (W0 removal rule).

---

## 7. Slices

### W3.0 — Flags, shadow instrumentation, no behaviour change

- Add the three new flag declarations to `config/flags.py`; change
  `HARNESS_PARALLEL_TOOLS` to `shadow|on|off` (default `off`).
- Emit `tool.batch_plan` in shadow: `calls`, `batches`, `parallelSafe`,
  `wouldSaveMs` (estimated from measured durations only, else null).
- Emit `tool.disclosure` with `mode`, `tier`, `advertisedTools`, `hiddenTools`,
  `toolSchemaTokens`, `catalogTokens`, `savedTokens`, `window`, `thresholdPct`.
- No dispatch change.

**Acceptance:** with all flags off, the surface, prompt bytes and event stream
match today except the added flag snapshot and shadow events; `off` is a
kill-switch test.

### W3.1 — Parallel read-only batch

- `tool_turn.py`: partition, slot planning, per-call context clone.
- `tools_node` executes batches with a semaphore, preserving slot order.
- Explicit `parallel_safe=True` on the audited read tools (§9.2); all others
  remain serial.
- Batch deadline and cancellation synthesis.

**Acceptance:** 6 × 200 ms tools finish in ≤ 350 ms with concurrency 6; order
is byte-identical to serial results; one failure is isolated; effectful calls
never overlap a read; concurrency `1` reproduces serial exactly; a resumed
batch never re-runs a completed call.

### W3.2 — Guardrail controller

- `tool_guardrails.py` pure rules + per-run state on the context.
- `warn` appends the directive; `halt` stops the turn and sets
  `guardrail_halt`.
- Emit `tool.guardrail` with `rule`, `count`, `tool`, `action`.
- Operator reset: `POST /runs/{id}/guardrail-reset` (operator-gated, added to
  `routers/recovery.py`) clears the per-run signature ledger; resume also
  starts a fresh ledger.

**Acceptance:** three identical successful calls halt with a clear message and
never execute the third; changed args are allowed; pollers are exempt;
`warn` mode changes text only; `off` matches today; a false-positive fixture
(paged listing with differing results) is not halted.

### W3.3 — BM25 + tiered catalogue

- `tool_bm25.py` + tags/domain fields.
- Deterministic tier selection and the catalogue prompt block.
- `tool_search` no-match `availableSources`.
- Keep `tool_invoke` read-only.

**Acceptance:** recall@5 ≥ 0.90 on a 25-query labelled fixture; exact name is
always result 1; advertised schema tokens drop ≥ 50% on a synthetic 1,000-tool
surface (catalogue block included in the saving); an effectful tool is never
hidden.

### W3.4 — Auto threshold and default-on

- `auto` activates only above `HARNESS_TOOL_DISCLOSURE_THRESHOLD_PCT` of the
  known window; unknown window stays eager.
- Promote the default to `auto` only after an offline eval parity run and a
  live canary with zero missed-tool incidents.
- Remove the `HARNESS_LAZY_TOOLS` alias.

**Acceptance:** explicit `on`/`off` always win; `auto` does not activate below
the threshold; a 1,000-tool surface saves ≥ 50% and still answers the same
eval tasks; rollback is a single flag.

---

## 8. Tests

| File | Covers |
|---|---|
| `test_parallel_tools.py` | partition, contiguous batches, slot order, semaphore, concurrency 1, failure isolation, batch deadline, cancellation, budget, effect ordering, duplicate in batch, context clone |
| `test_tool_guardrails.py` | identical/cycle/failure-streak, warn/halt/off, poller exemption, changed args, first-occurrence never halts, reset, resume fresh ledger |
| `test_tool_disclosure_bm25.py` | recall@5 fixture, exact-name first, tags/domain weights, deterministic ties, no-match sources, schema cap |
| `test_tool_surface.py` (extend) | search/invoke refusals, lazy alias precedence, effectful never hidden, no widening |
| `test_tool_disclosure_bm25.py` | tier budgets, byte-stable block, prompt token accounting (folded in) |
| `test_flags.py` (extend) | new defaults, shadow enum, batch timeout clamp |
| `test_graph.py` (extend) | shadow emits a plan without changing results; `guardrail_halt` routes to END; disclosure off is byte-identical |
| `test_size_budget.py` | `graph.py` stays under its pin (new logic lives in modules) |
| `test_recovery_api.py` | operator reset route exists and stays gated |

Timing tests use a fake async handler with a deterministic `asyncio.sleep`,
never a real provider or network call. The recall fixture is committed; it is
not generated at test time.

---

## 9. Rollout

### 9.1 Order

1. W3.0 shadow instrumentation; no behaviour change.
2. W3.3 BM25 search upgrade in `off` mode (search quality improves; surface
   unchanged).
3. W3.2 guardrails in `warn`; measure directives per run.
4. W3.1 parallel in `shadow`; compare estimated saving against the W0 baseline.
5. W3.1 `on` for an internal canary; then default-on after two green weeks.
6. W3.4 disclosure `auto` after eval parity; then the alias removal.

Parallel lands after guardrails so a batch cannot make a cheap loop cheaper
before the stop rules exist.

### 9.2 Read-tool concurrency audit (before W3.1 `on`)

For each candidate `parallel_safe=True` tool, record:

- Does it write a store/cache? If yes, is the write idempotent and safe under
  concurrent tasks on one connection?
- Does it call a rate-limited provider? If yes, keep it serial or give it a
  per-provider semaphore.
- Does it mutate the context or a sink? If yes, keep it serial.
- Does it depend on another tool's output in the same turn? If yes, keep it
  serial.

The audit result is committed with the slice. "Read-only" alone is not enough.

### 9.3 Rollback

| Slice | Rollback |
|---|---|
| W3.1 | `HARNESS_PARALLEL_TOOLS=off` (or concurrency `1`) |
| W3.2 | `HARNESS_TOOL_GUARDRAILS=off` |
| W3.3 | `HARNESS_TOOL_DISCLOSURE=off` |
| W3.4 | `HARNESS_TOOL_DISCLOSURE=off`; the block is not added |

No schema migration, so rollback is a restart, not a data repair.

---

## 10. Fault matrix

| Fault | Expected behaviour |
|---|---|
| One read call in a batch raises | Only that slot is an error; siblings complete; order preserved |
| One read call times out | Slot gets the tool timeout error; batch deadline does not cancel finished siblings |
| Run deadline expires mid-batch | Outstanding tasks are cancelled; every missing slot gets a cancelled result |
| Budget exhausts mid-batch | Pre-flight already refused the tail; no dispatch after the limit |
| Same call twice in one batch | Second slot gets the per-turn duplicate refusal, never dispatched |
| Effectful call between reads | Reads are split into contiguous batches; the effect never overlaps |
| Plugin veto in a batch | Vetoed slot gets the refusal; siblings still run (plugin hooks run per call) |
| Shared sqlite/store lock | The audit keeps that tool serial; if it still races, the call returns its normal error, never a silent retry |
| Recovery retry inside a batch | The retry stays inside the slot; it cannot reorder siblings |
| Guardrail false positive (poller) | Allowlist exempts it; warn-only default during rollout |
| Guardrail halt with a partial plan | Controlled stop names the rule/count; no fabricated answer |
| Guardrail reset | Ledger cleared; the next occurrence is a first occurrence |
| No search match | `availableSources` lists domains/counts; no invented tool |
| Search schema response too large | Falls back to names + descriptions with `schemasOmitted: true` |
| Tool discovered then unregistered (MCP reload) | `tool_invoke` returns `TOOL_NOT_FOUND` with a re-search hint |
| Window unknown in `auto` | Disclosure stays eager |
| Catalogue block changes mid-run | Impossible: built once per run; a registry change applies next run |
| Flag conflict (`LAZY_TOOLS` + `DISCLOSURE`) | `DISCLOSURE` wins; one `flags` snapshot value |

---

## 11. Observability

Events (names are the contract):

| Event | Payload |
|---|---|
| `tool.batch_plan` | `calls`, `batches`, `parallelSafe`, `wouldSaveMs` |
| `tool.guardrail` | `rule`, `count`, `tool`, `action`, optional `toolCallId` |
| `tool.disclosure` | `mode`, `tier`, `advertisedTools`, `hiddenTools`, `toolSchemaTokens`, `catalogTokens`, `savedTokens`, `window`, `thresholdPct` |

The run's `surface` payload gains a `disclosure` object (mode, tier, counts,
saved tokens) so a hidden tool is always explainable from the run record. No
raw arguments or results are added to any event.

Operator views: guardrail actions per run and disclosure savings per run are
derived from these events; no new store.

---

## 12. File map

| File | Change |
|---|---|
| `python/harness/config/flags.py` | parallel shadow enum; batch timeout; disclosure/guardrail values |
| `python/harness/tools.py` | `interactive`, `parallel_safe`, `tags`, `domain` fields; no execution change |
| `python/harness/tool_turn.py` | **new**: the ONE preflight/dispatch/postflight flow, contiguous batches, per-call context clone |
| `python/harness/tool_guardrails.py` | **new**: pure rules + decision (reuses `recovery.progress.attempt_digest`) |
| `python/harness/tool_bm25.py` | **new**: pure lexical ranker |
| `python/harness/tool_disclosure.py` | **new**: mode/threshold/tier + catalogue block |
| `python/harness/tool_surface.py` | BM25 search, tags, `availableSources`, lazy alias |
| `python/harness/graph.py` | `tools_node` is wiring; disclosure decision + event; guardrail-halt route |
| `python/harness/routers/recovery.py` | operator reset endpoint |
| `python/harness/context_budget.py` | (no change; reuse `tool_schema_text` for measurement) |
| `python/tests/*` | §8 |

`graph.py` is at its size pin. New logic must live in the new modules; the
graph gains wiring, not bodies.

---

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Parallel reads race on a shared store | Medium | High | Explicit allowlist + §9.2 audit; serial fallback |
| Read tool is rate-limited | Medium | Medium | Keep it serial; per-provider limits; one retry only |
| Guardrail false positive | Medium | Medium | Warn-first, poller allowlist, operator reset |
| Guardrail hides a real transient failure | Low | Medium | Failure streak requires no state change; recovery already classifies |
| Tool missed by BM25 | Medium | Medium | Tiered catalogue, `availableSources`, exact-name boost, eval recall gate |
| Catalogue block eats the savings | Low | Medium | Include it in the token accounting; tier down at the budget |
| Prompt cache is broken by the block | Low | Medium | Build once per run; byte-stable ordering |
| Context clone diverges from the real context | Low | High | Clone only per-call fields; audit; test that a shared service is the same object |
| Batch changes model-visible ordering | Low | High | Index-addressed slots; order test |
| `tool_invoke` bypasses budget/effects | Known | Low | Read-only only; documented; one invoke-per-outer-call; never effectful |

---

## 14. Acceptance / exit criteria

W3 is done when:

1. **Parallel:** 6 × 200 ms read calls finish in ≤ 350 ms at concurrency 6;
   serial and batched results are byte-identical; zero ordering violations; one
   failure is isolated; effectful calls never overlap.
2. **Guardrails:** three identical successful calls halt with a clear message;
   changed args and pollers are allowed; halt rate < 1% of runs in the canary;
   `off` reproduces today.
3. **Disclosure:** recall@5 ≥ 0.90 on the labelled fixture; advertised schema
   tokens fall ≥ 50% on a 1,000-tool surface including the catalogue block;
   effectful tools are never hidden; no missed-tool incident in the canary.
4. **Compatibility:** with every W3 flag off, the prompt, surface, events and
   results match the pre-W3 baseline; zero-config still works with no new
   dependency.
5. **Gate:** `npm run test` and `npx tsc --noEmit` pass; `npm run audit:agent`
   and the offline eval gate stay green; a `CHANGELOG.md` entry per slice.

---

## 15. Implementation status (2026-11-12)

**Landed (core).** W3.0–W3.4 are implemented behind their flags:

- **Flags:** `HARNESS_PARALLEL_TOOLS` (`off|shadow|on`), `HARNESS_TOOL_CONCURRENCY`,
  `HARNESS_TOOL_BATCH_TIMEOUT_S`, `HARNESS_TOOL_GUARDRAILS` (`warn|halt|off`),
  `HARNESS_TOOL_DISCLOSURE` (`auto|on|off`),
  `HARNESS_TOOL_DISCLOSURE_THRESHOLD_PCT`. `HARNESS_LAZY_TOOLS` is honoured as a
  deprecated alias only when the registry flag is unset.
- **One turn:** `tool_turn.py` owns preflight, dispatch and postflight for both
  sequential and parallel modes. `graph.tools_node` is wiring only.
- **Parallel:** contiguous `parallel_safe` batches with a semaphore, batch
  deadline, per-call context clone and index-addressed results. Effectful and
  interactive calls are serial; an effectful call breaks the batch.
- **Read audit:** `parallel_safe=True` is explicit. The first audited set is
  `tool_search` and the three response-contract read-back tools; `clarify` is
  `interactive=True`. Everything else stays serial until audited.
- **Guardrails:** pure `tool_guardrails.py` with a per-attempt ledger, identical
  success calls, cycle detection, failure streak, poller exemption, warn-first
  default and a controlled halt + `tool.guardrail` event. The operator reset is
  `POST /runs/{run_id}/guardrail-reset` (operator-gated).
- **Disclosure:** pure `tool_bm25.py` (name ×4, tags ×2, description ×1, domain
  ×1, exact-name boost), tiered catalogue block (4k/2k/500 token budgets),
  `availableSources` on no-match, `auto` threshold over a KNOWN window, and a
  `tool.disclosure` event plus `surface.disclosure` provenance.
- **Tests:** `test_parallel_tools.py`, `test_tool_guardrails.py`,
  `test_tool_disclosure_bm25.py`, plus extended `test_tool_surface.py`,
  `test_flags.py`, `test_run_effects.py`, `test_size_budget.py`,
  `test_recovery_api.py`. Verified: 1,250 passed / 3 skipped on the
  graph/context/tool/run/recovery group; 2,046 passed / 4 skipped on the
  agent/prompt/plugin/skill/evaluation/persistence group; `audit:agent` 49/49;
  offline eval gate ALL PASS; `npx tsc --noEmit` clean.

Deliberate gaps (rollout, not missing plumbing):

- Parallel stays `off` by default; the `shadow` and `on` modes are implemented
  and tested. Promotion is a canary decision, not a code change.
- Disclosure `auto` is the flag default and only activates above the threshold
  on a known window; the `HARNESS_LAZY_TOOLS` alias is removed after two green
  weeks (W0 flag-removal rule).
- The audited `parallel_safe` set is intentionally small. Adding a tool is a
  one-line change backed by the §9.2 audit.

## 16. Open decisions

1. **Parallel promotion.** Keep the explicit allowlist through the canary, then
   decide with the `tool.batch` timing record whether any broader default is
   justified. Recommendation: keep the allowlist.
2. **Halt UX.** Deterministic stop notice (implemented) vs. a final model turn.
   A model turn can loop, so the deterministic notice stays.
3. **Catalogue tier budgets.** 4k/2k/500 tokens are the shipped starting values;
   adjust only with a measured saved-token regression.
4. **Alias removal date.** Two green weeks after the W3.4 canary.
