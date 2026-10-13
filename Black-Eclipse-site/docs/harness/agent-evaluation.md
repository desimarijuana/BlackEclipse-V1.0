---
title: Agent Evaluation System
status: Current
last-verified: 2026-10-13
---

# Agent Evaluation System

**Who this is for:** anyone asking *"is the agent getting better or worse?"* and
wanting an answer backed by measurements of the **real** Eclipse runtime, not by
prose.

The evaluation system lives in `python/harness/evaluation/`. It runs versioned,
environment-isolated tasks through the real agent graph (the same
`harness.graph.execute_run` tool loop the product uses), captures the complete
trajectory, grades it with a pluggable grader engine, aggregates trials with
statistics, persists everything, compares against baselines and detects
regressions. It never fabricates a number: a metric that cannot be measured is
`UNKNOWN`, and a gate never collapses to one blended score.

## 1. Architecture

```
python/harness/evaluation/
  config.py         EvaluationConfig + paths under .black-eclipse/evaluation/
  tasks.py          the versioned EvaluationTask schema + dataset loader
  environments.py   deterministic environments (filesystem/db/finance/memory/mock)
  trajectory.py     capture + the normalized, versioned trajectory format
  stats.py          pass@1 / pass@k / variance / Wilson CI / flakiness
  taxonomy.py       the failure taxonomy (one failure, many labels)
  graders/          the pluggable grader engine (17 built-in graders)
  scoring.py        per-dimension metrics + thresholds + guarded composite
  runner.py         the runner + the two invokers (scripted / live)
  store.py          all durable rows on the ONE agent-memory.db connection
  baseline.py       baseline snapshots + guarded promotion
  regression.py     per-dimension regression gates
  report.py         JSON / JSONL / Markdown / HTML
  replay.py         inspect / compare / re-run a recorded trajectory
  mining.py         production-failure → regression-candidate pipeline
  improvement.py    the self-improvement verification loop
  experiments.py    A/B, model matrix, routing, skill and memory comparison
  dependencies.py   the affected-component map
  gate.py           the offline gate (used by scripts/test-evals.js)
  cli.py            `eclipse eval …`
  tools.py          sandbox tools the scripted tier exposes to the agent
  datasets/         the labelled benchmark (benchmark_v1 + construction_v1)
```

Two invokers drive the SAME runtime:

- **`ScriptedAgentInvoker`** (offline tier) — the real `execute_run` tool loop,
  real `ToolRegistry`, real authorization, real events, with a deterministic
  scripted chat model. This is exactly how the repo's own tests exercise the
  graph; the model is the only substituted part.
- **`ServiceAgentInvoker`** (live tier) — the production `AgenticService.run` with
  a real model.

Isolation between concurrent trials is by `contextvars` (the model override and
the bound environment), so independent trials run in parallel in one process.

## 2. Task format

A task is DATA. Schema version `TASK_SCHEMA_VERSION` (in `config.py`); each task
carries its own `version`, and changing a task bumps it — a score is scoped to
`(task_id, task_version)`.

```json
{
  "id": "finance.pe.001",
  "version": 1,
  "category": "finance",
  "difficulty": "easy",
  "input": { "prompt": "Price is 100 and EPS is 5. What is the P/E ratio?" },
  "environment": { "type": "filesystem" },
  "initial_state": { "files": {} },
  "expected_output": { "numeric": { "value": 20, "tolerance": 0.01 } },
  "expected_state": { "files": { "answer.py": { "contains": "2+2" } } },
  "expected_tools": ["eval_fs_write"],
  "required_tools": ["eval_fs_write"],
  "forbidden_tools": ["eval_external_publish"],
  "graders": [{ "name": "financial", "config": { "metric": "pe", "inputs": { "price": 100, "eps": 5 } } }],
  "constraints": {},
  "limits": { "max_turns": 40, "max_tool_calls": 200, "timeout_seconds": 300 },
  "metadata": { "tier": 0, "suites": ["finance"], "agent_script": [ { "type": "final", "content": "20.0" } ] }
}
```

Categories: `core`, `tools`, `research`, `citations`, `finance`, `coding`,
`browser`, `memory`, `planning`, `long_horizon`, `recovery`, `parallel`,
`safety`, `adversarial`, `regression`. Difficulties: `easy`, `medium`, `hard`,
`adversarial`.

`metadata.agent_script` is the deterministic model program for the offline tier:
`{"type": "tool", "calls": [...]}` or `{"type": "final", "content": "..."}`. A
task with no script (or `metadata.live_only: true`, or a `research`/`citations`
task with no script) is `unmeasured` offline — never a fabricated pass.

## 3. Environment format

`environment.type` selects a factory from `environments.py`:
`filesystem`, `database`, `finance`, `memory`, `mock_services`, `composite`,
`none`. Every environment implements `setup / reset / snapshot / restore / seed /
execute / inspect_state / teardown`; a trial always starts from a known state and
state-changing tasks are graded on the **real resulting state**, not the prose.

Environments are isolated (a private temp dir / temp SQLite file / in-process
map) and never reach the network or a production credential. A live evaluation
must explicitly opt in to external effects; the default is OFF.

