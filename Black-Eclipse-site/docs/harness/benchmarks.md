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

- run: `evalrun-1792864915449`
- dataset: `eclipse-benchmark` @ `1` (checksum `7e4a3d9264445b9c4050b78d7abf05d1`)
- tier: 0
- agent version: `0.1.0`
- git commit: `00ac60d8eb8895e867ef10f914758c33743361f0`
- grader version: `1`
- config: `{'trials': 1, 'tier': 0, 'split': 'validation', 'graderVersion': 1}`
- gate: **PASS**

| dimension | value |
|---|---|
| task_success | 1.0000 |
| tool_accuracy | 0.9712 |
| research_accuracy | UNKNOWN |
| citation_accuracy | 1.0000 |
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
| latency | 0.0792 |
| token_usage | 0.0000 |
| reliability | 1.0000 |

### Per category

| category | passed / measured | unmeasured | pass rate |
|---|---|---|---|
| adversarial | 14/14 | 0 | 100.0% |
| browser | 0/0 | 1 | UNKNOWN |
| citations | 1/1 | 1 | 100.0% |
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

- run: `live:f368f388bb662ce717c19da715f0bb44`
- dataset: `eclipse-benchmark` @ `1` (checksum `d6375ca430594df65fc95daec98c2f1f`)
- tier: 1
- agent version: `0.1.0`
- git commit: `2b6df30a65289d51e9a7c8a3bcf825fb0b109af0`
- grader version: `unknown`
- config: `{'tier': 1, 'taskCount': 198, 'measuredTrials': 196}`
- gate: **FAIL**

Live-eligible re-score from this same run: 167/196 = 0.8520. The other 46 measured trials are tier-0 scripted tasks that require eval-only tools or synthetic environments; the production service cannot run them, so they are excluded from the agent measurement. Dimensions that came only from those fixtures are UNKNOWN here; the raw run including them scored 0.6901.

| dimension | value |
|---|---|
| task_success | 0.8520 |
| tool_accuracy | UNKNOWN |
| research_accuracy | UNKNOWN |
| citation_accuracy | UNKNOWN |
| code_correctness | UNKNOWN |
| financial_accuracy | 0.8706 |
| memory_accuracy | UNKNOWN |
| planning_quality | UNKNOWN |
| recovery_success | UNKNOWN |
| misroute_rate | UNKNOWN |
| escalation_correct | UNKNOWN |
| provenance | UNKNOWN |
| honesty | UNKNOWN |
| artifact_delivery | UNKNOWN |
| visual_delivery | UNKNOWN |
| hallucination_rate | 0.0000 |
| safety_score | UNKNOWN |
| cost | 0.0000 |
| latency | 4.9609 |
| token_usage | 28748.0041 |
| reliability | 1.0000 |

### Gate failures

- task_success=0.8520 < 0.9
