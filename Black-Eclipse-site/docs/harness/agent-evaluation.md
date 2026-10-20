---
title: Agent Evaluation System
status: Current
last-verified: 2026-10-18
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

### 5.2 Routing benchmark (round 4, W3.2)

`evaluation/routing.py` runs `harness/ui/routing_benchmark_v1.json` (eight
deterministic Compose/Engineer cases, including the multi-zone clock) through
the REAL classifier. `run_offline_gate` injects its two dimensions into the
SAME threshold check as the agent suite and records the source in
`SuiteResult.routing` — it is explicitly **not** an agent-trial measurement:

| dimension | source | gate |
|---|---|---|
| `misroute_rate` | mismatched cases / all cases | maximum 0.0 |
| `escalation_correct` | correct engineer/both verdicts / expected-escalation cases | minimum 1.0 |

The benchmark grows from a production misroute: add the failing request with its
recorded expected verdict, then fix the classifier until the gate is green again.

**The end-to-end tier (`routing_e2e_v1.json`).** The classifier tier above is
the fast gate; four of the same scenarios ALSO run through the real
`execute_run` graph as ordinary evaluation tasks (`routing_e2e.*`, category
`recovery`/`tools`) and are graded on the REAL resulting state:

- the `ui` environment (`environments.py::UiStateEnvironment`) reports the
  durable engineering tasks/plans a trial created (kind, `capabilityGap`,
  status, acceptance count) — the invoker binds the trial's real `UiService` +
  `TaskManager` and hands store cleanup to the environment's teardown (grading
  reads the store after invoke);
- every trial gets its OWN isolated store, so concurrent trials can never see
  each other's durable work;
- `ScriptedAgentInvoker` registers the `ui_*` + `task_*` families, so a
  scenario calls the real `ui_classify_request` / `ui_start_engineering` tools;
- a restored pre-W0 defect (a witness-less Compose verdict plus no catalog
  re-check) makes the clock task FAIL on the missing engineering task — the
  tier is a release gate for the whole escalation path, not just the
  classifier (`test_evaluation_routing_e2e.py`).

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

**Candidate harnesses (RSL R3).** `evaluation/candidate_invoker.py` implements
the `AgentInvoker` protocol for a validated `HarnessSnapshot`: the real graph
runs with the snapshot's system prompt, tool subset and step/call ceilings, in a
private per-trial store/registry, with the trial environment bound and cleaned
up. `validate_snapshot` refuses a tool outside the base allowlist, a raised
ceiling or an unknown skill id. `self_improvement/security.py`
(`RSL_DENY_GLOBS`, `assert_landable_target`) refuses a subject that owns the
evaluator, tests, policy, approvals or landing machinery. Candidate runs never
write the production store and never activate a change.

**R4 conductor.** `self_improvement/loop.py` scans and atomically claims
`EvolutionCandidate` rows (one experiment at a time, daily budget + lease).
Code candidates use `verify_code` (owning tests in a worktree; the benchmark is
recorded as UNMEASURED by default), while surface candidates use `verify_surface`
(a measured path recorded on an `EvaluationRun` with RSL metadata). With
`HARNESS_RSL_CODE_BENCHMARK=on`, `verify_code_benchmark` runs the deterministic
suite in an isolated patched worktree (`evaluation/worktree_invoker.py`) and
compares it to the unpatched baseline; only then is a code candidate recorded as
`MEASURED`. Evaluation, candidate-trials and gate runs set
`RunRequest.liveSurface=False`, so an operator-activated live surface can never
contaminate a measurement. `landing.prepare` returns the existing promotion
preview and never applies it.

## 7.1 Splits and provenance

**Splits.** `select_tasks(..., split=...)` filters `optimization`,
`validation`, `held_out` and `release`. A task's `metadata.split` wins, then the
dataset's top-level `metadata.split` (preserved per task by
`load_all_builtin`'s `splitById` map), then `validation`. The built-ins are:
`benchmark_v1` + `construction_v1` = validation (47), `routing_e2e_v1` =
optimization (4), `team_v1` = held_out (2). `select_tasks` without `split`
still returns every task (53) for the release gate; an unknown split is refused.

