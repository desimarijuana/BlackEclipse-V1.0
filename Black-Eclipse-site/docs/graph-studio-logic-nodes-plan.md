---
title: Graph Studio — Logic & Control-Flow Node Improvement Plan
status: In progress
last-verified: 2026-11-01
---

# Logic & control-flow node improvement plan

**Scope:** the 15 node types that carry *logic* in a workflow —
`logic.aggregate`, `logic.deduplicate`, `logic.condition`, `logic.merge`,
`flow.gate`, `logic.switch`, `logic.map`, `logic.filter`, `logic.reduce`,
`logic.wait`, `flow.subworkflow`, `logic.stop`, `flow.for_each`, `flow.repeat`,
`flow.while`.

**What this document is:** an implementation-ready plan. Part 3 is a per-node
specification (ports, config, semantics, errors, compatibility, tests). Part 7 is
a work-breakdown you can turn into tickets. Part 9 is how to ship each change
without breaking saved workflows.

**What it is not:** a decision record. Anything marked **DECISION** needs your
answer before the ticket is started; accepted decisions become an ADR in
`skills/ARCHITECT.md` and a section in `docs/graph-studio.md`.

## 0. Progress

§4 is the audit as it stood when this plan was written. This table is the live
state.

| Item | Status | Notes |
| --- | --- | --- |
| W0.1 `logic.stop` honours `status` | **done** | Was already implemented in the tree (`_stop` reserved key + `_stop_request`); verified and documented. |
| W0.1b `logic.stop` carries a `value` | **done** | New optional data input; terminal capture already reads it. |
| W0.2 `NodeExecContext.control_fired` + `should_cancel` | **done** | `registry.py`, filled by `executor.py`; `control_fired` is empty for the node-test path. |
| W0.3 cancel-aware `logic.wait` | **done** | 100 ms poll; reports the time actually waited. |
| W0.4 kill the silent zero (D3) | **done** | `_item_scope` no longer binds a missing field; `map/filter/reduce` fail honestly. |
| W0.5 `logic.aggregate` empty → `null` (D4) | **done** | `count` stays `0`; `value` port is `nullable`. |
| W0.6 `logic.merge` `first_present` (D5) | **done** | Legacy `first` shares the semantics. |
| W0.7 summary lines | **done** | All 15 nodes emit one line per successful run. |
| W0.8 skip diagnostics name the wire | **done** | `_control_skip_reason`. |
| `logic.condition` | **done** | `If true` / `If false` / `Result`, branch-first; control handles square. |
| W0.9 declared-field-is-read invariant | **done** | `python/tests/test_graph_node_config_usage.py`, scoped to `logic.*`/`flow.*`. |
| W1.4 `logic.switch` case outputs | **done** | `case1`…`case8` + `matched`; first match wins. |
| W1.6 `flow.gate` join | **done** | `in2`/`in3` + `require: any\|all`. |
| W1.8 `logic.deduplicate` modes | **partial** | `keep: first\|last` and `caseInsensitive`; min/max + `duplicates` output still open. |
| W1.14 `flow.while` state | **partial** | object/boolean fields readable in the condition; the shared condition model is still open. |
| W1 otherwise / W2 / W3 | not started | See §8. |

**Node UX work lives in `docs/graph-studio-node-ux-plan.md`** (U1 legibility is
implemented; U2/U3 are not).

---

## 1. Executive summary

The logic pack works, but four of its fifteen nodes cannot express the thing
they are named after, and seven behaviours are outright defects:

| Class | Count | Example |
| --- | --- | --- |
| Defects (the node lies) | 7 | `logic.stop` declares `status: failed` and ignores it |
| Expressiveness ceilings | 8 | `logic.switch` routes every case to one output |
| Structural ceilings | 6 | no loop can contain an inline body |

The plan fixes them in four waves, each independently shippable:

| Wave | Theme | Outcome | Effort |
| --- | --- | --- | --- |
| **W0** | Honesty | No node in the pack can silently lie or return a fake zero | ~4–5 days |
| **W1** | Expressiveness | Every logic node can express its own name; all changes additive | ~10–12 days |
| **W2** | Structure | Typed value language, variadic ports, error routing, inline bodies | ~15+ days (2 ADRs) |
| **W3** | Scale | Concurrency and 100 k-row performance, if measurements justify it | TBD |

Success metrics (measured on the operator side, not vanity):

1. **Zero** silent-zero paths in the pack (grep-able invariant test).
2. A 3-way branch needs **one** `logic.switch` node instead of 1 + 2 conditions.
3. A sector summary (sum, average, count) needs **one** `logic.aggregate`.
4. A loop with a 3-node body needs **no** second saved workflow (W2).
5. Every logic node prints one summary line per run.
6. No logic-node defect class survives: "declared but ignored config key" is
   caught by a test that walks every declared `ConfigField` and asserts the
   executor reads it.

---

## 2. Scope and non-goals

**In scope:** the 15 node contracts, their executors, the scheduler behaviours
they depend on (control gating, cancellation, loop checkpoints), the editor
presentation of their config, and their tests/docs.

**Out of scope (separate efforts):**

- The finance/quant/research/agent/trading node packs, except where they are the
  *body* of a loop or subworkflow.
- The Fabric/durability substrate, schedules, triggers, webhooks.
- A general-purpose scripting node. If someone needs arbitrary code, that is a
  different conversation and a different risk class.
- Reworking the IR document shape. The only IR-level change contemplated is W2.4
  (inline bodies), and it is gated behind an ADR.

---

## 3. Architecture recap — the four things this plan must not break

### 3.1 Every node is declared four times

| Layer | File | Must agree on |
| --- | --- | --- |
| Editor contract | `src/lib/graph-studio/registry.ts`, `registry-transform.ts` | ports, zod schema, defaults, modes, capabilities, side effects |
| Editor presentation | `src/lib/graph-studio/config-fields.ts` | label, kind, inline, quick, options, help |
| Manifest | `registry.manifest.json` (generated by `npm run graph:manifest`) | ports (id/name/type/kind/optional/nullable), config field names/kinds/constraints |
| Runtime | `python/harness/graph_runtime/nodes.py` · `table_nodes.py` · `loop_nodes.py` | `NodeDef` ports + `ConfigField`s + executor |

`python/tests/test_graph_registry_parity.py` fails the build when a side is
missed. **Consequence for planning:** each ticket below is deliberately
self-contained across all four layers. A "15-node sweep" PR is not schedulable.

### 3.2 Control ports gate execution, never values

