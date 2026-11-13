---
title: W0 — Baseline, Flags and Guardrails (Detailed Plan)
status: Active
last-verified: 2026-11-12
owner: Agent runtime + evaluation
parent: docs/harness/roadmap/hermes-inspired-improvement-plan.md
scope: planning only — no production code changed
---

# W0 — Baseline, Flags and Guardrails

## Implementation status (2026-11-12)

**Landed (first slice):**

- `python/harness/config/flags.py` — typed registry for W1–W7 flags, stdlib only,
  bool/int/enum parsing, strict mode, stable snapshot/hash.
- `python/harness/run_flags.py` — per-run snapshot, `run.flags` event, and
  `HarnessRun.context.flags` / `flagsHash`.
- `graph.execute_run` — records the snapshot once per run/resume and merges it
  into the completion/overflow context. Event ordering is additive
  (`run.created`, `run.started`, `run.flags`).
- `boot._boot` — calls `flags.assert_valid()`; strict mode is opt-in via
  `HARNESS_FLAG_STRICT=on`.
- `python/harness/evaluation/w0_baseline.py` + `scripts/w0-baseline.js` —
  read-only metrics collector (runs, events, model attempts, tools, effects)
  with honest `UNKNOWN`; writes JSON + Markdown.
- Tests: `test_flags.py`, `test_run_flags.py`, `test_w0_baseline.py`,
  `test_kill_switches.py`; the exact event-order test in `test_graph.py` was
  updated.

**Still to do for W0 exit:**

- none for the first slice; the committed baseline is
  `docs/harness/baselines/w0-0a7ec906-2026-11-12.{json,md}` (74/74 terminal,
  offline/SLO/audit/conformance/tsc PASS, live `NOT MEASURED`).

`docs/harness/roadmap/w0-flags-and-review.md` now holds the flag matrix and
reviewer checklist.

The first slice changes no prompt, tool, schema or model behaviour.

W0 is the measurement and control layer for the Hermes-inspired programme. It
does not improve the agent. It makes every later improvement **falsifiable**.

Without W0, "faster", "cheaper", "more reliable" are opinions. With W0, each
workstream has a baseline number, a comparison protocol, a feature flag, a kill
switch, and a review gate that prevents a second loop/scheduler/approval path.

**Duration:** 5 working days + 2 buffer days.
**Output:** a reproducible baseline artifact, a typed flag registry, a
kill-switch suite, and a review checklist.

---

## 1. Objectives

1. Capture the current harness behaviour on a frozen commit, with provenance
   (commit, dataset checksums, model, platform, flags).
2. Measure the dimensions each later workstream will claim to improve:
   latency, tokens, cost, retries, fallbacks, tool errors, context overflow,
   orphan rate, resume success, effect-unknown count, eval scores.
3. Establish the comparison protocol so W1–W8 compare like with like.
4. Introduce one typed flag registry and one kill-switch test pattern.
5. Make "no second seam" enforceable in review.

## 2. Non-goals

- No model gateway, context anchor, parallel tools, goal loop, curator or
  checkpoint implementation. Those are W1–W7.
- No change to run semantics, schema, prompts or tool surface.
- No new dependency.
- No benchmark tuning. If the baseline is bad, record it honestly.

---

## 3. Deliverables

| ID | Deliverable | Path | Owner |
|---|---|---|---|
| D1 | Baseline collector | `scripts/w0-baseline.js` (new) | runtime |
| D2 | Machine baseline | `docs/harness/baselines/w0-<commit>-<date>.json` | runtime |
| D3 | Human baseline | `docs/harness/baselines/w0-<commit>-<date>.md` | runtime |
| D4 | Typed flag registry | `python/harness/config/flags.py` (new) | runtime |
| D5 | Flag tests | `python/tests/test_flags.py`, `test_kill_switches.py` | runtime |
| D6 | Flag matrix + review checklist | `docs/harness/roadmap/w0-flags-and-review.md` | runtime |
| D7 | Run flag snapshot | `run.flags` event + `HarnessRun.context.flags` | runtime |

`D4` and `D7` are the only production-code changes in W0. Everything else is
scripts/docs/tests. That keeps W0 low-risk.

---

## 4. Metric dictionary

Every metric names its source table or gate. The collector must not invent a
value; an absent metric is `null` with `measured: false` and a reason.

### 4.1 Run lifecycle