**Provenance.** A persisted run records `agentVersion`, `gitCommit` (or
`gitCommitUnavailable`), the dataset checksum, and a config identity
(`trials`, `tier`, `split`, `graderVersion`, optional `seed`/`temperature`).
Metadata carries `taskFingerprintDigest`, `taskCount`, `graderVersion`, the
split and the measured-trial count. Task fingerprints are persisted through
`upsert_task`; each trial's score JSON carries `graderVersion`.
`evaluation.provenance.require_provenance` refuses a run missing a required
piece. Cost and latency are `None` when no real source reported them, never
`0`; `cost_per_success` is UNMEASURED if any measured trial's cost is unknown.

## 8. Adding tasks

1. Add a task object to `python/harness/evaluation/datasets/benchmark_v1.json`
   (or a new `datasets/<name>.json` — `construction_v1.json` is the R3-08
   construction benchmark; `load_all_builtin` merges every dataset and rejects
   duplicate ids).
2. Bump the dataset `datasetVersion` and, if you changed an existing task, its
   `version`. Never edit a task in place without bumping `version`.
3. A construction task should declare `metadata.suites: ["construction"]`,
   `metadata.scenario` and `metadata.measures` (the signals it exercises).
   A task that is not part of the validation acceptance set declares
   `metadata.split` (`optimization`, `held_out` or `release`).
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
| misroute_rate | any rise | regression (critical) |
| escalation_correct | any drop | regression (critical) |
| cost / latency / token_usage | rise > 20% / 25% / 25% | warning |

## 12. CI integration

The offline gate is one step inside the repo's single release gate. It is wired
into `scripts/test-evals.js` (which `scripts/check-all.js` already runs). The
critical floors are `safety_score = 1.0` and `hallucination_rate = 0.0`; since
R3-08, `task_success >= 0.9` and `recovery_success >= 0.85` are gated too (both
measured 1.0 offline) — never weakened to make a run pass.

```
evaluation gate: PASS (tasks=53 run=…)
  construction: 16/16 measured, 100%
  finance: 7/7 measured, 100%
  …
  task_success: 1.0
  recovery_success: 1.0
  misroute_rate: 0.0
  escalation_correct: 1.0
  safety_score: 1.0
  routing: cases=8 misroute_rate=0.0 escalation_correct=1.0
construction gate: PASS tasks=16 task_success=1.0 recovery_success=1.0
```

It runs on a **private temp `agent-memory.db`** so CI never touches the dev
runtime DB. `node scripts/test-evals.js` exits non-zero on a gate failure; when
the Python stack is absent it skips honestly (exit 0).

### 12.1 Self-evolution metrics (round 4, W7)

`evaluation/repair_metrics.py` adds the §1 metric block to the gate report:
`time_to_repair_ms` + `self_repair_precision` (recovery incidents),
`requirement_completeness` (goal-contract task criteria), `cost_per_success` +
`unauthorized_action_rate` (evaluation trials), plus the R8 RSL block:
`rsl_experiments`, `rsl_accepted`, `rsl_rejected`, `rsl_unmeasured` (a partition
of completed RSL experiment runs; UNMEASURED is its own bucket) and
`regression_rate` (measured runs with a recorded regression). The offline gate
measures the suite-backed dimensions and prints `UNMEASURED` for store-backed
ones with no samples — an unmeasured dimension is never fabricated. A
production run passes real incidents/tasks/runs via
`collect_self_evolution_metrics(...)` or `store=...`; the runtime exposes the
same block read-only at `GET /recovery/metrics` (incident outcomes read from the
`action="outcome"` attempts, goal tasks from the task store, RSL runs from the
`EvaluationRun` rows). The RSL-specific deterministic end-to-end gate is
`self_improvement/gate.py`, wired into `scripts/test-evals.js`.

## 13. Model benchmarking

`experiments.model_matrix(store, tasks, {label: ModelSettings})` runs
model × task × trial through the production service and records per-model
metrics. `experiments.ab_evaluate` compares two invokers with everything else
held constant; `experiments.routing_accuracy` grades the router against labelled
cases; `skill_delta` / `memory_delta` measure the with/without effect. Providers
are never hard-coded — the existing model registry is used.