- An executor returns reserved `_control: [names]`; the executor refuses a name
  that is not a declared control output.
- `_control_satisfied` runs a node if **any** wired control input fired. There is
  no AND today (W1.6 adds one without changing the default).
- A non-fired branch is `skipped`; dataflow then skips everything below it, so
  if/else falls out of the scheduler.
- A node whose required input never materialised is `skipped` with
  `error_code: upstream_failed`, never run with a null placeholder.

### 3.3 Input resolution is `wire → node literal → optional/null`

Mirrored in `validation.ts::CONFIG_FALLBACK`, `compiler.py::_CONFIG_FALLBACK_*`
and `executor.py::_resolve_inputs`. Any new "value may come from config" rule
must be added to **all three**.

### 3.4 Executors are pure and the scheduler owns failure

Executors get a `NodeExecContext` with no store and no network. Timeouts,
retries, cancellation and output validation live in `executor.py`. A logic node
must never sleep on a resource, open a file, or catch its own cancellation.

**Invariant to preserve:** two runs of the same graph with the same inputs
produce byte-identical node outputs. Any concurrency (W1.7) must keep result
ordering index-based.

---

## 4. Current-state audit

Read from the code, at `registry.ts@1.0.0` / `nodes.py` as of 2026-11-01.

### 4.1 Defects

| # | Node | Observed behaviour | Why it matters |
| --- | --- | --- | --- |
| **D1** | `logic.stop` | `_exec_stop` returns `{"stopped": True}`; the declared `status` field is never read | A guard-rail graph reports green when it should be red |
| **D2** | `logic.stop` | declares no data input, but `_run_node` reads `inputs["value"]` for the terminal payload | A graph ending in Stop emits `{}`/`None` |
| **D3** | `logic.map/filter/reduce` | `_item_scope` binds `value = 0.0` when a row has no numeric field | `filter` on a text field drops **every** row; `map` returns zeros |
| **D4** | `logic.aggregate` | empty input → `0.0` for sum/avg/min/max/median/stddev/percentile | "no rows" indistinguishable from "sum is 0" (honest-data violation) |
| **D5** | `logic.merge` (`first`) | `a if a is not None else b` | empty array/string/0 beats a populated `b` — the exact case a merge exists for |
| **D6** | `logic.wait` | `time.sleep(ms)` up to 30 s; cancel only checked between nodes | cancel is unresponsive for up to 30 s |
| **D7** | `logic.switch` | all matches fire the single `matched` output | 3-way routing needs 2 extra condition nodes |

Plus one structural defect:

| **D8** | `flow.while` | condition reads only `_numeric_state` (scalar, or `value`/`state`/`result`) | a body returning `{done: true}` exits immediately; a string state loop is impossible |

### 4.2 Expressiveness ceilings

| Node | Today | Cannot express |
| --- | --- | --- |
| `logic.condition` | one comparison, `compareTo` is a static string | AND/OR, wire-vs-wire, `contains`/`matches`/`in`/`between`/`isNull`, dates |
| `logic.switch` | comma string, one output | distinct branches, ranges, regex, a comma inside a value |
| `logic.merge` | `first` / `object` | concat, union, deep merge, coalesce, "which branches arrived" |
| `logic.map/filter/reduce` | numeric formula; items must be numbers or numeric-field objects | strings, nulls, booleans, row paths, building an object, a non-numeric accumulator |
| `logic.aggregate` | one metric | sum + avg + count in one pass, `countDistinct`, first/last, null policy |
| `logic.deduplicate` | keep first | keep last, keep latest-by-date, case-insensitive, report dropped rows |
| `flow.gate` | passthrough, OR semantics | acting as a join (AND), a `done` output |
| `flow.subworkflow` | one input, one output, 600 s fixed | input mapping, choosing a child terminal, timeout config, per-call error isolation |
| `flow.for_each` | sequential, bare `results` array | which item failed, bounded concurrency, truncation count |
| `flow.repeat` | final state only, config-only `count` | collecting per-iteration outputs, a dynamic count |

### 4.3 Structural ceilings

| # | Gap | Effect |
| --- | --- | --- |
| S1 | No inline body for loops/subworkflows | a 5-line loop needs a second saved workflow + version + editor trip |
| S2 | No error routing (skipped ≠ failed) | "on failure take this path" is unbuildable |
| S3 | No variadic ports | `merge` is stuck at 2, `switch` at 1 output, `aggregate` at 1 array |
| S4 | No per-node summary output | a merge that received 1 of 2 branches looks identical to one that received 2 |
| S5 | Loop nodes are excluded from node testing | `ORCHESTRATED` set in `node-test-ui.ts` |
| S6 | Silent coercion in 3 places | one wrong decision (`_numeric_operand`, `_item_scope`, `_numeric_state`) applied three times |

---

## 5. Design principles for every ticket in this plan

1. **Additive or versioned.** Never change the meaning of an existing config
   value. New behaviour is a new defaulted field, a new enum member, or a new
   optional port. A semantic change needs `strictValues`-style opt-in or a
   `type@version` bump (see §9).
2. **No scheduler special-cases.** If a node needs new execution context (e.g.
   which control inputs fired), add it to `NodeExecContext` — do not add
   `if node.type == ...` branches in `executor.py`.
3. **Errors are data, not crashes.** A bad config or input produces a node-level
   failure with a readable message. Silent zeros, silent skips and silent
   truncation are forbidden.
4. **One evaluator.** Conditions (`logic.condition`, `flow.gate`, `flow.while`)
   and expressions (`map/filter/reduce`, `transform.formula`) get one shared
   module each. Never a second implementation.
5. **Bounded.** Every new field gets a hard bound (length, count, depth, time)
   and a documented failure when the bound is hit.
6. **Observable.** Every node emits one human summary per successful run.
7. **Testable in isolation.** New pure nodes must satisfy the node-test envelope
   (`none`/`read` side effects). Orchestrated nodes get a "validate body" action
   instead (W2.5).

---

## 6. Target specifications, node by node

Conventions used below:

- `…` = unchanged from today.
- Ports table columns: id · type · kind · optional · new?
- Config tables list **only** new or changed fields; everything not listed is
  unchanged.
- "Compat" states exactly what an existing saved graph does after the change.

### 6.1 `logic.stop` — v1.0.0, behaviour fix (W0)

**Ports**

| id | type | kind | optional | new |
| --- | --- | --- | --- | --- |
| `in` | any | control | yes | — |
| `value` | any | data | yes | **new** |
| `stopped` | boolean | data | — | — |