| Metric | Source | Definition |
|---|---|---|
| `runs.total` | `HarnessRun` | Count in the baseline window |
| `runs.byStatus` | `HarnessRun.status` | `completed/failed/cancelled/interrupted/created/running` |
| `runs.terminalCorrectness` | `HarnessRun` | `completed / (completed+failed+cancelled)`; `interrupted` excluded and reported separately |
| `runs.orphanRate` | `run_recovery` events / status | Non-terminal rows with no live lease at boot ÷ total |
| `runs.resumeAttempts` | `HarnessEvent` type `run.resumed` | Count |
| `runs.resumeSuccess` | `HarnessRun` after resume | `completed / resumed` |
| `runs.interrupted` | `HarnessRun.status='interrupted'` | Count |
| `runs.stalled` | `HarnessEvent` type `run.failed` data.code `RUN_STALLED` | Count |
| `runs.partialDelivered` | `HarnessEvent` type `run.partial` | Count |

### 4.2 Latency

| Metric | Source | Definition |
|---|---|---|
| `latency.run.p50/p95/p99` | `HarnessRun.startedAt/finishedAt` | Wall clock, terminal runs only |
| `latency.model.p50/p95` | `ModelRequest.latencyMs` | Per physical attempt |
| `latency.ttft.p50/p95` | `ModelRequest.ttftMs` | Time to first token when present |
| `latency.tool.p50/p95` | `HarnessToolExecution.durationMs` | Per tool call |
| `latency.resume.p95` | `run.resumed` → terminal | Resume wall clock |

Implementation: SQLite has no percentile; sort in Python and use the nearest-rank
method, the same convention as `quant/metrics.py` (`ceil(p*n)-1`).

### 4.3 Model and cost

| Metric | Source | Definition |
|---|---|---|
| `model.attempts` | `ModelRequest` | Physical attempts |
| `model.attemptsPerRun` | `ModelRequest` grouped by `runId` | Mean/p95 |
| `model.retries` | `ModelRequest.retries` + `model.retry` events | Count |
| `model.fallbacks` | `ModelRequest.fallback=1` + `model.fallback` events | Count and rate |
| `model.errorClasses` | `ModelRequest.errorClass` | Histogram |
| `model.tokens.input/output/total` | `ModelRequest` | Sum/mean/p95 |
| `model.cost.total` | `ModelRequest.costTotal` | Null when unpriced |
| `model.cost.pricedCoverage` | `ModelRequest.costTotal IS NOT NULL` | Ratio; never substitute 0 |
| `model.providers` | `ModelRequest.provider` | Histogram |

### 4.4 Context

| Metric | Source | Definition |
|---|---|---|
| `context.promptTokens.mean/p95` | `HarnessRun.promptTokens` | Per run |
| `context.overflowRate` | `HarnessEvent` `context.overflow` ÷ runs | Ratio |
| `context.retryRate` | `HarnessEvent` `context.retry` ÷ runs | Ratio |
| `context.compactions` | `HarnessEvent` compaction types | Count and rate |
| `context.avgHistoryChars` | `HarnessRun.context` / events | Mean |
| `context.budgetEffective` | `ContextBudget.effective` | Ratio of runs with a known window |

### 4.5 Tools

| Metric | Source | Definition |
|---|---|---|
| `tools.calls` | `HarnessToolExecution` | Count |
| `tools.callsPerRun` | grouped by `runId` | Mean/p95 |
| `tools.errorRate` | `ok=0` ÷ calls | Ratio |
| `tools.timeoutRate` | `HarnessEvent` `tool.failed` code `TOOL_TIMEOUT` ÷ calls | Ratio |
| `tools.duplicateRate` | `HarnessEvent` duplicate suppression / `skill.tool_duplicate` if present | Ratio |
| `tools.avgResultChars` | `HarnessToolExecution.text` length | Mean/p95 |
| `tools.spillRate` | `HarnessEvent` full-output handle events ÷ calls | Ratio |
| `tools.topTools` | `HarnessToolExecution.name` | Histogram |

### 4.6 Safety and effects

| Metric | Source | Definition |
|---|---|---|
| `security.approvals` | `HarnessEvent` approval types | Count |
| `security.denials` | `HarnessEvent` approval denied | Count |
| `security.effectUnknown` | `RunEffect.state='unknown'` | Count; target 0 |
| `security.effectStarted` | `RunEffect.state='started'` at baseline | Count |
| `security.tokenMode` | `HARNESS_EFFECT_TOKENS` | `shadow/enforce/off` |
| `security.shadowViolations` | effect-token shadow records | Count |

