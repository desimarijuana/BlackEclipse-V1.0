---
title: ML Research Lab — Architecture and Operations
status: Current
last-verified: 2026-10-11
---

# ML Research Lab

**Who this is for:** anyone working on, or researching with, Eclipse's ML Lab.

This documents **why** the ML Lab is built the way it is, the contracts at each
boundary, and what is actually implemented versus planned. It does not restate
code you can read — it records intent, invariants and navigation.

> **Status: production-hardening slice — IMPLEMENTED and VERIFIED.**
> Phases 0–5 plus the reliability/isolation core of Phase 12: durable,
> cancellable, resource-bounded background training through the Execution
> Fabric; real scikit-learn / LightGBM / XGBoost / sklearn-forest / extra-trees
> adapters (installed and tested); a leakage test suite and an end-to-end
> acceptance scenario. The remaining feature phases (Optuna, calibration,
> ensembles, SHAP, drift monitoring) are **not** implemented yet. See "Roadmap".

## What exists

The ML Lab is a supervised-learning research workflow integrated with the
existing Eclipse financial infrastructure. It reuses — and never duplicates —
the ONE market data gateway, the shared Feature Registry, `agent-memory.db`
persistence, the gzipped artifact convention and the agent tool registry.

```
Next.js front door                     Python harness (the ONLY compute)
  /api/ml/*  ──────────────────────►   /ml/v1/*           (routers/ml.py)
  src/lib/ml-client.ts                 ├─ service.py      orchestration + singleton MLStore
  src/components/screens/ml-lab/       ├─ datasets.py     gateway → immutable dataset version
        ml-lab-screen.tsx (AppTab)     ├─ quality.py      severity-graded data quality
                                       ├─ targets.py      label construction
                                       ├─ splits.py       chronological/walk-forward/purged
                                       ├─ features.py     fit-on-train-only selection
                                       ├─ metrics.py      classification/regression/ranking
                                       ├─ adapters.py     model adapters (NumPy + optional)
                                       ├─ training.py     fold-fit pipeline + final holdout
                                       ├─ store.py        MLStore on agent-memory.db
                                       └─ tools.py        15 ml_* agent tools
```

## Boundaries and contracts

All contracts are plain dataclasses in `python/harness/ml/models.py`, each
carrying `schemaVersion` (`CONTRACT_SCHEMA_VERSION`) and `ML_ENGINE_VERSION`.

| Boundary | Contract | Notes |
|---|---|---|
| Dataset build | `DatasetSpec` → immutable manifest + arrays | symbols, interval, feature names, `TargetSpec`, missing policy |
| Label | `TargetSpec` → label matrix + `labelStart`/`labelEnd` | start = t, end = t+horizon; the basis of purging |
| Validation | `SplitSpec` → folds (train/test/purged/embargoed) | no random splits are offered at all |
| Experiment | `ExperimentConfig` | dataset@version, family, hyperparameters, selection, split, seed |
| Model artifact | JSON state + SHA-256 | never a pickle; loading verifies the hash first |

### Hard invariants (the correctness gate)

1. **Chronological only.** `splits.py` builds `chronological`, `walk_forward`
   and `purged_kfold` folds. Random/shuffled splitting is deliberately absent.
2. **Label overlap is purged.** A training row whose `[labelStart, labelEnd]`
   interval overlaps any test label interval is removed; observations within
   `embargo` periods after the test window are embargoed.
3. **Independent leakage check.** `assert_no_leakage` re-derives the invariant
   from the emitted fold assignments — a bug in split construction cannot pass
   silently.
4. **Fit-on-train only.** Standardisation and feature selection are fitted on
   the training rows of each fold and merely applied to the test rows.
5. **Final test isolation.** The final production model is fitted on a
   chronological 80% of the finite rows and evaluated on the held-out 20%; that
   holdout is never used for selection.
6. **No fabrication.** An unavailable optional library raises
   `MODEL_UNAVAILABLE`; a metric that cannot be computed returns `null`; the
   quality engine blocks critical findings.

## Data provenance

