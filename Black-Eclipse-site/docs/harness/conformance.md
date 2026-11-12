---
title: Conformance Suite (C8)
status: Current
last-verified: 2026-11-11
---

# Conformance suite

**Who this is for:** anyone releasing the harness, or changing the loop, the
observability projection, the tool manifest or the plugin SDK. This is the C8
gate: fault matrix + golden trace + contract checks, offline and deterministic.

## Run it

```bash
npm run gate:conformance           # full suite
node scripts/conformance-gate.js --quick
node scripts/conformance-gate.js --only fault.retry_429
node scripts/conformance-gate.js --json docs/harness/conformance-report.json
```

`check-all.js` and CI run the gate. Exit codes: `0` pass, `1` a case failed or a
declared case is missing, `2` bad invocation/interpreter.

## What it asserts

| Case | Invariant |
|---|---|
| `fault.retry_429` | a 429 is retried within policy and can succeed |
| `fault.retry_500` | a 500 is retried within policy and can succeed |
| `fault.retry_disconnect` | a connection failure is retried |
| `fault.no_retry_400` | a non-retryable 400 is attempted once |
| `fault.no_retry_cancel` | cancellation is never retried |
| `fault.deadline_blocks_retry` | an expired run deadline refuses a retry |
| `fault.duplicate_effect` | a duplicate `begin` is idempotent; `finish` records done |
| `golden.run_step_tool` | the trace is `run → step → tool/LLM` with one terminal state |
| `contract.event_vocabulary` | hooks are closed and include `onStepStart/End` |
| `contract.tool_manifest` | manifest version, digest, and permission/effect honesty |
| `contract.slo_report` | release report carries runs/latency/cost/slos |
| `contract.plugin_sdk` | the plugin SDK declares a version |

The manifest (`docs/harness/conformance.json`) is authoritative: a case that
disappears or an undeclared case that appears fails the gate. Add a case by
adding it to `python/harness/evaluation/conformance/cases.py` **and** the
manifest; never leave a silent skip.

## Boundaries

- The fault matrix covers retry/deadline/cancel/duplicate-effect primitives, not
  a full kill-at-every-state process matrix yet (C8 follow-up).
- Golden traces compare structure/terminal state, not byte-identical timing.
- External benchmarks (SWE-bench Lite, GAIA, tau-bench, FinanceBench) are C8.2,
  not part of this offline gate.