### 4.7 Evaluation

| Metric | Source | Definition |
|---|---|---|
| `eval.offline.gate` | `run_offline_gate` | PASS/FAIL + failing dimensions |
| `eval.offline.categories` | Suite result | Per-category passed/measured/unmeasured |
| `eval.offline.dimensions` | Suite result | All 22 dimensions, with `UNKNOWN` preserved |
| `eval.live.gate` | `run_live_gate` | PASS/FAIL/NOT MEASURED + reason |
| `eval.live.model` | live suite | Provider/model/temperature |
| `eval.variance` | repeated trials | pass@1, pass@k, Wilson interval where available |
| `eval.selfEvolution` | `collect_self_evolution_metrics` | Measured/unmeasured exactly as the runner reports |

### 4.8 Ops / gates

| Metric | Source |
|---|---|
| `gate.slo` | `npm run gate:slo` + `docs/harness/slo-report.json` |
| `gate.audit` | `npm run audit:agent` (44 checks) |
| `gate.conformance` | `npm run gate:conformance` |
| `gate.tsc` | `npx tsc --noEmit` |
| `gate.offlineEvals` | `node scripts/test-evals.js` |
| `gate.fullTest` | `npm run test` (nightly; record duration/result) |

---

## 5. Measurement protocol

### 5.1 Freeze the code

Record:

```json
{
  "commit": "<git rev-parse HEAD>",
  "dirty": true/false,
  "python": "<python --version>",
  "node": "<node --version>",
  "platform": "win32/x64",
  "datasetChecksums": {"eclipse-benchmark": "..."},
  "flags": {"HARNESS_EFFECT_TOKENS": "shadow", "...": "..."}
}
```

A dirty tree is allowed for a local baseline but must be flagged; the official
baseline is from a clean commit.

### 5.2 Isolate the database

**Never** point the collector at the developer's `agent-memory.db`.

- Create `mkdtemp("be-w0-")`.
- Set `AGENT_MEMORY_DB_PATH` and `ECLIPSE_MEMORY_DB_PATH` to temp files.
- Set `BLACK_ECLIPSE_CODE_INTEL_WARM=0`.
- Run the evaluation gate (which already uses a private temp DB).
- For runtime metrics, either run a controlled soak against the temp DB or
  snapshot a **copy** of a real DB and read it read-only. Never write the real
  DB.

### 5.3 Offline tier (every W0 run)

```bash
node scripts/test-evals.js
```

Record:

- the full gate line (`ALL PASS` / failures);
- per-category counts;
- all dimensions, including `UNKNOWN`.

The offline tier is deterministic enough to compare across commits. Run it
**three times** for the variance check if time allows; otherwise run once and
mark `trials=1`.

### 5.4 Live tier (only if configured)

```bash
node scripts/run-live-evals.js --suite benchmark --limit 30 --model <provider>/<model>
```

Rules:

- 30 measured trials is the minimum for a gate (`MIN_LIVE_TRIALS=30`).
- If no provider is configured, record `NOT MEASURED` and the reason. Do not
  fabricate.
- Pin one model/provider for the entire programme; a model switch invalidates
  comparisons.
- Record temperature/top-p/seed if the provider supports them.

### 5.5 Runtime soak (small, controlled)

Use the existing G1-style pattern:

- 50 sequential runs + 24 concurrent runs on the temp DB;
- a scripted model (no provider cost) for the offline soak;
- assert every run reaches a terminal state;
- count orphaned/interrupted rows after boot reconciliation.

This is not a load test; it is a **lifecycle** test. A larger soak belongs to
W8.

### 5.6 Gates

```bash
npm run gate:slo
npm run audit:agent
npm run gate:conformance
npx tsc --noEmit
```

`npm run test` is the full suite; run it once in W0 as a nightly job and record
its duration and result. Do not block the 5-day plan on it if it exceeds the
timeout; mark `fullTest: "not_completed"` with the reason.

---

## 6. Baseline artifact schema

`docs/harness/baselines/w0-<shortsha>-<YYYY-MM-DD>.json`:

```json
{
  "version": 1,
  "label": "w0-baseline",
  "generatedAt": "2026-11-12T18:00:00Z",
  "provenance": {
    "commit": "9eeb9266",
    "dirty": false,
    "python": "3.12.x",
    "node": "22.x",
    "platform": "win32-x64",
    "datasetChecksums": {
      "eclipse-benchmark": "ea086f46b491f84fdd3b7a87220d5533"
    },
    "flags": {
      "HARNESS_EFFECT_TOKENS": "shadow",
      "HARNESS_MODEL_FALLBACK": "off",
      "HARNESS_LAZY_TOOLS": "off"
    }
  },
  "window": {
    "from": "...",
    "to": "...",
    "runCount": 0,
    "source": "temp-db|snapshot-copy"
  },
  "metrics": {
    "runs": {},
    "latency": {},
    "model": {},
    "context": {},
    "tools": {},
    "security": {},
    "eval": {},
    "gates": {}
  },
  "categories": {},
  "unmeasured": [
    {"metric": "eval.live.gate", "reason": "no provider configured"}
  ],
  "notes": []
}
```

Rules:

- Every metric is `{value, unit, sample, measured, source}`; no bare numbers.
- `null` + `measured:false` is required when unknown; never `0`.
- The Markdown file is generated from the JSON, not hand-written.
- The artifact is committed; it is small (no prompts, no tool outputs, no
  secrets).

---

## 7. Flag registry design

### 7.1 Why a registry

There are already **242** `os.environ.get("HARNESS_...")` call sites in
`python/harness`. Adding more ad-hoc flags would make rollout and rollback
unreviewable. W0 gives new work one typed entry point; it does not rewrite the
existing 242.

### 7.2 `python/harness/config/flags.py`

```python
from dataclasses import dataclass
from typing import Literal

Kind = Literal["bool", "int", "enum", "str"]

@dataclass(frozen=True)
class FlagSpec:
    name: str                 # HARNESS_MODEL_GATEWAY
    kind: Kind
    default: str
    values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    owner: str = ""
    description: str = ""
    since: str = ""           # version/date
    remove_by: str | None = None

FLAGS: dict[str, FlagSpec] = {
    "HARNESS_MODEL_GATEWAY": FlagSpec(
        name="HARNESS_MODEL_GATEWAY", kind="enum",
        default="shadow", values=("shadow", "on", "off"),
        owner="W1", description="Route the graph through ModelGateway",
        since="w0", remove_by="after W1 is green for 2 weeks",
    ),
    # ... one entry per flag in the matrix
}

def get_flag(name: str, *, environ=None) -> str: ...
def get_bool(name: str, *, environ=None) -> bool: ...
def get_int(name: str, *, environ=None) -> int: ...
def snapshot(*, environ=None, redact=True) -> dict[str, str]: ...
def validate(*, environ=None) -> list[str]: ...
```

Rules:

- Parsing: bool accepts `1,true,yes,on,enable,enabled` (case-insensitive);
  false accepts `0,false,no,off,disable,disabled`.
- Int is clamped to `[minimum, maximum]`; an invalid value returns the default
  and records a warning (not a crash).
- Enum is validated against `values`; invalid → default + warning.
- Unknown `HARNESS_*` names are not errors; `validate()` only checks known
  specs.
- `snapshot()` returns only known flags, sorted, no secrets (none of these are
  secrets).
- No imports from `graph`, `service` or any runtime module. Stdlib only. This
  keeps it importable from tests, scripts and boot.

### 7.3 Run flag snapshot

At run start (`execute_run`), emit:

```json
{
  "type": "run.flags",
  "data": {
    "flags": {"HARNESS_MODEL_GATEWAY": "shadow", "...": "..."},
    "snapshotHash": "sha256:..."
  }
}
```

and store the same map in `HarnessRun.context.flags` (bounded, redacted). This
makes a run reproducible after a flag default changes.

### 7.4 Strict mode

`HARNESS_FLAG_STRICT=1` makes `validate()` fail boot on an invalid known flag
value. Default off in development, on in production after W0. This catches a
typo like `HARNESS_MODEL_GATEWAY=shdaow` instead of silently using the default.

---

## 8. Kill-switch test design

Every new flag has a test that proves the old path still works.

`python/tests/test_kill_switches.py`:

```python
CASES = [
    ("HARNESS_MODEL_GATEWAY", "off", "legacy step path"),
    ("HARNESS_USAGE_ANCHOR", "off", "heuristic budget"),
    ("HARNESS_PARALLEL_TOOLS", "off", "sequential tools"),
    ("HARNESS_TOOL_GUARDRAILS", "off", "no guardrail halt"),
    ("HARNESS_TOOL_DISCLOSURE", "off", "eager tools"),
    ("HARNESS_AUTONOMY", "off", "no goal loop"),
    ("HARNESS_SKILL_EXEC_EVAL", "off", "static-only gate"),
    ("HARNESS_FENCED_PROGRESS", "off", "legacy update_run"),
]
```

Each case:

1. set the flag off;
2. run a minimal smoke (real `execute_run` with a scripted model);
3. assert the legacy path is used (event/attribute);
4. set the flag on and assert the new path is used;
5. restore the environment.

This is the only way to guarantee a rollout is reversible.

---

## 9. "No second seam" review gate

A PR is rejected if it adds any of:

- a second agent loop;
- a second scheduler/tick loop;
- a second approval store/path;
- a second model client or provider adapter;
- a second tool registry/dispatcher;
- a second event bus;
- a second memory store;
- a new database file.

The PR description must answer:

1. Which existing seam does this extend? (file/function)
2. What flag controls it?
3. What is the kill switch?
4. What event/metric proves it works?
5. What test fails if the old path is used?
6. Does it change a contract? If yes, which ADR?
7. Does it add a dependency? Why is it lighter than the alternative?

`docs/harness/roadmap/w0-flags-and-review.md` contains the checklist and the
flag matrix. Reviewers copy it into the PR.

---

## 10. Day-by-day plan

### Day 1 — Freeze and inventory