### 13.1 Multi-agent comparison (round 4, W12)

`evaluation/team_benchmark.py` + `experiments.multi_agent_compare` compare ONE
agent against a 2–3 specialist team on the SAME frozen task. This is the
adoption gate for parallelism (ADR-H213), not a second orchestration system.

- The team trial runs the REAL stack — `TeamService` → `A2AService` →
  `TaskScheduler` → the ONE `execute_run` graph — over a per-trial isolated
  store (`TeamAgentInvoker`, the `ScriptedAgentInvoker` isolation pattern; a
  lightweight host instead of a full `AgenticService`, so a benchmark never
  touches process-wide singletons or the developer's databases). Each subtask
  executes its own deterministic script; the model seam answers ONLY while a
  team trial is active, so a team trial can never reach a provider (a repair
  task created with no script gets a deterministic "(no script)" answer).
- Both variants are graded by the SAME graders on the REAL resulting state
  (`state` + `tool`). Tool-call arguments are captured at the registry boundary
  and folded back into the AGGREGATED trajectory; call ids carry a per-subtask
  prefix (`_script_messages(call_id_prefix=…)`) so concurrent child runs cannot
  collide.
- `multi_agent_compare` returns both suites' recorded run ids + metrics,
  measured axes (`taskSuccess`, wall clock, `toolCalls`, `modelSteps`) and a
  deterministic `adoption` verdict: the team is adopted ONLY when quality does
  not regress AND it shows a real gain (wall clock improved ≥ 15%, or strictly
  fewer tool calls). An unmeasured variant decides nothing. Cost/tokens are
  published as `UNMEASURED` for the scripted tier — never a fabricated 0.
- With `persist=True` both variants also write their durable
  `EvaluationModel` rows, so a comparison is recorded with the frozen-set
  results rather than only printed.

**The frozen set (`datasets/team_v1.json`)** — two multi-step builds, each
carrying BOTH a single-agent program (`metadata.agent_script`) and the team
decomposition (`metadata.team`: members, dependency-aware subtasks, one script
per subtask): `team.multi_leg_build.001` (two independent module legs + a
dependent report) and `team.verified_fix.001` (a repair + an independent
verification leg). The single-agent program also runs in the standing offline
gate like any other task.

**The recorded 2026-10-18 measurement** (3 trials × 2 tasks, offline scripted
tier): quality 1.0 both (6/6 measured); wall clock 1454 ms single vs 2234 ms
team (+53.6%); tool calls 27 vs 30; model steps 33 vs 45. Verdict: **not
adopted** — quality equal, no latency/cost gain. This is the expected offline
result: every evaluation tool executes synchronously in one event loop, so
"parallel" legs cannot overlap real work while the team pays the plan/task
overhead. The harness is the gate for re-measurement on the live tier; nothing
in the default path routes work to a team.

**The live tier (`multi_agent_compare_live`).** The same comparison with REAL
models: `LiveTeamAgentInvoker` runs the identical real stack with NO script
pool — every subtask resolves the operator's real `modelSettings` through the
production `build_chat_model` path (the scripted seam's pool is never set, and
if the seam is installed by an offline trial in the same process an unset pool
delegates to the original build) — and the single-agent variant is the
production `ServiceAgentInvoker`. Without model settings every trial is
honestly `unmeasured` ("published unmeasured, never fabricated"): the live
verdict is open until a run with a configured provider. Token/cost axes are
published only when a variant's REAL trajectories reported them
(`team_benchmark.measured_usage`) — the scripted tier's zeros stay unmeasured,
and a live run's provider-reported usage is summed. Opt-in live smoke:
`test_live_team_comparison_through_a_real_provider` (`HARNESS_TEAM_LIVE_IT=1`,
never in CI; `HARNESS_TEAM_LIVE_{PROVIDER,MODEL,BASE_URL,API_KEY}`).

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

- `docs/harness/decisions.md` — ADR-H157 (this subsystem), ADR-H213 (multi-agent
  adoption is measured, never assumed).
- `docs/harness/architecture.md` — the runtime the evaluation drives.
- `docs/harness/bot-team-orchestration.md` — the team machinery W12 measures.
- `docs/NAVIGATION.md` — the update-trigger table.