**Semantics.** `value` becomes the terminal payload (fixes D2). `status` is
honoured: `succeeded` ends the run successfully; `failed` ends the run as
`failed` with `error_code: "stopped"` and the configured `message` as the error.
`stops_run` stays true, so downstream nodes are `skipped` either way.

**Compat.** Graphs that never used `status: failed` are unchanged. Graphs that
did were already misreporting — this is a fix, not a semantic change, and needs
no compat flag.

**Errors.** None new. Empty `message` defaults to `"run stopped"`.

**Tests.** `test_graph_control_flow.py`: failed stop → run status failed;
value passthrough reaches the run output; downstream skipped.

### 6.2 `logic.wait` — v1.0.0, behaviour fix (W0) + additive (W1)

**Ports.** Unchanged.

**Config**

| key | kind | default | bound | wave |
| --- | --- | --- | --- | --- |
| `ms` | integer | 0 | 0 … 86 400 000 | — |
| `until` | string (ISO-8601) | `""` | when set, wins over `ms` | W1 |
| `jitterMs` | integer | 0 | 0 … 60 000 | W1 |

**Semantics (W0).** Sleep in ≤ 100 ms slices, checking cancellation each slice.
A cancelled wait returns immediately (the run is cancelled by the scheduler);
`waitedMs` reports the **actual** elapsed milliseconds, not the requested value.
Durable runs keep the existing `DeferredWait` path and emit
`"paused for 5000 ms; the job will resume"`.

**Semantics (W1).** `until` computes `max(0, until - now)` once, then behaves
like `ms`; an `until` in the past waits 0 and emits a warning line. `jitterMs`
adds a deterministic-per-run jitter (`hash(run_id + node_id) % jitter`) so a
scheduled fan-out does not thump.

**Compat.** `ms` semantics unchanged; only cancellation and the reported value
become truthful.

### 6.3 `logic.condition` — v1.0.0, additive (W1)

**Ports**

| id | type | kind | optional | new |
| --- | --- | --- | --- | --- |
| `value` | any | data | — | — |
| `compareTo` | any | data | yes | **new** (wired value wins over the config string) |
| `true` / `false` | any | control | — | — |
| `result` | boolean | data | — | — |

**Config**

| key | kind | default | notes |
| --- | --- | --- | --- |
| `operator` | enum | `truthy` | **legacy** path, unchanged |
| `compareTo` | string | `""` | **legacy** path |
| `combinator` | enum `all\|any\|none` | `all` | group logic |
| `conditions` | array ≤ 8 of `{ path, operator, value }` | `[]` | when non-empty, replaces the legacy pair |

Operators (adds to the existing seven):
`contains`, `startsWith`, `endsWith`, `matches` (bounded pattern, 200 chars, no
backreferences), `in` (comma list), `between` (two comma values, inclusive),
`isNull`, `isEmpty`, `isNotEmpty`.

`path` is a dotted path into `value` (empty = the whole value). This is the same
path resolver as the tabular nodes (`values.py::resolve_path`), so
`conditions: [{path: "signal", operator: "eq", value: "buy"}]` works on a row.

**Compat.** Empty `conditions` → the legacy single comparison, byte-identical. The
UI writes `conditions` only when the operator is not truthy or a path is set, and
migrates the legacy pair on first open **without** deleting the legacy keys.

**Errors.** Unknown operator; invalid regex (names the pattern); numeric
comparison on a non-numeric (unchanged, with the series warm-up message kept).

### 6.4 `logic.switch` — v1.0.0, additive (W1)

**Ports**

| id | type | kind | new |
| --- | --- | --- | --- |
| `value` | any | data | — |
| `case1` … `case8` | any | control | **new** |
| `matched` | any | control | — (still fires for every match) |
| `default` | any | control | — |
| `matchedIndex` | number | data | **new** |
| `matchedValue` | any | data | **new** |
| `matchedLabel` | string | data | **new** |

**Config**

| key | kind | default | notes |
| --- | --- | --- | --- |
| `cases` | string | `""` | **legacy** comma list |
| `caseList` | array ≤ 8 of `{ value, label?, kind: value\|range\|regex }` | `[]` | preferred |
| `caseInsensitive` | boolean | false | text comparison only |

**Semantics.** Evaluate cases in order, first match wins. Fire `caseN` (N = index
+ 1, only when ≤ 8) **and** `matched`; fire `default` when nothing matches and
`matchedIndex = -1`. Firing a control output that has no wire is a no-op, so
existing graphs that only wire `matched` are unaffected; new graphs wire `caseN`.
`range` uses `a..b` inclusive; `regex` is the same bounded matcher as
`condition`. `matchedValue` is the matched case's configured value;
`matchedLabel` its label (or `""`).

**Compat.** `caseList` empty → parse `cases` exactly as today; `matched`/`default`
timing unchanged; new outputs are simply never wired in old graphs.

**Errors.** A `range` with a non-numeric bound or `a > b`; an invalid `regex`; a
`caseList` entry that is not an object.

### 6.5 `logic.merge` — v1.0.0, additive (W1)

**Ports**

| id | type | kind | optional | new |
| --- | --- | --- | --- | --- |
| `in` | any | control | yes | **new** |
| `a` | any | data | — | — |
| `b` | any | data | yes | — |
| `c` | any | data | yes | **new** |
| `done` | any | control | — | **new** |
| `value` | any | data | — | — |
| `received` | array of port ids | data | — | **new** |
| `count` | number | data | — | **new** |

**Config**

| key | kind | default |
| --- | --- | --- |
| `strategy` | enum `first_present\|object\|array\|union\|deep\|coalesce` | `first_present` |
| `dedupe` | boolean | false (array only) |
| `caseInsensitive` | boolean | false (union only) |
| `onMissing` | enum `skip\|error` | `skip` |
| `aKey`/`bKey`/`cKey` | string | `a`/`b`/`c` |

**Semantics.**

- *Absent* means `None`, `""`, `[]`, or `{}` (this is the D5 fix).
- `first_present`: first non-absent of `a, b, c`.
- `coalesce`: first non-null (empty string/array allowed) — the date-fallback idiom.
- `object`: `{ [aKey]: a, … }` including only received ports.
- `array`: concatenate arrays; a present non-array is an error.
- `union`: like `array` then identity-dedupe (same rule as `logic.deduplicate`:
  `1`, `1.0` and `"1"` are one row).
- `deep`: recursive object merge, right wins, depth ≤ 8, a type conflict at the
  same key is an error.
- `onMissing: error` turns "no branch arrived" into a node failure.

