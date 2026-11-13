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
| `fault.crash_before_begin` | crash before begin: resume executes exactly once |
| `fault.crash_after_begin` | crash after begin: resume refuses (unknown, zero effects) |
| `fault.crash_after_effect` | crash after the effect: resume refuses (exactly one effect) |
| `fault.crash_after_finish` | crash after finish: resume does not re-execute |
| `golden.run_step_tool` | the trace is `run → step → tool/LLM` with one terminal state |
| `contract.event_vocabulary` | hooks are closed and include `onStepStart/End` |
| `contract.tool_manifest` | manifest version, digest, and permission/effect honesty |
| `contract.slo_report` | release report carries runs/latency/cost/slos |
| `contract.plugin_sdk` | the plugin SDK declares a version |
| `signal.model_attempt` | attempts, fallback numerator and TTFT reach the report |
| `signal.model_ttft` | first token becomes a TTFT observation |
| `signal.context_compression` | pressure, summary and skeleton outcomes are distinguishable |
| `signal.tool_batch` | batch size, concurrency and guardrail outcome are recorded |
| `signal.integrity_unknown_effect` | an unknown effect is counted and fails the invariant gate |
| `signal.integrity_lease_lost` | a lost lease reaches the integrity section |
| `signal.file_checkpoint` | created, failed and restored are distinguishable |
| `signal.goal_verdict` | verdicts roll up into completion/blocked rates |
| `signal.skill_evaluation` | evaluation outcomes reach the learning section |
| `contract.slo_report_v2` | schema v2, capabilities and unmeasured objectives |
| `contract.unmeasured_gate` | missing samples fail only when required |
| `contract.alert_metric_names` | every alert metric exists in the shipped exposition |

The manifest has 28 cases. `contract.alert_metric_names` parses
`deploy/prometheus/blackeclipse.rules.yml` and compares every `eclipse_*`
metric (bucket/sum/count suffixes normalised) with the exposition the shipped
probe records, so a renamed metric cannot silently disarm an alert.

The manifest (`docs/harness/conformance.json`) is authoritative: a case that
disappears or an undeclared case that appears fails the gate. Add a case by
adding it to `python/harness/evaluation/conformance/cases.py` **and** the
manifest; never leave a silent skip.

## Boundaries

- The fault matrix covers retry/deadline/cancel/duplicate-effect plus a
  process-level kill matrix at each durable window (before begin, after begin,
  after the effect, after finish).
- Golden traces compare structure/terminal state, not byte-identical timing.
- External benchmarks (SWE-bench Lite, GAIA, tau-bench, FinanceBench) run through
  `npm run gate:external` on committed two-task fixtures; the real benchmark data
  is opt-in and never committed.