Datasets are built ONLY through `stats.datasets.resolve_frame(gateway, …)` — the
same Market Data Gateway the stats/quant/factors engines use. The ML engine never
contacts a provider directly and never fills a missing observation with an
invented value. Each dataset version records: symbols, interval, window,
feature names, target spec, missing policy, coverage, quality report, timestamp
range and a content `dataHash`; the full matrix is stored as a gzipped artifact.

Built-in features (`datasets.BUILTIN_FEATURES`): `ret_1`, `ret_5`, `ret_21`,
`mom_63`, `vol_21`, `volume_z_21`. A feature named `feature:<name>` is evaluated
against the shared Feature Registry (`stats.feature_registry`), so Factor Lab and
ML Lab consume the same registered definitions.

## Model adapters

| Family | Tier | Tasks | Serialisation |
|---|---|---|---|
| `dummy` | native (NumPy) | classification, regression | JSON |
| `ridge` | native (NumPy) | regression | JSON |
| `logistic` | native (NumPy) | classification | JSON |
| `random_forest` | native (NumPy CART + bagging) | classification, regression | JSON |
| `sklearn_forest` / `sklearn_extra_trees` | optional | classification, regression | native loader |
| `lightgbm` / `xgboost` | optional | classification, regression | native loader |

`GET /ml/v1/capabilities` (and the `ml_model_capabilities` tool) reports what is
**actually** importable in the running runtime. Optional wheels are installed
from `python/requirements-ml.txt`, which is intentionally separate from
`python/requirements.txt` so the default install stays lightweight. In the
verified environment all eight families are available: sklearn 1.6, LightGBM
4.7, XGBoost 3.4.

Third-party estimators are serialized with joblib (pickle fallback), embedded as
base64 in the model artifact, and are only ever loaded after the artifact's
SHA-256 hash is verified — a trusted, locally-produced artifact, never an
untrusted upload.

## Background execution (Execution Fabric)

Training is long and CPU-bound, so it runs on a **dedicated ML worker** on its
own `ml` queue (`WorkerKind.ML` / `QueueName.ML`) rather than in the request path
or the agent loop. Submitting `POST /ml/v1/experiments` with `background:true`
(or the `ml_run_experiment` tool with `background:true`) returns a job id
immediately; the worker invokes the SAME `service.run_experiment_job` pipeline.
The Fabric provides: hard cancellation (polled between folds, and a
`CancelledError` path that never leaves a run stuck "running"), a wall-clock
timeout, retry/DLQ, crash recovery, and progress events. The job output is a
COMPACT summary (the full result is persisted as a hash-addressed ML artifact —
the Fabric output column is bounded). Poll with `GET /ml/v1/jobs/{id}`, cancel
with `POST /ml/v1/jobs/{id}/cancel`.

## Resource guardrails

`ml/config.py` reads `HARNESS_ML_*` and hard-limits every run:
`HARNESS_ML_MAX_ROWS` (default 2,000,000 — a bigger dataset is refused with 413),
`HARNESS_ML_MAX_FOLDS`, `HARNESS_ML_MAX_SECONDS` (also the worker timeout source),
`HARNESS_ML_MAX_CONCURRENT`, `HARNESS_ML_MAX_ARTIFACT_MB`, `HARNESS_ML_ENABLED`.
A run exceeding its budget stops at the next fold boundary with
`TIME_BUDGET_EXCEEDED`; it is recorded as `timed_out`, never completed.

## Persistence

`MLStore` (`store.py`) uses `agent-memory.db` with additive, idempotent DDL —
never `jdds.db`, never `eclipse-memory.db`. Tables: `MLDataset`,
`MLDatasetVersion`, `MLTargetDefinition`, `MLSplitDefinition`,
`MLFeatureSelection`, `MLExperiment`, `MLExperimentRun`, `MLFoldResult`,
`MLModel`, `MLModelVersion`, `MLArtifact`, `MLPredictionBatch`,
`MLApprovalEvent`, `MLAudit`. Immutable version records are kept distinct from
mutable run status. Large arrays (feature matrices, split assignments, out-of-
fold predictions, model state) live as gzipped JSON artifacts under
`.black-eclipse/ml/artifacts/`; the database holds metadata, hashes and lineage.

