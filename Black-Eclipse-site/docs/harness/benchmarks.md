# Published benchmarks

**GENERATED FILE - do not edit it.** Regenerate with:

```bash
python -m harness.evaluation.report
```

A number here is only worth what its provenance is worth, so every
tier carries its dataset, its checksum, its agent version, its commit
and its grader version. The two tiers are kept APART on purpose: the
offline tier measures the harness, the live tier measures the agent.

## Offline tier - the scripted model

A deterministic script replaces the model, so this measures the
**runtime** (the tool surface, the policy, the graders, the wiring)
- not the model. It is the floor the harness must never fall below.

- run: `evalrun-1794252916357`
- dataset: `eclipse-benchmark` @ `1` (checksum `7b701a93ce4706def8de154fd6a311b9`)
- tier: 0
- agent version: `0.1.0`
- git commit: `5b8cf410bded9420c4127f58b0603f7510e5550b`
- grader version: `1`
- config: `{'trials': 1, 'tier': 0, 'split': 'validation', 'graderVersion': 1}`
- gate: **PASS**

| dimension | value |
|---|---|
| task_success | 0.9969 |
| tool_accuracy | 0.9712 |
| research_accuracy | UNKNOWN |
| citation_accuracy | 0.0000 |
| code_correctness | 1.0000 |
| financial_accuracy | 1.0000 |
| memory_accuracy | 1.0000 |
| planning_quality | 0.8937 |
| recovery_success | 1.0000 |
| misroute_rate | 0.0000 |
| escalation_correct | 1.0000 |
| provenance | 1.0000 |
| honesty | 1.0000 |
| artifact_delivery | 1.0000 |
| visual_delivery | 1.0000 |
| hallucination_rate | 0.0000 |
| safety_score | 1.0000 |
| cost | 0.0000 |
| latency | 0.0551 |
| token_usage | 0.0000 |
| reliability | 1.0000 |

### Per category

| category | passed / measured | unmeasured | pass rate |
|---|---|---|---|
| adversarial | 14/14 | 0 | 100.0% |
| browser | 0/0 | 1 | UNKNOWN |
| citations | 0/1 | 1 | 0.0% |
| coding | 4/4 | 0 | 100.0% |
| core | 4/4 | 0 | 100.0% |
| finance | 270/270 | 0 | 100.0% |
| long_horizon | 2/2 | 0 | 100.0% |
| memory | 2/2 | 0 | 100.0% |
| parallel | 3/3 | 0 | 100.0% |
| planning | 2/2 | 0 | 100.0% |
| recovery | 7/7 | 0 | 100.0% |
| regression | 1/1 | 6 | 100.0% |
| research | 0/0 | 4 | UNKNOWN |
| safety | 4/4 | 0 | 100.0% |
| tools | 12/12 | 0 | 100.0% |

### Unmeasured tasks

- `research.live.001`
- `browser.live.001`
- `replay.quote.001`
- `replay.fundamentals.001`
- `replay.news.001`
- `replay.unavailable.001`
- `replay.stale.001`
- `replay.refused.001`
- `research.cite.001`
- `research.unavailable.001`
- `research.conflict.001`
- `research.stale.001`

## Live tier - a real model

This is the only tier that measures the **agent**. The model is
named, and the run is reproducible from the provenance below.

- run: `live:7e9d161037e45360f95717198f839ced`
- dataset: `eclipse-benchmark` @ `1` (checksum `7b701a93ce4706def8de154fd6a311b9`)
- tier: 1
- agent version: `0.1.0`
- git commit: `5b8cf410bded9420c4127f58b0603f7510e5550b`
- grader version: `unknown`
- config: `{'tier': 1, 'taskCount': 282, 'measuredTrials': 282}`
- gate: **PASS**

fresh full live run evalrun-1794250611536: gate PASS (task_success 0.9574468085106383, hallucination_rate 0.0)

| dimension | value |
|---|---|
| task_success | 0.9574 |
| tool_accuracy | 0.4776 |
| research_accuracy | UNKNOWN |
| citation_accuracy | 0.0000 |
| code_correctness | UNKNOWN |
| financial_accuracy | 0.9857 |
| memory_accuracy | 1.0000 |
| planning_quality | 0.9995 |
| recovery_success | 1.0000 |
| misroute_rate | UNKNOWN |
| escalation_correct | UNKNOWN |
| provenance | UNKNOWN |
| honesty | UNKNOWN |
| artifact_delivery | UNKNOWN |
| visual_delivery | 0.7500 |
| hallucination_rate | 0.0000 |
| safety_score | 1.0000 |
| cost | 0.0000 |
| latency | 10.4424 |
| token_usage | 323958.8723 |
| reliability | 1.0000 |
