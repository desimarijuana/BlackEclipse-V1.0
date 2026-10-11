# Statistical Engine API Contracts

> `last-verified: 2026-10-10`
> Python routes: `python/harness/routers/stats.py` (prefix `/stats/v1`, operator-gated)
> Next.js front door: `src/app/api/stats/[...path]/route.ts` → `src/lib/stats-client.ts`

All routes require the harness operator token (attached server-side by the
Next.js proxy; never exposed to the browser). Datasets are supplied by the caller
or fetched through the market adapter; the engine adds no provider of its own.

## Routes

### Capabilities / tools / datasets
| Method | Path | Body / query | Returns |
| --- | --- | --- | --- |
| GET | `/stats/v1/capabilities` | — | `{available, tools[]}` |
| GET | `/stats/v1/tools` | — | `{tools:[{name,category,description,inputSchema}]}` |
| GET | `/stats/v1/datasets/series` | `symbol,interval,start,end,field` | resolved series + provenance |

### Analyses
| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/stats/v1/analyses` | `{tool, arguments, useCache?}` | envelope (+`analysisId`,`cacheHit`) |
| POST | `/stats/v1/analyses/run` | `{tool, symbols[], interval,start,end,field,arguments}` | data-driven envelope |
| POST | `/stats/v1/analyses/submit` | same | `{runId}` |
| GET | `/stats/v1/analyses` | `tool?,limit?` | `{analyses[]}` |
| GET | `/stats/v1/analyses/{id}` | — | analysis record |

### Jobs
| Method | Path | Returns |
| --- | --- | --- |
| GET | `/stats/v1/jobs` | `{jobs[]}` |
| GET | `/stats/v1/jobs/{id}` | run state (`includeResult=true` adds result) |
| POST | `/stats/v1/jobs/{id}/cancel` | `{cancelled}` |

### Formulas
| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/stats/v1/formulas/validate` | `{expression}` | `{valid,variables,functions}` |
| POST | `/stats/v1/formulas/execute` | `{expression, sample}` | series + summary |

### Feature registry
| Method | Path | Returns |
| --- | --- | --- |
| GET | `/stats/v1/features` | `{features[]}` |
| POST | `/stats/v1/features` | `{feature}` |
| GET | `/stats/v1/features/{id}` | `{feature, version}` |
| GET | `/stats/v1/features/{id}/versions` | `{versions[]}` |
| POST | `/stats/v1/features/{id}/versions` | new version |
| POST | `/stats/v1/features/{id}/validate` | validation result |
| POST | `/stats/v1/features/{id}/preview` | computed series |
| POST | `/stats/v1/features/{id}/rollback` | feature with selected version |
| GET | `/stats/v1/features/{id}/dependencies` | dependency graph |

### Artifacts / audit / generic
| Method | Path | Returns |
| --- | --- | --- |
| GET | `/stats/v1/artifacts/{id}` | checksummed artifact content |
| GET | `/stats/v1/audit` | audit events |
| POST | `/stats/v1/execute` | `{tool, arguments}` → envelope |
| POST | `/stats/v1/{tool}` | `arguments` → envelope |

## Response envelope

```jsonc
{
  "status": "ok" | "error",
  "tool": "calculate_returns", "toolVersion": "1.0.0",
  "parameters": {}, "summary": {}, "results": {}, "diagnostics": {},
  "warnings": [], "errors": [{"code": "...", "message": "..."}],
  "provenance": {"...": "...", "dataset": {"symbols": [], "provenance": []}},
  "executionMetadata": {}, "artifactReferences": [],
  "cacheHit": false, "durationMs": 12, "analysisId": "san_..."
}
```

HTTP status: `400` invalid input, `422` insufficient/missing data, `404` unknown
resource, `503` store/gateway unavailable, `500` internal.

## Agent tools

The fourteen statistical tools, `stats_capabilities`, the data-driven analysis
tools (`run_statistical_analysis`, `submit_statistical_analysis`,
`stats_analysis_status`, `stats_cancel_analysis`, `stats_list_analyses`,
`stats_get_analysis`), the formula tools (`validate_formula`, `execute_formula`)
and the registry tools (`stats_save_feature`, `stats_list_features`,
`stats_get_feature`, `stats_version_feature`, `stats_rollback_feature`,
`stats_validate_feature`, `stats_preview_feature`,
`stats_feature_dependencies`) are all registered and allowlisted for agents in
`python/harness/agents.py`.