**Compat.** Legacy `first` is accepted as an alias for `first_present` and
**changes one behaviour** (D5). Documented in the node docs; no graph can
legitimately depend on "an empty `a` wins over a populated `b`". The release note
calls it out.

**Errors.** Non-array under `array`/`union`; type conflict under `deep`; empty
under `onMissing: error`.

### 6.6 `flow.gate` — v1.0.0, additive (W1)

**Ports**

| id | type | kind | optional | new |
| --- | --- | --- | --- | --- |
| `in` | any | control | — | — |
| `in2` | any | control | yes | **new** |
| `in3` | any | control | yes | **new** |
| `value` | any | data | yes | — |
| `done` | any | control | — | **new** |

**Config:** `require: enum any|all` (default `any`), `whenFired: boolean`
(default `true`; `false` makes the gate a "join that did **not** happen" guard).

**Semantics.** `any` = today. `all` = run only when every **wired** control input
fired from a succeeded source. This needs to know which of its own control inputs
fired, so §7.1 adds `control_fired: dict[str, bool]` to `NodeExecContext`. `done`
fires on success so a gated chain can own a continuation without a helper gate.

**Compat.** One wired control input behaves identically (`any`/`all` coincide).

**Errors.** `require: all` with zero wired control inputs is a compile-time error
(an AND of nothing is not a gate).

### 6.7 `logic.map` / `logic.filter` / `logic.reduce` — v1.0.0, additive (W1) + language (W2)

**Shared changes (W1).**

- `_as_items` accepts any JSON item (string, boolean, null, object, array).
- Scope binds `row` (the whole item) in addition to `value`/`index`; a **missing**
  field binds `MISSING` (never `0.0`) — fixes D3.
- New config `language: enum v1|v2` default `v1`; `v2` is W2.
- New config `onError: enum fail|skip|default` default `fail`; `skip` drops the
  item, `default` uses `defaultValue`. New outputs `errors` (number) on all three,
  and `skipped` on `map`.

**`logic.map`** adds: `defaultValue` (any JSON), output `errors`.
**`logic.filter`** adds: `path` (dotted, default `""` = the whole item becomes
`value`), output `errors`.
**`logic.reduce`** adds: `initial` becomes **any JSON** (not forced to `float`),
`acc` may be an object/array, output `errors`. `initial` of `{}` + expression
`object(...)` (W2) is how you reduce to a record.

**Compat.** With `strictValues` (§9) still `false` and `language: v1`, D3 is the
one intended change: a row with no numeric field now **errors** instead of
silently reading 0. That is the defect fix — announce it in the release note.

**W2 language surface** (gated by `language: v2`): string literals, `null`,
booleans, `len/lower/upper/trim/split/join/contains/startsWith/endsWith/matches`,
`coalesce/isnull/to_number/to_text`, `field(path)`, `object(k, v, …)`,
`array(a, b, …)`. Still no `eval`, no attribute access, bounded tokens/length.

### 6.8 `logic.aggregate` — v1.0.0, additive (W1)

**Ports.** Unchanged plus `rows` (number) and `groupCount` (number); `value`
becomes `nullable: true` (null when there are no rows).

**Config**

| key | kind | default |
| --- | --- | --- |
| `field`/`op`/`percentile` | — | **legacy** single metric |
| `metrics` | array ≤ 8 of `{ field, op, as, percentile? }` | `[]` |
| `nullPolicy` | enum `skip\|zero\|error` | `skip` |
| `sortBy` | enum `group\|value` | `group` |
| `order` | enum `asc\|desc` | `asc` |

New `op` members: `countDistinct`, `first`, `last`, `sumsq`, `mode`.

**Semantics.** `metrics` non-empty → one pass per metric; each group object gets
one key per `as` (default `<op>_<field>`). Legacy fields are merged into a single
metric at execution time, so both paths share one implementation. `nullPolicy`
decides what a null/non-numeric value does (today = `skip`). Empty input → every
metric `null` except `count*` = 0, `rows: 0`, `groups: []` (D4 fix). `min`/`max`
keep type (dates/strings compare naturally) instead of coercing to float.

**Compat.** Legacy single-metric output shape `{value, groups:[{…groupBy, value, count}]}`
is preserved **when `metrics` is empty**. With `metrics` set, groups additionally
carry the metric keys; `value` and `count` remain for compatibility.

**Errors.** A metric without a field for a non-count op; a duplicate `as` name;
`op: percentile` with a bad percentile.

### 6.9 `logic.deduplicate` — v1.0.0, additive (W1)

**Config**

| key | kind | default |
| --- | --- | --- |
| `keys` | string | `""` |
| `keep` | enum `first\|last\|min\|max` | `first` |
| `by` | string (dotted) | `""` (required for min/max) |
| `caseInsensitive` | boolean | false |
| `nullKeys` | enum `keep\|drop` | `keep` |

**Ports.** Adds `duplicates` (array, bounded to the first 1 000 dropped rows) and
`kept` (number).

**Semantics.** `keep: min|max` keeps the row with the smallest/largest `by` value
per key (numeric or ISO-date aware); `caseInsensitive` folds text keys only;
`nullKeys: drop` refuses rows whose key is null. Order of output is first-seen
order for `first`/`min`/`max`, and last-seen order for `last`.

**Compat.** Defaults reproduce today exactly.

### 6.10 `flow.subworkflow` — v1.0.0, additive (W1)

**Ports**

| id | type | kind | optional | new |
| --- | --- | --- | --- | --- |
| `input` | any | data | yes | — |
| `output` | any | data | — | — |
| `runId` | string | data | — | — |
| `status` | string | data | — | **new** |
| `error` | string | data | yes, nullable | **new** |

**Config**

| key | kind | default | notes |
| --- | --- | --- | --- |
| `workflowId` | string | `""` | — |
| `version` | integer | 1 | `0` = current (W1, see below) |
| `inputMode` | enum `direct\|object` | `direct` | `object` wraps `{input: …}` |
| `outputMode` | enum `terminal\|named` | `terminal` | `named` picks one child terminal |
| `outputKey` | string | `""` | required when `outputMode: named` |
| `timeoutMs` | integer | 600 000 | 1 000 … 3 600 000 |
| `onError` | enum `fail\|continue` | `fail` | `continue` returns `status: "failed"` + `error` |

**Semantics.** `version: 0` resolves to the workflow's current version and is
recorded in the run event log; the inspector shows a **Pin** action and a
"floating" warning. `outputMode: named` selects one terminal of the child by its
node id (`outputKey`) and errors when the child has no such terminal.
`onError: continue` converts a child failure into node success with
`status: "failed"`, `error: <child error>` and `output: null`, so a caller can
gate on `status` — the W2 error-routing primitive's first half.

