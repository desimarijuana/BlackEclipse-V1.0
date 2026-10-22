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

- run: `evalrun-1792638945412`
- dataset: `eclipse-benchmark` @ `1` (checksum `d8939d9ab004d61990ced8ca95adca4e`)
- tier: 0
- agent version: `0.1.0`
- git commit: `e4abf567a4eeebe45ef40d8cdad3369aa7b8c45a`
- grader version: `1`
- config: `{'trials': 1, 'tier': 0, 'split': 'validation', 'graderVersion': 1}`
- gate: **PASS**

| dimension | value |
|---|---|
| task_success | 1.0000 |
| tool_accuracy | 0.9683 |
| research_accuracy | UNKNOWN |
| citation_accuracy | 1.0000 |
| code_correctness | 1.0000 |
| financial_accuracy | 1.0000 |
| memory_accuracy | 1.0000 |
| planning_quality | 0.8791 |
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
| latency | 0.1341 |
| token_usage | 0.0000 |
| reliability | 1.0000 |

### Per category

| category | passed / measured | unmeasured | pass rate |
|---|---|---|---|
| adversarial | 6/6 | 0 | 100.0% |
| browser | 0/0 | 1 | UNKNOWN |
| citations | 1/1 | 0 | 100.0% |
| coding | 4/4 | 0 | 100.0% |
| core | 4/4 | 0 | 100.0% |
| finance | 12/12 | 0 | 100.0% |
| long_horizon | 2/2 | 0 | 100.0% |
| memory | 2/2 | 0 | 100.0% |
| parallel | 3/3 | 0 | 100.0% |
| planning | 2/2 | 0 | 100.0% |
| recovery | 7/7 | 0 | 100.0% |
| regression | 1/1 | 6 | 100.0% |
| research | 0/0 | 1 | UNKNOWN |
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

## Live tier - a real model

**NOT MEASURED.**

no live run has been recorded. The live lane needs a configured provider; run `npm run eval:live -- --model <provider>/<model>`.

This is published as missing on purpose. A live number that nobody
has run is a rumour, and a rumour in a benchmark table is worse
than an empty row.