## 4. Trajectory format

`TRAJECTORY_FORMAT_VERSION` (in `config.py`). Captured from the runtime's own
event bus — the evaluation system never re-implements the agent loop.

```json
{
  "trajectoryVersion": "1",
  "runId": "…", "taskId": "…", "taskVersion": 1, "trialId": "…",
  "agentVersion": null, "gitCommit": "…",
  "agent": {}, "model": {},
  "events": [ { "index": 0, "type": "tool.requested", "at": "…", "data": { "name": "…", "args": { … } } } ],
  "finalAnswer": { "output": "…", "status": "completed" },
  "outcome": { "status": "completed", "error": null },
  "metrics": { "toolCalls": 2, "totalTokens": 0, "cost": 0.0, "latencyMs": null }
}
```

The runtime's `tool.requested` event deliberately omits arguments (privacy), so
the scripted invoker records arguments at the `ToolRegistry` boundary and folds
them back into the trajectory — that is how tool **arguments** are graded
honestly. Replay: `replay.inspect`, `replay.compare_trajectories`,
`replay.replay` (re-runs the same task through a chosen invoker).

## 5. Grader API

Every grader implements one interface and returns a structured result:

```python
class Grader:
    def __init__(self, config: dict | None = None) -> None: ...
    def grade(self, ctx: GradeContext) -> GraderResult: ...

@dataclass
class GraderResult:
    grader: str; score: float; passed: bool
    details: dict; failures: list[str]; evidence: list; unmeasured: bool
```

Built-ins: `exact`, `state`, `tool`, `research`, `citation`, `financial`, `code`,
`browser`, `memory`, `safety`, `semantic`, `hallucination`, `recovery`, `honesty`,
`provenance`, `artifact`, `response`. A grader that cannot measure returns
`unmeasured=True` and renders `UNKNOWN` — never `0`, never an inferred pass.
Graders are chosen per task from `task.graders` (each
`{"name": …, "config": …}`); a task that names none gets `default_graders_for`.

**Financial grading is deterministic.** `FinancialGrader` independently computes
the expected value (via `harness.research.calculations` and closed-form ratios)
and compares it to the agent's number within a declared tolerance — an LLM is
never the authority on a calculation.

### 5.1 Construction graders (R3-08)

The five construction graders read the trajectory, the REAL environment state and
the final answer — never prose alone:

| grader | dimension | what it measures |
|---|---|---|
| `recovery` | `recovery_success` | after a failure, a DIFFERENT route (or the same route after an intervening repair) eventually succeeds; a blind repeat of a failed route is a **redundant retry**. Modes: `recover_required`, `stop_expected` (budget kills / honest delivery failures), `any`. No failure ⇒ UNKNOWN. |
| `honesty` | `honesty` | false-success claims (a success marker not earned by the declared state / completed evidence tools), unsupported claims (a declared value with no completed evidence tool), an un-named gap/failure. |
| `provenance` | `provenance` | required labels (`retrieved`/`computed`/`collected`) appear; required sources are BOTH used (a completed call) and cited; `collected` data is never called `verified`. |
| `artifact` | `artifact_delivery` | the artifact exists in the real (possibly composite) environment state; delivery genuinely completed OR failed-and-reported, never faked. |
| `response` | `visual_delivery` | the answer text survives; every `eclipse-response` fence decodes with a valid block list and a usable chart block when required. The TS contract (`src/lib/response/contract.ts`) stays the authority. |

The scenario signals are declared per task in `metadata.measures`; latency, cost
and tokens are captured for **every** trial by the trajectory.

## 6. Custom graders

```python
from harness.evaluation.graders import Grader, GraderResult, GradeContext, register_grader

class MyGrader(Grader):
    name = "my_grader"
    def grade(self, ctx: GradeContext) -> GraderResult:
        ok = "expected" in (ctx.final_output or "")
        return GraderResult(self.name, 1.0 if ok else 0.0, ok, failures=[] if ok else ["missing"])

register_grader("my_grader", MyGrader)
```

Then name it in a task: `"graders": [{"name": "my_grader"}]`. An unknown grader
name is a hard error — never silently skipped.

## 7. Running evaluations

```bash
# The offline deterministic gate (all built-in tasks, temp DB)
python -m harness.evaluation

# The CLI
eclipse eval run --suite finance --trials 5
eclipse eval smoke
eclipse eval regression --baseline main
eclipse eval benchmark --report --format md,json
eclipse eval run --task finance.pe.001
eclipse eval run --model ollama/llama3.1          # live tier
eclipse eval run --affected --paths python/harness/browser/x.py
eclipse eval replay --trajectory .black-eclipse/evaluation/trajectories/<id>.json
eclipse eval report
eclipse eval mine --run <production-run-id>
eclipse eval improve
```

Tiers: **0** deterministic (offline), **1** integration, **2** live. Select with
`--tier`. The runner executes independent trials concurrently
(`--concurrency`, default `HARNESS_EVAL_CONCURRENCY=4`) with a bounded semaphore.

## 8. Adding tasks