**Compat.** All defaults match today (`direct`, `terminal`, fail).

**Migration note.** With `version: 0` allowed, both `validation.ts` and
`compiler.py` must accept it and the front-door bundle loader must resolve
"current" at dispatch time (it already loads versions from JDDS).

### 6.11 `flow.for_each` — v1.0.0, additive (W1)

**Config**

| key | kind | default |
| --- | --- | --- |
| `maxIterations` | integer | 100 (≤ 1 000) |
| `maxDurationMs` | integer | 0 |
| `continueOnError` | boolean | false |
| `resultMode` | enum `outputs\|detailed` | `outputs` |
| `concurrency` | integer 1…4 | 1 |
| `onEmpty` | enum `succeed\|fail` | `succeed` |

**Ports.** Adds `failed` (number) and `truncated` (number).

**Semantics.** `detailed` returns `[{ index, item, status, output, error }]`;
`outputs` stays a bare array (today's shape). `concurrency > 1` runs up to N
iteration bodies at once; **results are always ordered by index** and child run
ids stay `<parent>:<node>:i<N>`, so resume and determinism are unaffected.
`truncated` reports `len(items) - maxIterations` when the input is clamped.
`onEmpty: fail` makes `items: []` a node failure (a loop that silently does
nothing is a bug in the caller).

**Errors.** `concurrency` outside 1…4; a non-array `items` (unchanged).

### 6.12 `flow.repeat` — v1.0.0, additive (W1)

**Ports.** Adds `count` (number, optional input; config is the fallback),
`results` (array), `failed` (number).

**Config.** Adds `collect: boolean` (default false), `continueOnError` (default
false).

**Semantics.** `count` from the wire wins over config, clamped to 1…1 000.
`collect` returns every iteration output in `results`; otherwise `results` is `[]`
and only the final `state` is returned (today's shape). `failed` counts
`continueOnError` skips.

### 6.13 `flow.while` — v1.0.0, additive (W1)

**Config**

| key | kind | default |
| --- | --- | --- |
| `condition` | string | `value > 0` (**legacy** expression) |
| `combinator`/`conditions` | — | same model as `logic.condition` |
| `doWhile` | boolean | false |
| `collect` | boolean | false |
| `maxIterations` | integer | 100 |
| `maxDurationMs` | integer | 0 |

**Ports.** Adds `results` (array).

**Semantics.** When `conditions` is set, the shared condition module evaluates it
against a scope of `{ state, value, index, iterations }` where `state` is the
**whole** previous output (path access allowed) — fixes D8. `doWhile` runs the
body once before the first test. `collect` returns per-iteration outputs.

**Compat.** An empty `conditions` array keeps the legacy expression evaluated
against the same numeric projection as today.

---

## 7. Cross-cutting enablers

These unlock several nodes at once and must land **before** the nodes that need
them. They are the only items in W0/W1 that touch shared infrastructure.

### 7.1 E1 — Execution context additions (W0)

Add to `NodeExecContext` (`registry.py`, both construction sites
`executor.py:443` and `service.py:163`):

| field | type | purpose |
| --- | --- | --- |
| `control_fired` | `dict[str, bool]` | which of this node's wired control inputs fired (gate AND, better skip messages) |
| `should_cancel` | `Callable[[], bool]` | cancel-aware wait and future long nodes |

Both are defaulted, so existing executors are unaffected. The scheduler fills
them from `_fired` / `self._cancel`. Also improve the skip message: when a node
is skipped because its control input did not fire, name the wire(s), e.g.
`its control input "in" did not fire (from node "if1")`.

### 7.2 E2 — Summary lines (W0)

One `context.emit(...)` per successful execution. Canonical strings:

| Node | Message |
| --- | --- |
| `logic.condition` | `true (close 12.4 gt 10)` / `false …` |
| `logic.switch` | `case 2 of 3 ("growth")` / `default` |
| `logic.merge` | `merged 2/3 inputs (a, c)` |
| `flow.gate` | `gate passed (2/2 control inputs)` |
| `logic.aggregate` | `42 rows → 5 groups, 1 metric` |
| `logic.deduplicate` | `kept 42 of 50 rows (8 duplicates)` |
| `logic.map/filter` | `mapped 42 items (0 errors)` / `kept 30 of 42 rows` |
| `logic.reduce` | `reduced 42 items → 1234.5` |
| `logic.wait` | `waited 500 ms` / `paused 5000 ms; the job will resume` |
| `logic.stop` | the configured message, then `run stopped (failed)` |
| `flow.for_each` | `8/10 items, 2 failed, truncated 3` |
| `flow.repeat` | `10 iterations, 0 failed` |
| `flow.while` | `4 iterations (condition false), 4 collected` |
| `flow.subworkflow` | `child wf_x@3 succeeded in 1.2 s` |

### 7.3 E3 — Structured list config fields (W1)

`metrics`, `conditions`, `caseList` are lists of objects. **No manifest change is
needed**: `configKind` already maps an array default to `array`, and Python has
`ConfigKind "array"`. Work required:

- `ConfigFieldDef.kind` gains `'rows'`; a renderer in `config-field.tsx`
  (add/remove/reorder rows, per-row sub-fields driven by a small `columns` spec).
- Persisted value is a real JSON array of objects (not a JSON string).
- Per-node zod schema validates shape and row count (`max(8)`); Python validates
  the same in the executor and reports the offending row index.
- `config-fields.test.ts` gains a case per new rows field.

**Follow-up (optional):** manifest `maxItems` so the parity test can compare row
bounds. Not required for correctness because both sides validate.

### 7.4 E4 — Shared condition module (W1)

New `python/harness/graph_runtime/conditions.py`:

```
evaluate(conditions, combinator, scope, *, path_resolver) -> bool
```

Used by `logic.condition`, `flow.gate` (optional `when`), and `flow.while`.
One operator table, one regex bound, one error vocabulary. Tests live in
`test_graph_conditions.py`; the three nodes then only marshal config.

### 7.5 E5 — Typed value language (W2, ADR required)

New `graph_runtime/expr.py` with a `Value` union and a bounded parser. Keep
`evaluate_formula(expr, vars: dict[str, float]) -> float` as a thin wrapper so
`transform.formula` and every existing graph are untouched. Gate with
`language: v1|v2`; flip the default at IR v3.

**Hard constraints:** ≤ 2 000 chars, ≤ 400 tokens, ≤ 32 call depth, no
attribute access, no I/O, no user-defined functions, deterministic, every failure
a readable node error. This is the single riskiest item in the plan — it needs an
ADR and a fuzz/property test suite, not just examples.

### 7.6 E6 — Variadic ports (W2, ADR required)

`PortDef` gains `variadic?: { min: number; max: number }` in TS and Python;
manifest carries it (`ManifestPort.variadic`, `manifestVersion: 2`). Touch list:

- `registry.ts` / `nodes.py` port declarations
- `manifest.ts` + regenerate JSON + parity test
- `validation.ts`: required-input rule becomes "at least `min` of the group"
- `compiler.py`: same rule (`_inputs_map` keyed by the declared ids)
- `executor.py::_resolve_inputs`: iterate the group
- canvas: dynamic port rows (`eclipse-node.tsx`), `canConnect`
- inspector: port list

Enables: `logic.merge` at N inputs, `logic.switch` at N case outputs,
`logic.aggregate` over several arrays.

### 7.7 E7 — Error routing (W2)

`NodeDef`/`NodeDefinition` gains `onError: 'fail' | 'route'` and a declared
`error` control output plus `errorMessage`/`errorCode` value outputs on the logic
pack. A routed failure fires `error` instead of failing the node, and the
scheduler must **not** mark downstream data nodes as `upstream_failed` when the
route fired. This is a scheduler change with a clear contract — the first thing
in this plan that legitimately touches `executor.py` semantics.

### 7.8 E8 — Inline bodies (W2, ADR required)

**DECISION.** Two options:

- **Option A (recommended, ~3–4 days):** no IR change. The node card gets
  **Edit body** (opens the child workflow in a second editor tab with a
  breadcrumb) and **Create body from selection** (extracts selected nodes into a
  new workflow, pins it, and replaces the selection with the loop/subworkflow
  node). Fixes the UX cliff without touching the IR.
- **Option B (~3+ weeks):** `body: { nodes, edges }` sub-IR on the node. Correct
  long-term but duplicates validation, editing, undo, layout and canvas
  rendering for nested graphs, and needs an IR version bump.

Start with A. If A proves insufficient in real use, write the B ADR with
measured pain.

### 7.9 E9 — Testing orchestrated nodes (W2)

`node-test-ui.ts` excludes the four orchestrated types. Replace the exclusion
with a **Validate body** action: `POST /api/graph-runs/node-test` gains an
optional `body` bundle the front door resolves (it already knows how to load
pinned subworkflows via `subworkflow-bundle.ts`); the runtime compiles the child
with the parent's grants and returns diagnostics without executing. Keeps the
"never run a graph from a node test" rule intact.

---

## 8. Work breakdown

Effort: **S** ≤ 0.5 d · **M** ≤ 1.5 d · **L** ≤ 3 d · **XL** > 3 d (needs ADR).
Every ticket closes only when §11 (Definition of done) is satisfied.

### Wave 0 — honesty (release `logic-honesty`)

| ID | Task | Files | Depends | Effort |
| --- | --- | --- | --- | --- |
| W0.1 | `logic.stop` honours `status`, carries `value` (D1, D2) | `registry.ts`, `nodes.py`, `executor.py` (terminal read is already generic), `config-fields.ts` help text | — | S |
| W0.2 | `NodeExecContext.control_fired` + `should_cancel` (E1) | `registry.py`, `executor.py:443`, `service.py:163` | — | M |
| W0.3 | `logic.wait` cancel-aware, truthful `waitedMs` (D6) | `nodes.py` | W0.2 | S |
| W0.4 | Kill silent zero in `_item_scope` (D3) | `nodes.py`, `config-fields.ts` (help), `graph-studio.md` | W0.2 | M |
| W0.5 | `logic.aggregate` empty-input `null` (D4) | `table_nodes.py`, registry `nullable` on `value` port | — | S |
| W0.6 | `logic.merge` `first_present` (D5) | `nodes.py`, registry enum, docs | — | S |
| W0.7 | Summary lines for all 15 nodes (E2) | executors only | — | M |
| W0.8 | Better skip diagnostics (name the wire) | `executor.py` | W0.2 | S |
| W0.9 | Invariant test: every declared `ConfigField` is read by some executor (kills "declared but ignored" defects — would have caught D1) | `python/tests/test_graph_node_config_usage.py` (new) | — | M |

**Exit criteria:** D1–D6 closed with regression tests; `npm run test`,
`npx tsc --noEmit`, `npm run demo:transform` green; release note lists the two
behaviour changes (D3, D5).

### Wave 1 — expressiveness (release `logic-expressiveness`)

Order matters: E3 and E4 first, then nodes.

| ID | Task | Files | Depends | Effort |
| --- | --- | --- | --- | --- |
| W1.1 | E3 rows editor + zod shape validation | `types.ts`, `config-field.tsx`, `config-fields.ts`, node schemas | — | M |
| W1.2 | E4 `conditions.py` + operator table + tests | new module + `test_graph_conditions.py` | — | L |
| W1.3 | `logic.condition` v2 fields + `compareTo` port | registry, `nodes.py`, `config-fields.ts`, docs | W1.1, W1.2 | M |
| W1.4 | `logic.switch` case outputs + `caseList` | registry (ports), `nodes.py`, `config-fields.ts` | W1.1 | L |
| W1.5 | `logic.merge` strategies + ports + `received` | registry, `nodes.py`, `config-fields.ts` | — | L |
| W1.6 | `flow.gate` `require`/`whenFired`/`in2`,`in3`/`done` | registry, `nodes.py`, `validation.ts` (all-with-zero rule) | W0.2 (control_fired) | M |
| W1.7 | `logic.aggregate` `metrics`, ops, `nullPolicy`, `rows` | `table_nodes.py`, registry, `config-fields.ts` | W1.1 | L |
| W1.8 | `logic.deduplicate` keep modes + `duplicates` | `table_nodes.py`, registry | — | M |
| W1.9 | `logic.wait` `until`/`jitterMs` | `nodes.py`, `compiler.py` test-run limit interaction | W0.3 | S |
| W1.10 | `logic.map/filter/reduce` row scope, any-JSON items, `onError`, `path` | `nodes.py`, registry, `config-fields.ts` | W0.4, W1.1 | L |
| W1.11 | `flow.subworkflow` input/output modes, `timeoutMs`, `onError`, `version: 0` | registry, `executor.py`, `validation.ts`, `compiler.py`, `subworkflow-bundle.ts` | — | L |
| W1.12 | `flow.for_each` `detailed`, `concurrency`, `truncated`, `onEmpty` | `loop_nodes.py`, `executor.py` | W0.2 | L |
| W1.13 | `flow.repeat` `collect`, `count` port, `continueOnError` | `loop_nodes.py`, `executor.py` | — | M |
| W1.14 | `flow.while` shared conditions, `doWhile`, `collect` | `executor.py::_loop_condition`, `loop_nodes.py` | W1.2 | M |
| W1.15 | Determinism test: `for_each` with `concurrency: 4` is byte-identical to 1 | `test_graph_loops.py` | W1.12 | S |

**Exit criteria:** every §6 spec implemented with a legacy-default test; the
release note lists new fields per node; docs updated.

### Wave 2 — structure (two releases + two ADRs)

| ID | Task | ADR | Effort |
| --- | --- | --- | --- |
| W2.1 | E5 typed value language + fuzz/property tests | ADR needed | XL |
| W2.2 | Flip `map/filter/reduce/formula` to `language: v2` behind the flag | — | M |
| W2.3 | E6 variadic ports + manifest v2 + validator/executor/canvas | ADR needed | XL |
| W2.4 | Adopt variadic: merge N inputs, switch N outputs, aggregate M arrays | — | L |
| W2.5 | E7 error routing (`onError: route`) + scheduler contract | ADR needed | L |
| W2.6 | E8 inline bodies — Option A | DECISION first | L |
| W2.7 | E9 validate-body for orchestrated nodes | — | M |

### Wave 3 — scale (only with measurements)

| ID | Task | Trigger |
| --- | --- | --- |
| W3.1 | `logic.aggregate` single-pass at 100 k rows | a benchmark shows > 1 s |
| W3.2 | `for_each` concurrency against the Fabric budget | concurrency > 1 is used in production |
| W3.3 | `logic.wait` "queued" surfacing in the UI | operator reports a hang |

---

## 9. Versioning, compatibility, migration

Per ADR-H344: **additive changes keep `type@version`; removals/renames do not.**

### 9.1 Three categories in this plan

| Category | Examples | Handling |
| --- | --- | --- |
| Pure bug fix | D1, D2, D4, D6, D7, D8 | No version change, no flag. Call it out in the release note. |
| Intended behaviour change | D3 (missing field → error), D5 (`first` → `first_present`) | No version change (both are wrong today), **but** ship `strictValues` for D3 so an operator can opt out for one release. |
| Additive | every W1 field/port/output | Same `type@version`. Defaults reproduce today. |

### 9.2 `strictValues`

Add `strictValues: boolean` (default `false`) only to `logic.map`, `logic.filter`,
`logic.reduce` and `logic.aggregate`.

- `false` → today's coercion for the **values** path, except D3's missing-field
  case, which always errors (a missing field is not a coercion).
- `true` → a non-numeric/non-comparable value is an error instead of skipped.
- The validator records a **warning** on graphs that read a field which is absent
  in some rows when `strictValues` is off.
- Removed at IR v3 when `language: v2` becomes the default.

Two flags total (`strictValues`, `language`), both with a scheduled removal. No
third flag without an ADR.

### 9.3 `version: 0` for subworkflows

Allowed only for `flow.subworkflow` (not loops, where a body must be stable for
the iteration checkpoint to mean anything). Resolution happens in the front-door
bundle loader at dispatch time; the run event log records the resolved version.
The editor shows a floating-pin warning and a **Pin** action.

### 9.4 Migration rules for saved graphs

- Anything added has a default, so `parseWorkflowIR` accepts old documents with
  no migration.
- `migrations.ts` gains an entry only if a field is **renamed**; none are in this
  plan.
- A graph saved with `metrics: []` and `caseList: []` must execute exactly as
  before — this is the single most important test per node.

---

## 10. Test plan

### 10.1 Per-node test matrix (every row is a required test)

| Node | Cases |
| --- | --- |
| `logic.stop` | failed stop → run failed + code; value passthrough; downstream skipped; empty message default |
| `logic.wait` | cancel during wait returns promptly; `waitedMs` truthful; durable defer path; test-run 5 s cap; `until` in the past; jitter deterministic per run |
| `logic.condition` | legacy pair unchanged; each new operator; combinator all/any/none; path into a row; wired `compareTo` beats config; invalid regex message |
| `logic.switch` | legacy comma path unchanged; `caseN` fires exactly one; `matched` still fires; default + `matchedIndex = -1`; range; regex; 9 cases → index 9 fires only `matched`; comma inside a legacy value still breaks (documented) |
| `logic.merge` | each strategy; empty `a` no longer wins; `received`/`count`; `onMissing: error`; deep type conflict; union identity (`1`/`"1"`) |
| `flow.gate` | `any` unchanged; `all` waits for every wired input; `all` with zero wired inputs is a compile error; `done` fires |
| `logic.map/filter/reduce` | string array now works; missing field errors (not 0); object row path; `onError` skip/default + `errors` count; reduce to object (`initial: {}`); legacy numeric graphs unchanged |
| `logic.aggregate` | legacy single metric byte-identical; multi-metric; `countDistinct`; empty input → null; `nullPolicy` three modes; group ordering numeric; duplicate `as` refused; min/max on dates |
| `logic.deduplicate` | keep first (legacy); last; min/max by date; case-insensitive; `duplicates` bounded; `nullKeys: drop` |
| `flow.subworkflow` | direct/object input; terminal/named output; `timeoutMs`; `onError: continue` shape; `version: 0` resolution; cycle/depth still refused |
| `flow.for_each` | legacy `outputs` shape; `detailed` shape; `concurrency: 4` ordered and byte-identical to 1; `truncated`; `onEmpty: fail`; `continueOnError` + `failed` |
| `flow.repeat` | legacy final-state shape; `collect`; wired `count`; clamp; `continueOnError` |
| `flow.while` | legacy expression unchanged; shared conditions on a string state; `doWhile` runs once; `collect`; iteration/duration bounds still hold |

### 10.2 Test files to touch

| File | Purpose |
| --- | --- |
| `python/tests/test_graph_tables.py` | aggregate, deduplicate (extend) |
| `python/tests/test_graph_control_flow.py` | condition, switch, gate, stop (extend) |
| `python/tests/test_graph_executor.py` | merge, value paths, skip messages, cancellation |
| `python/tests/test_graph_loops.py` | for_each/repeat/while, concurrency determinism, resume |
| `python/tests/test_graph_subworkflows.py` | input/output modes, version 0, onError |
| `python/tests/test_graph_conditions.py` | **new** E4 module |
| `python/tests/test_graph_expr.py` | **new** E5 language (+ property tests) |
| `python/tests/test_graph_node_config_usage.py` | **new** "no declared field is ignored" invariant |
| `python/tests/test_graph_registry_parity.py` | runs after `npm run graph:manifest` |
| `src/lib/graph-studio/config-fields.test.ts` | new field presentation |
| `src/lib/graph-studio/registry.test.ts` | ports/enums/defaults |
| `src/lib/graph-studio/validation.test.ts` | new structural rules (gate all, version 0) |
| `python/examples/transform_demo.py` | one PASS/FAIL per new behaviour |

### 10.3 Invariants to assert globally

1. Every `ConfigField`/`configSchema` key is read by its executor (W0.9).
2. Every declared control output that can fire is declared before it fires
   (already enforced; keep the test).
3. Legacy default execution: for every node, a config built from
   `defaultConfig()` produces the same output before and after a change. Golden
   snapshots in `test_graph_legacy_defaults.py` (**new**) make this mechanical.
4. Determinism: same graph + same inputs → identical node outputs, with
   `for_each` concurrency both 1 and 4.
5. Bounds: every bounded field has a test that exceeds the bound and asserts a
   readable error.

---

## 11. Definition of done (per ticket)

A ticket is done only when **all** of these are true:

- [ ] TS registry updated (ports, zod schema, defaults, `docs` string).
- [ ] `npm run graph:manifest` run; `registry.manifest.json` committed.
- [ ] Python `NodeDef` mirrors the ports and `ConfigField` kinds/bounds exactly.
- [ ] Executor implemented, pure, bounded, with one W0.7-style summary line.
- [ ] `config-fields.ts` presentation updated (label, kind, inline/quick, help).
- [ ] `validation.ts` / `compiler.py` updated if a required-input or structural
      rule changed (both sides, same code string).
- [ ] Python tests + TS tests + a legacy-default test.
- [ ] `python/examples/transform_demo.py` extended where the node is covered.
- [ ] `docs/graph-studio.md` section updated; `docs/CHANGELOG.md` entry appended.
- [ ] `npm run test` and `npx tsc --noEmit` green from `Black-Eclipse-site/`.
- [ ] No new dependency.

---

## 12. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Contract drift across the four declaration sites | High without discipline | Broken parity, runtime rejects saved graphs | One node per PR; manifest + parity test as the gate; §11 checklist |
| E5 language grows into a programming language | Medium | Security/maintainability | Hard caps, no I/O/attr access, ADR, fuzz suite, `language: v1` default |
| E6 variadic ports ripple through canvas/validator/executor | High | Multi-day surprises | Prototype with `logic.merge` only, then adopt; manifest v2 gated |
| D3/D5 behaviour change breaks an operator's graph | Low | Trust | Release-note callout; `strictValues` escape hatch; golden legacy tests |
| `for_each` concurrency breaks determinism | Medium | Silent ordering bugs | Results indexed by input position; determinism test at 1 vs 4 |
| Subworkflow `version: 0` floats a production graph | Medium | Unreproducible runs | Floating-pin warning + Pin action; resolved version in the event log |
| Inline bodies (Option B) balloon | High if started | Half-built nested editor | Option A now; Option B only after an ADR with measured pain |
| Config UI (rows editor) becomes a second schema | Medium | Divergence | The rows spec lives beside the zod schema; the editor never invents fields |
| Flags accumulate | Medium | Unmaintainable | Exactly two flags, both with a scheduled removal at IR v3 |

---

## 13. Open decisions (need an answer before the ticket starts)

1. **D3/D5 shipping.** Ship the strict behaviour immediately, or keep
   `strictValues: false` for one release? *Recommendation: flag on, default off,
   release note.*
2. **`logic.switch` shape.** Fixed `case1..case8` outputs now, or wait for E6
   variadic outputs? *Recommendation: fixed eight now — it unblocks users today
   and becomes the fallback after E6.*
3. **`flow.subworkflow` `version: 0`.** Allow floating pins, or keep
   pinned-only? *Recommendation: allow, with a warning + Pin action.*
4. **E8 inline bodies.** Option A (no IR change) or Option B (sub-IR) as the
   end state? *Recommendation: A now, B only with an ADR.*
5. **`logic.map/filter/reduce` language.** Is a typed expression language
   acceptable, or would you rather have a bounded, sandboxed script node (much
   higher risk class)? *Recommendation: the expression language; a script node
   is a separate product decision.*
6. **Error routing (E7).** Is "a routed failure does not fail the run" the
   desired semantics? *Recommendation: yes — the route is the handler; the run
   fails only if nothing handles it.*

---

## 14. Appendix — config schema sketch (W1 shapes)

TypeScript (editor contract), for the three nodes with structured config:

```ts
// logic.condition
configSchema: z.object({
  operator: z.enum(['eq','neq','gt','gte','lt','lte','truthy']).default('truthy'),
  compareTo: z.string().max(400).default(''),
  combinator: z.enum(['all','any','none']).default('all'),
  conditions: z.array(z.object({
    path: z.string().max(200).default(''),
    operator: z.enum([
      'eq','neq','gt','gte','lt','lte','truthy','contains','startsWith',
      'endsWith','matches','in','between','isNull','isEmpty','isNotEmpty',
    ]).default('truthy'),
    value: z.string().max(400).default(''),
  })).max(8).default([]),
})

// logic.switch
caseList: z.array(z.object({
  value: z.string().max(200).default(''),
  label: z.string().max(80).default(''),
  kind: z.enum(['value','range','regex']).default('value'),
})).max(8).default([]),

// logic.aggregate
metrics: z.array(z.object({
  field: z.string().max(200).default(''),
  op: z.enum(['sum','avg','min','max','count','median','stddev','percentile',
             'countDistinct','first','last','sumsq','mode']).default('sum'),
  as: z.string().max(80).default(''),
  percentile: z.number().min(0).max(100).default(50),
})).max(8).default([]),
```

Python (runtime contract):

```python
ConfigField("combinator", "enum", "all", enum=("all", "any", "none")),
ConfigField("conditions", "array", []),
# coerce_config checks isinstance(list); the executor validates each row and
# names the offending index, e.g.
#   conditions[2].operator: unsupported operator 'like'
```

Note: the manifest maps all three to `kind: "array"`, so **no manifest change** is
required for W1. Add `maxItems` to the manifest only if E6 lands (W2.3).
