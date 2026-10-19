---
title: Runbook — Add a Collection Source
status: Current
last-verified: 2026-10-18
---

# Runbook — Add a Collection Source

**Who this is for:** an operator or developer adding one more bulk data source to
`acquire`. The rule: **one registry row + one adapter + the tests.** A source
without a registry row is not collectable, and a row without a licence is a test
failure — the registry IS the gate.

## Before you start

- The source must reach the data through an **existing read-only bridge
  capability** (`src/lib/harness/data-bridge.ts`). If the capability does not
  exist yet, that is a data-plane change (TS) plus this row — not a new
  transport in Python. Python never opens its own HTTP path for collection.
- Read `python/harness/acquire/registry.py` (the contract) and
  `python/harness/acquire/adapters.py` (how a payload becomes rows).

## 1. Declare the row — `python/harness/acquire/registry.py`

Add one `AcquisitionSource` to `SOURCES`:

```python
"my_source": AcquisitionSource(
    id="my_source",
    label="Plain words for the user",          # the manifest and the reply use this
    capability="the_bridge_capability",         # an EXISTING capability
    query_params=("the", "closed", "set"),      # a caller key outside this set is refused
    accepts_symbols=False,                      # True only when `symbols` drives paging
    per_call_param="the",                       # the param that pages one call
    rate_per_minute=30,
    max_rows_per_call=5_000,
    columns=("a", "b", "c"),                    # the EXACT CSV schema
    licence="public domain / vendor terms — be precise",
    attribution="The publisher named for the user",
),
```

`registry_issues()` (a test calls it) fails a row with a missing label,
capability, licence, attribution, an empty parameter set, or non-positive
ceilings. If a parameter has a closed value vocabulary, add it to
`CLOSED_VALUE_SETS` too — a value outside it is refused before any call.

## 2. Write the adapter — `python/harness/acquire/adapters.py`

Add one branch to `collect(...)` and one `_collect_<id>` function. The adapter
MUST:

- read only the payload's documented shape and emit rows with EXACTLY the
  declared `columns` (a missing field becomes `None`, never an invented value);
- call `budget.allow_call()` before each bridge call and `budget.record_call()`
  after;
- turn a failure or an empty payload into a plain `problem` sentence
  (`_problem(problems, "...")`) — never a fabricated row;
- stop at `budget.max_rows` and let the writer mark the file partial.

## 3. Prove it — the tests

- `python/tests/test_acquire.py` — extend the stub-bridge tests: a complete
  pull, a partial pull (one symbol UNAVAILABLE), a closed-parameter refusal, and
  the manifest's licence/attribution.
- The registry test (`test_registry_rows_are_complete_and_declared`) now covers
  the new row automatically.
- The opt-in live smoke
  (`test_live_macro_collection_through_the_real_bridge`, `HARNESS_ACQUIRE_IT=1`)
  is the only test that may touch the real network. Never put it in CI.

## 4. Bounds you do NOT get to widen

- `AcquisitionBudget` (per call) and `RunUsage` (per turn) are enforced in
  Python; a new source cannot raise them. Run ceilings come from
  `HARNESS_ACQUIRE_RUN_MAX_*` and are the operator's, not the model's.
- `MAX_SYMBOLS_PER_CALL` bounds one pull; the user can ask again for more.
- The write ceiling is enforced at each flush (`writer.write_csv`); a partial
  file is always marked partial with the reason.
- `acquisition_enabled` (Eclipse Memory → Policies, default OFF) gates the whole
  tool; `data.collect` is granted only by the acquisition profile.

## 5. Do not

- Do not spawn a fetcher, a browser or an HTTP client in Python for a collection
  — the bridge is the one egress.
- Do not accept a host, URL, header or secret as a caller parameter; a source
  that needs a credential refuses until the operator configures it.
- Do not edit the frozen constants in `code/policy.py`.

## Related

- `docs/harness/roadmap/phase-16-bulk-acquisition.md` — the phase and its gates,
  with the shipped status (ADR-H190) and the remaining slice.
- `python/harness/acquire/` — registry, budget, adapters, writer, tools.