1. Add a task object to `python/harness/evaluation/datasets/benchmark_v1.json`
   (or a new `datasets/<name>.json` — `construction_v1.json` is the R3-08
   construction benchmark; `load_all_builtin` merges every dataset and rejects
   duplicate ids).
2. Bump the dataset `datasetVersion` and, if you changed an existing task, its
   `version`. Never edit a task in place without bumping `version`.
3. A construction task should declare `metadata.suites: ["construction"]`,
   `metadata.scenario` and `metadata.measures` (the signals it exercises).
4. Run `python -m harness.evaluation` — the gate must stay green.

## 9. Creating regression tests

A production failure becomes a permanent regression test through
`mining.py`:

```
Production Failure → Normalize → Classify → Deduplicate → Candidate
```

```bash
eclipse eval mine --run <run-id>        # creates a candidate (dedup by signature)
```

A candidate is not a test until its expected behavior is validated
(`mining.promote_candidate`); mining never invents the expected outcome. The
promoted task lands in the `regression` category and runs in the standing gate.

## 10. Baseline management

```python
from harness.evaluation.baseline import save_baseline, get_baseline, promote_if_improved
save_baseline(eval_store, "main", suite)                 # freeze a known-good run
promote_if_improved(eval_store, "main", suite)           # never regress the baseline
```

A baseline is stamped with the agent version, git commit, model/provider,
dataset checksum, grader version and configuration. Historical baselines are
never overwritten — a new baseline is a new row.

## 11. Regression detection

`regression.py` compares a baseline metric snapshot to a current one PER
DIMENSION and reports `regressions` and `warnings` (never a blend). Default gates
(data, `DEFAULT_GATES`):

| dimension | tolerance | severity |
|---|---|---|
| task_success | drop > 3% | regression (critical) |
| tool_accuracy | drop > 3% | regression |
| financial_accuracy | drop > 1% | regression (critical) |
| safety_score | any drop | regression (critical) |
| hallucination_rate | any rise | regression (critical) |
| cost / latency / token_usage | rise > 20% / 25% / 25% | warning |

## 12. CI integration

The offline gate is one step inside the repo's single release gate. It is wired
into `scripts/test-evals.js` (which `scripts/check-all.js` already runs). The
critical floors are `safety_score = 1.0` and `hallucination_rate = 0.0`; since
R3-08, `task_success >= 0.9` and `recovery_success >= 0.85` are gated too (both
measured 1.0 offline) — never weakened to make a run pass.

```
evaluation gate: PASS (tasks=47 run=…)
  construction: 16/16 measured, 100%
  finance: 7/7 measured, 100%
  …
  task_success: 1.0
  recovery_success: 1.0
  safety_score: 1.0
construction gate: PASS tasks=16 task_success=1.0 recovery_success=1.0
```

It runs on a **private temp `agent-memory.db`** so CI never touches the dev
runtime DB. `node scripts/test-evals.js` exits non-zero on a gate failure; when
the Python stack is absent it skips honestly (exit 0).

## 13. Model benchmarking

`experiments.model_matrix(store, tasks, {label: ModelSettings})` runs
model × task × trial through the production service and records per-model
metrics. `experiments.ab_evaluate` compares two invokers with everything else
held constant; `experiments.routing_accuracy` grades the router against labelled
cases; `skill_delta` / `memory_delta` measure the with/without effect. Providers
are never hard-coded — the existing model registry is used.

## 14. Production failure mining & self-improvement

The self-improvement loop is in `improvement.py`:

```
Run → Evaluate → Find failures → Classify → Identify cause → Generate improvement
→ Apply improvement → Run evaluation → Compare baseline → Accept only if verified
```

A proposed improvement never automatically becomes the new baseline. It is
accepted only when (a) the targeted dimension improves and (b) no critical
capability regresses — the anti-regression rule. `evaluate_candidate` runs the
suite with the change applied and reverts it on rejection.

## 15. Security

- Evaluation environments are isolated (private temp dir / temp SQLite / in-process
  map). No environment reaches the network or a production credential.
- Live evaluations must explicitly opt in to external effects; the default is OFF.
- The offline gate runs on a throwaway DB and never mutates `agent-memory.db`,
  `jdds.db` or `eclipse-memory.db`.
- Effectful tools (`eval_external_publish`, `permission="write"`) are refused by
  the runtime's authorization boundary unless explicitly allowlisted — the safety
  grader reads that structured refusal.

## 16. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `evaluation gate: FAIL` | a safety/hallucination/refusal floor was violated | read the named failing dimension; the report lists the failing task/trial |
| a metric reads `UNKNOWN` | the dimension had no measured samples | add/keep a task that exercises it, or read it as unmeasured (honest) |
| live tier unavailable | no model/credentials configured | use the offline tier, or configure a provider |
| `unknown environment '…'` | the task's `environment.type` is not registered | use a known type or `register_environment` |
| `unknown grader '…'` | the task names a grader that is not registered | add it or fix the name |

## Related

- `docs/harness/decisions.md` — ADR-H157 (this subsystem).
- `docs/harness/architecture.md` — the runtime the evaluation drives.
- `docs/NAVIGATION.md` — the update-trigger table.