## Lifecycle and governance

`draft → evaluated → approved_research → archived` (`service.transition_model`).
Every transition is recorded in `MLApprovalEvent` and `MLAudit`. **Research
approval is not trading authorization** — no trading controls exist in the ML
Lab and none are enabled by approval.

## HTTP surface (`/ml/v1`, operator-gated)

`GET capabilities` · `GET/POST datasets` · `GET datasets/{id}/versions[/{v}]` ·
`GET/POST experiments` · `GET experiments/{id}/runs` · `GET runs/{id}` ·
`POST runs/{id}/reproduce` · `GET models` · `POST models/register` ·
`GET models/{id}` · `POST models/{id}/transition` · `GET models/{id}/verify` ·
`POST models/{id}/predict`.

Agent tools (`ML_TOOLS`, 15): `ml_list_datasets`, `ml_list_features`,
`ml_build_dataset`, `ml_run_experiment`, `ml_get_run`, `ml_list_experiments`,
`ml_reproduce_run`, `ml_register_model`, `ml_list_models`, `ml_verify_model`,
`ml_predict`, `ml_model_capabilities`, `ml_job_status`, `ml_list_jobs`,
`ml_cancel_job`. `ML_TOOLS` is imported by `agents.py` and spread into the
`ECLIPSE_AGENT` allowlist, so the supervised chat agent can drive ML research.

## UI

The ML Lab is an SPA tab (`ml-lab`) rendered by
`src/components/screens/ml-lab/ml-lab-screen.tsx` via the shell
(`stock-chat.tsx`), and reachable from the command palette (`page-ml-lab` in
`src/lib/search/registry.ts`). Tabs: Overview (real capabilities + counts),
Datasets (build + quality + versions), Experiments (train + folds + feature
importance + reproduce + register), Model Registry (verify + lifecycle). Every
page has loading / empty / populated / error states backed by real endpoints.

## Tests

- `python/tests/test_ml_core.py` — metrics, targets, splits/leakage, selection,
  adapters, quality, end-to-end training.
- `python/tests/test_ml_store.py` — dataset immutability, run persistence, model
  registry, artifact tamper detection, reproduction, honest failure recording.
- `python/tests/test_ml_models_ext.py` — every required family (baseline,
  scikit-learn, LightGBM, XGBoost) trains end-to-end; capability truthfulness.
- `python/tests/test_ml_leakage.py` — the leakage gate (Phase 13.3): overlapping
  labels purged, the independent gate rejects a hand-crafted overlap, future
  prices never enter earlier labels, preprocessing/final model fit on train only,
  train/test index disjointness, stale/duplicate reporting.
- `python/tests/test_ml_fabric.py` — background training through the Fabric
  completes; time budget enforced; cancellation reported without raising;
  oversized-dataset guardrail refuses.
- `python/tests/test_ml_acceptance.py` — the end-to-end acceptance scenario
  (Phase 18.4) over SYNTHETIC fixtures: train baseline + candidates, compare
  folds, register, verify hash, inference, reproduce, background step.
- `src/lib/ml-client.test.ts` — request shape + error path of the front door.

Run: `npm run test` (vitest + python) and `npx tsc --noEmit`.

## Roadmap (not implemented)

The remaining feature phases of the ML brief: Optuna hyperparameter search
(Phase 6), probability calibration and ensembles/stacking (Phase 7), SHAP
explainability (Phase 8), drift/decay monitoring (Phase 10), and the deep
backtester / Factor Lab runtime handoff with the full agent research workflow
(Phase 11). The contracts, store and workers were designed to accommodate them
without migration.

## Dependencies

The optional ML wheels are installed from `python/requirements-ml.txt`
(scikit-learn, LightGBM, XGBoost) into the runtime interpreter. They are NOT in
`python/requirements.txt`, so a default `npm install && npm run dev` stays
lightweight; when a wheel is absent its adapter reports an honest
`MODEL_UNAVAILABLE` rather than substituting a different model. SHAP and Optuna
(when their phases land) go in the same optional file.