- Confirm the commit and clean/dirty state.
- Record Python/Node/platform.
- Inventory existing flags and the **new** flags W0–W7 will need.
- Run `node scripts/test-evals.js`; save the full output.
- Run `npx tsc --noEmit`.
- Identify the exact tables/fields for each metric (the dictionary above).
- Write `docs/harness/baselines/w0-notes.md` with gaps (e.g. "ttftMs is often
  null", "orphan rate needs a boot run").

### Day 2 — Collector + offline baseline

- Implement `scripts/w0-baseline.js`:
  - resolve Python via `scripts/python-runner.js`;
  - create temp DB env;
  - run the offline gate through the existing Python entry point;
  - read the temp DB (read-only) for run/tool/model/effect metrics;
  - write JSON + Markdown.
- Run it. Inspect for `null`/`measured:false` mistakes.
- Add a `--dry-run` that prints the SQL and paths without executing.
- Add a `--db <path>` read-only mode for a snapshot copy.

### Day 3 — Live tier + gates + soak

- If a provider is configured:
  `node scripts/run-live-evals.js --suite benchmark --limit 30 --model ...`.
  Otherwise record `NOT MEASURED` + reason.
- Run `npm run gate:slo`, `npm run audit:agent`, `npm run gate:conformance`.
- Run the 50+24 lifecycle soak on the temp DB.
- Start `npm run test` as a nightly; do not block the day.
- Add all results to the JSON.

### Day 4 — Flag registry + snapshot

- Implement `python/harness/config/flags.py` (stdlib only).
- Add `python/tests/test_flags.py`:
  - bool/int/enum parsing;
  - invalid → default + warning;
  - clamp;
  - snapshot sorted/stable;
  - `validate()` unknown/invalid;
  - no secret keys.
- Add `run.flags` emission at run start and `HarnessRun.context.flags`.
- Add `python/tests/test_run_flags.py` (snapshot hash stable, bounded size).

### Day 5 — Kill switches + review + exit

- Add `python/tests/test_kill_switches.py` (one case per W1–W5 flag).
- Run the full W0 suite:
  - `node scripts/test-evals.js`
  - `npx tsc --noEmit`
  - targeted pytest: `test_flags.py test_kill_switches.py test_run_lease.py
    test_run_effects.py test_run_watchdog.py test_context_budget.py
    test_history_compaction.py test_tool_surface.py`
- Write the Markdown baseline from the JSON.
- Hold the W0 exit review:
  - Is every metric measured or explicitly unmeasured?
  - Does every new flag have a kill switch?
  - Is the baseline reproducible from the recorded command?
  - Are the W1/W2/W3 target metrics named?

Buffer days 6–7: fix collector bugs, rerun, review.

---

## 11. Exit criteria

W0 is complete when:

1. **Baseline artifact committed** with commit sha, dataset checksums, model and
   flag snapshot.
2. **Every metric** in §4 is either measured or `null` with a reason. No
   fabricated zeros.
3. **Offline gate ALL PASS**, or the failing dimension is recorded as a known
   baseline defect.
4. **Live gate** is PASS or `NOT MEASURED` with a reason (never a fake pass).
5. **SLO, audit, conformance, tsc** results recorded.
6. **`flags.py`** merged with tests; `run.flags` emitted.
7. **Kill-switch suite** passes for every W1–W5 flag.
8. **Flag matrix + review checklist** committed.
9. **No behaviour change**: the only production diff is `config/flags.py`,
   the `run.flags` emission, and tests. No prompt, schema or tool change.
10. **Handoff note** names the baseline values W1–W8 will be compared against.

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Live lane has no provider | Record `NOT MEASURED`; offline tier is still a baseline. Do not fake. |
| p95 is noisy on a laptop | Run 3 samples where possible; report sample size and median p95; compare only on the same machine. |
| Real DB contamination | Temp DB only; `--db` is read-only; no writes to `agent-memory.db`. |
| Dataset drift | Record dataset checksum; refuse to compare across checksums. |
| Collector reads a schema that moved | The collector queries only documented tables; a missing table is `measured:false` with the reason, not a crash. |
| Full suite too slow | Nightly full run; W0 gate uses targeted suites + evals. |
| New flags multiply | One registry; a flag older than its `remove_by` is a review failure. |
| Baseline becomes a vanity metric | Every metric has a source and a sample; `UNKNOWN` is allowed. |

---

## 13. Handoff to W1–W8

The baseline artifact is the comparison source for every later slice:

| Workstream | Primary baseline metrics | Target |
|---|---|---|
| W1 model gateway | `model.fallbacks`, `model.attemptsPerRun`, `latency.model.p95`, `model.cost.pricedCoverage` | Fallback works; no cost regression; p95 within 10% |
| W2 context | `context.overflowRate`, `context.promptTokens.p95`, `context.compactions` | Overflow < 1%; tokens down; no evidence loss |
| W3 tools | `tools.callsPerRun`, `latency.tool.p95`, `tools.errorRate` | Read-only batch ≥3× faster; error rate flat |
| W4 autonomy | `runs.terminalCorrectness`, `runs.resumeSuccess`, goal completion | No regression; goal completion measured |
| W5 learning | `eval.offline` memory/skill dimensions, `skill.execution` | No regression; execution gate coverage |
| W6 kernel | `runs.orphanRate`, `security.effectUnknown`, `runs.resumeSuccess` | Orphan 0; effect unknown 0 |
| W7 delegation | `runs.terminalCorrectness`, `tools.callsPerRun`, child jobs | No regression; async completion measured |
| W8 ops | all of the above | SLOs green for 2 weeks |

A slice may not claim an improvement without a before/after pair from the same
dataset checksum, model and machine class. If the metric is `UNKNOWN` in the
baseline, the slice must first make it measurable.

---

## 14. Command appendix

```bash
# Offline eval gates (deterministic, temp DB)
node scripts/test-evals.js

# Live tier (only if a provider is configured; 30+ trials is a gate)
node scripts/run-live-evals.js --suite benchmark --limit 30 --model <provider>/<model>

# Release gates
npm run gate:slo
npm run audit:agent
npm run gate:conformance
npx tsc --noEmit

# Full suite (nightly; long)
npm run test

# Targeted W0 Python suite
node scripts/test-python.js python/tests/test_flags.py python/tests/test_kill_switches.py \
  python/tests/test_run_lease.py python/tests/test_run_effects.py \
  python/tests/test_run_watchdog.py python/tests/test_context_budget.py \
  python/tests/test_history_compaction.py python/tests/test_tool_surface.py

# Baseline collector (once implemented)
node scripts/w0-baseline.js --out docs/harness/baselines/w0-<sha>-<date>.json
```

---

## 15. What W0 is not

- It is not a performance optimisation.
- It is not a rewrite of the 242 existing env flags.
- It is not a promise that the baseline is good. It is a promise that the
  baseline is **honest and reproducible**.
- It is not a reason to delay W1. W0 and W1 can overlap after Day 3; W1 only
  needs the flag registry and the baseline numbers for its four metrics.
