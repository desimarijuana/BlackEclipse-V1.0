---
title: ML Research Lab — Architecture and Operations
status: Current
last-verified: 2026-11-03
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
| Dataset build | `DatasetSpec` → immutable manifest + arrays | `source` (`market`/`records`), symbols, interval, feature names, `TargetSpec`, missing policy |
| Label | `TargetSpec` → label matrix + `labelStart`/`labelEnd` | start = t, end = t+horizon; the basis of purging (a `column` label spans only its own row) |
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

A dataset version declares its `source`:

| Source | What it is | How rows are supplied |
|---|---|---|
| `market` | Price/volume series resolved through the gateway | `symbols` + `interval`; features are the built-in or registered price features |
| `records` | Any tabular data the operator has (an uploaded CSV) | `records` (one object per row) + `featureNames` naming its numeric columns |

Both sources end in the SAME contract — `DatasetSpec → manifest + arrays + dataHash + quality report` — and both feed the same chronological split engine, so the leakage gate applies unchanged.

A `records` dataset uses the `column` target kind: `target.column` names the label column and `target.task` (`regression` or `classification`) says how it is modelled. Classification labels are coded in **sorted** order and the mapping is stored as `manifest.target.classLabels`, so a prediction decodes back to the operator's own vocabulary. There is no forward horizon: a row's label interval is the row itself.

Honest failure rules for `records` (never a silent coercion):

- a non-numeric value in a feature column → `INVALID_INPUT` naming the column and row;
- a non-numeric value in a numeric (`regression`) label → the same, with the hint to use `task="classification"`;
- a `timeColumn` that is not sorted ascending → refused, because rows are never re-sorted silently under a chronological split design;
- a classification label with fewer than two classes → `INSUFFICIENT_DATA`;
- the market-only forward-return kinds on a records source → refused (they need a price panel).

A `market` dataset is resolved ONLY through `stats.datasets.resolve_frame(gateway, …)` — the
same Market Data Gateway the stats/quant/factors engines use. The ML engine never
contacts a provider directly and never fills a missing observation with an
invented value. Each dataset version records: source, symbols, interval, window,
feature names, target spec, missing policy, coverage, quality report, timestamp
range and a content `dataHash`; the full matrix is stored as a gzipped artifact.

Built-in features (`datasets.BUILTIN_FEATURES`): `ret_1`, `ret_5`, `ret_21`,
`mom_63`, `vol_21`, `volume_z_21`. A feature named `feature:<name>` is evaluated
against the shared Feature Registry (`stats.feature_registry`), so Factor Lab and
ML Lab consume the same registered definitions.

## Unsupervised tasks

`clustering` and `anomaly` are label-free. A dataset declares them as
`target.kind="unsupervised"` with `target.task` naming the task; there is no
target column, `arrays.y` is all-NaN, and the quality report measures **feature**
coverage instead of label coverage (it must not report "0% of rows have a valid
target" — there is no target).

The invariants do not relax:

- the SAME chronological / walk-forward folds are built and the independent
  `assert_no_leakage` gate still runs;
- every reported metric is **out-of-sample** — the model is fitted on the fold's
  training rows only and scored on its test rows;
- feature selection is refused (`selection.method` must be `none`), because every
  selection method needs a label;
- a metric that is mathematically undefined is `null`: `silhouette` returns
  `None` when a fold's prediction has fewer than two clusters or a singleton
  cluster, and anomaly detection reports a rate and score distribution — never an
  "accuracy" it cannot know;
- the standardiser is fitted on training rows only, exactly as in the supervised
  path.

| Task | Family | What is fit | What is reported |
|---|---|---|---|
| `clustering` | `kmeans` (`nClusters`, `maxIter`, `tol`, `seed`) | centroids via seeded k-means++ | `silhouette`, `inertia`, `nClusters`, `clusterSizes` |
| `anomaly` | `mad_z` (`contamination`) | per-feature median/MAD + a training-score quantile | `anomalyRate`, `flagged`, `scoreMean`, `scoreP95`, `targetRate` |

`silhouette` is O(n²): above 4000 rows it uses a deterministic stride subsample
(never a random one, so the same data yields the same number). The anomaly
threshold comes from the TRAINING score quantile, so the rate reported on a later
fold is a real out-of-sample rate rather than the one it was tuned to.

## Recipe planner

`POST /ml/v1/plan` (agent tool `ml_plan_model`) turns a data profile — a built
dataset version, or inline `rows`/`features`/`task` — into a **plan**: model
family, hyperparameters, split design and feature-selection choice, each with the
reason it was chosen, plus warnings. It returns the exact
`/ml/v1/experiments` body, so planning and running cannot drift apart.

What it will not do, by construction:

- **plan an unavailable family** — the choice comes from the runtime's own
  `model_capabilities()`, so `torch_mlp` is only proposed when torch imports;
- **claim a metric** — a plan is a proposal; only a run reports numbers;
- **vary run to run** — the same profile and preference yield the same plan (no
  model call, no randomness), which is what makes it reviewable in a PR or a chat.

The policy is deliberately small: an interpretable linear model below 2 000 rows,
a boosted/ensemble tree above it, `kmeans`/`mad_z` for the label-free tasks, and
`preference: "deep"` only plans `torch_mlp` when it is installed (otherwise it
says so as a warning rather than silently choosing something else). The ML Lab's
"Suggest a model" button is the same endpoint, filling the experiment form.

## Model arena

`POST /ml/v1/compare` (agent tool `ml_compare_models`) trains up to six families on
ONE dataset version with the caller's exact split spec, seed and selection
config, then returns a table and a verdict. Every family is a normal persisted
run, so the arena never invents a second training path.

The verdict refuses the three ways a comparison normally lies:

- **no zero for a missing metric** — a `null` (or an incompatible family) is
  listed under `unmeasured` and excluded from the ranking, never sorted as 0;
- **no winner inside the noise** — if the top two are closer than the larger of
  their fold standard deviations, the note says "no clear winner" and `winner` is
  `null`;
- **no ranking without ground truth** — `anomaly` returns the table with a note
  that nothing can be "better", and `clustering` ranks only by silhouette.

Each run reports the same folds, because the split spec is copied into every
call; a comparison cannot be won by an easier validation design.

## Calibration and drift

Two questions decide whether a model can be trusted after it trains.

**Are the probabilities real?** `ExperimentConfig.calibration` (payload field
`calibration`) accepts `none`, `platt` or `isotonic`. The curve is fitted on the
**pooled out-of-fold** predictions — every row was scored by a model that never
saw it — so the final holdout is used only to REPORT the effect
(`finalCalibratedEvaluation`, plus the before/after Brier and log-loss on the OOF
rows). The curve travels with the artifact and `predict_proba` returns calibrated
scores. Binary classification only: a multiclass curve is a different design and
is not claimed; the fit returns `None` rather than an identity when the data is
too small or the labels are not binary.

**Has the world moved?** `POST /ml/v1/models/{id}/drift` (tool `ml_model_drift`)
compares the dataset version the model was trained on with a later one, per
feature: PSI (population stability index under the reference's own quantiles) and
a two-sample KS statistic with its asymptotic p-value. The verdict is
`stable` < 0.10 ≤ `watch` < 0.25 ≤ `drift`, and a feature present on only one side
is a `schema_change`, never a zero. Nothing is imputed and no model is called —
a drift verdict means the inputs moved, not that the model is wrong.

## Explainability and export

`finalPermutationImportance` explains EVERY family, not just the trees that
expose a split-based importance: on the final holdout, each selected feature is
shuffled five times (seeded) and the drop in accuracy (classification) or
negative RMSE (regression) is averaged, with its standard deviation. It is
`None` below 30 holdout rows — an importance from a toy sample would be noise
wearing a number. This is a model-agnostic attribution, deliberately NOT SHAP
values.

`GET /ml/v1/datasets/{id}/versions/{v}/export?format=csv|jsonl&limit=` returns
the version as portable text: features, the target, its human labels when the
target is a `column`, and the row timestamps — read from the stored artifact, not
re-derived. The export is bounded and says `truncated` when the limit bit.

## Hyperparameter search

`POST /ml/v1/search` (tool `ml_search_hyperparameters`) runs up to 24 trials of ONE
family over a declared grid — or a seeded random sample of it — every trial
validated on the caller's exact split spec and persisted as a normal run. Each
native family has a small documented default space (`DEFAULT_SPACES`), and an
optional family takes the caller's explicit grid.

The ranking is the arena's, so the same rules apply (an unmeasured trial cannot
win). Two search-specific honesty rules:

- the **top-ranked config is always reported** as the empirical best, with
  `withinNoise` saying whether it is actually separable from the runner-up;
- the note always states that the winner was **selected on the same folds it is
  scored on**, so its score is optimistic — a fresh-period confirmation is the
  next step, and no search result is presented as a generalization estimate.

`maxTrials` and `maxSeconds` bound the run; `stoppedReason` says which bound hit.

## Ensembles

`POST /ml/v1/ensembles` (tool `ml_create_ensemble`) registers a model whose artifact
is a **composition**: the member ids/versions plus one rule. Nothing is re-fitted,
which is what keeps it auditable and cheap.

- Members must share one **task** and one **dataset version** — different folds or
  datasets are refused, because their out-of-fold rows would not be comparable.
  Their row indices are intersected before blending.
- Classification averages member **probabilities** and takes the argmax; a member
  without probabilities falls back to a **majority vote**, with a tie resolved to
  the lowest class code (deterministic, stated).
- The ensemble's metrics are computed on the members' own out-of-fold outcomes, so
  the score is measured, not inherited. The result says plainly that a mean of
  predictions adds no information beyond its members.
- `ml_predict` accepts a **model name** as well as an id, so chat can say "predict
  with the committee model".

## Model adapters

| Family | Tier | Tasks | Serialisation |
|---|---|---|---|
| `dummy` | native (NumPy) | classification, regression | JSON |
| `ridge` | native (NumPy) | regression | JSON |
| `logistic` | native (NumPy) | classification | JSON |
| `random_forest` | native (NumPy CART + bagging) | classification, regression | JSON |
| `kmeans` | native (NumPy, seeded k-means++) | clustering | JSON (centroids) |
| `mad_z` | native (NumPy median/MAD) | anomaly | JSON (median, scale, threshold) |
| `torch_mlp` | optional (`python/requirements-train.txt`) | classification, regression | JSON (weight lists) |
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

`GET capabilities` · `GET/POST datasets` · `POST plan` · `POST compare` · `POST search` ·
`GET datasets/{id}/versions[/{v}]` · `GET datasets/{id}/versions/{v}/export` ·
`GET/POST experiments` · `GET experiments/{id}/runs` · `GET runs/{id}` ·
`POST runs/{id}/reproduce` · `GET models` · `POST models/register` ·
`GET models/{id}` · `POST models/{id}/transition` · `GET models/{id}/verify` ·
`POST models/{id}/drift` · `POST ensembles` · `POST models/{id}/predict`.

Agent tools (`ML_TOOLS`, 20): `ml_list_datasets`, `ml_list_features`,
`ml_build_dataset`, `ml_plan_model`, `ml_run_experiment`, `ml_compare_models`,
`ml_search_hyperparameters`, `ml_get_run`, `ml_list_experiments`,
`ml_reproduce_run`, `ml_register_model`, `ml_create_ensemble`, `ml_list_models`,
`ml_verify_model`, `ml_model_drift`, `ml_predict`, `ml_model_capabilities`,
`ml_job_status`, `ml_list_jobs`, `ml_cancel_job`. `ML_TOOLS` is imported by
`agents.py` and spread into the `ECLIPSE_AGENT` allowlist, and the chat system
prompt now names this workflow, so the agent composes it instead of leaving the
tools unused.

## UI

The ML Lab is an SPA tab (`ml-lab`) rendered by
`src/components/screens/ml-lab/ml-lab-screen.tsx` via the shell
(`stock-chat.tsx`), and reachable from the command palette (`page-ml-lab` in
`src/lib/search/registry.ts`). Tabs: Overview (real capabilities + counts),
Datasets (build + quality + versions), Experiments (train + folds + feature
importance + reproduce + register), Model Registry (verify + lifecycle). Every
page has loading / empty / populated / error states backed by real endpoints.

The Datasets tab builds either source: `Market data` (symbols + features +
target kind) or `Uploaded table (CSV)` — the file is parsed in the browser with
the shared dependency-free parser, its columns become the feature/target
choices, and the rows go to `/api/ml/datasets` as `source: "records"`. The
column names are lower-cased by that parser, and the table keeps its file order
(the form says so): the chronological split design reads it in that order, and
the backend refuses an unsorted declared time column rather than re-sorting it.

The Experiments tab has a **Suggest a model** button that calls `POST /ml/v1/plan`
for the selected dataset and fills the family, hyperparameters, split and
selection fields from the plan, showing its first rationale line and any
warnings. It never trains on its own.

**Compare families** runs `POST /ml/v1/compare` over the available families that
support the dataset's task (up to four) with the form's split spec, and renders
the ranking with each metric's fold standard deviation, the not-ranked list and
the verdict note.

A built dataset version has **Export CSV** / **Export JSONL** buttons: the file is
fetched through the same proxy as a text payload and downloaded in the browser,
with the truncation state shown when the row limit is reached.

**Tune {family}** runs `POST /ml/v1/search` over that family's default grid (six
trials at most from the UI) and shows the best metric, the winning
hyperparameters and the search note — including the "selected on the same folds"
caveat.

Both sources offer the label-free tasks too: the target-kind select (market) and
the task select (records) include `clustering` and `anomaly`, which send
`target.kind: "unsupervised"` and hide the target-column choice.

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
- `python/tests/test_ml_unsupervised.py` — clustering/anomaly: deterministic
  k-means and artifact round-trip, an anomaly model flagging unseen outliers,
  silhouette semantics (including `None` for one cluster), a label-free records
  dataset, and out-of-sample experiment runs for both tasks.
- `python/tests/test_ml_records_source.py` — the `records` source: manifest
  provenance, sorted class labels, regression vs classification labels, and an
  honest refusal for a non-numeric cell, an unsorted time column, a single-class
  label, a market-only target kind, or an unknown source; plus the full service
  path (payload → immutable version → experiment → registry).
- `python/tests/test_ml_recipes.py` — the planner: determinism, small/large data
  policy, never planning an unavailable family, honest deep-preference warnings,
  unsupervised plans, and the service path (build a version → plan against it).
- `python/tests/test_ml_torch_adapter.py` — the optional deep adapter: it reports
  its real availability, fails with `MODEL_UNAVAILABLE` when torch is absent, and
  (when installed) trains, serializes as JSON weights and reloads identically.
- `python/tests/test_ml_compare.py` — the arena: best measured family wins, a null
  metric is excluded (never zero), a failed run cannot be ranked, a margin inside
  fold noise is not a win, anomaly is never ranked, and the same folds are proven
  across families through the real service.
- `python/tests/test_ml_calibration_drift.py` — Platt pulls over-confident scores
  to the observed rate and lowers the Brier score, isotonic stays monotone and
  bounded, the fit declines (None) instead of faking an identity, PSI/KS behave on
  identical and shifted samples, a missing feature is a schema change, and the
  service round-trip proves a calibrated run predicts with its curve while drift
  on the training version stays `stable`.
- `python/tests/test_ml_importance_export.py` — permutation importance ranks a real
  feature above noise and is deterministic, a tiny holdout gets `None`, CSV/JSONL
  exports carry labels and timestamps, a limit truncates loudly, and an unknown
  format is refused.
- `python/tests/test_ml_search.py` — the trial planner (stable cartesian product,
  seeded unique sampling, default spaces, the 24-trial cap) and the service path
  (every trial runs, the best config is named, a within-noise winner is flagged,
  and the "selected on the same folds" caveat is always present).
- `python/tests/test_ml_ensemble.py` — the blend rules (mean, probability average,
  majority vote with a deterministic tie), the row alignment (shared rows only, an
  empty intersection refused), and the service path: two members registered, an
  ensemble created and predicted by NAME with a blend that matches the members'
  mean; plus refusals for mixed datasets and a single member.
- `src/lib/ml-client.test.ts` — request shape + error path of the front door.

Run: `npm run test` (vitest + python) and `npx tsc --noEmit`.

## Roadmap (not implemented)

Deep learning is intentionally narrow: `torch_mlp` is a tabular network. Image
and sequence adapters (CNN/GRU/transformer) are NOT implemented, because the ML
Lab has no image or sequence dataset path yet — a family would have nothing
honest to train on.

The remaining feature phases of the ML brief: ensembles/stacking (Phase 7 —
probability calibration HAS landed), SHAP values (Phase 8 — model-agnostic
permutation importance HAS landed), and the deep backtester / Factor Lab runtime
handoff with the full agent research workflow (Phase 11). Hyperparameter search
(Phase 6) has landed as a dependency-free grid/random search, and drift/decay
monitoring (Phase 10) as the PSI/KS report. The contracts, store and workers were
designed to accommodate the rest without migration.

## Dependencies

The optional ML wheels are installed from `python/requirements-ml.txt`
(scikit-learn, LightGBM, XGBoost) into the runtime interpreter. They are NOT in
`python/requirements.txt`, so a default `npm install && npm run dev` stays
lightweight; when a wheel is absent its adapter reports an honest
`MODEL_UNAVAILABLE` rather than substituting a different model. SHAP and Optuna
(when their phases land) go in the same optional file.

Deep learning is a SECOND, deliberately separate opt-in:
`python/requirements-train.txt` adds `torch` for the `torch_mlp` adapter only
(tabular classification/regression; no image or sequence data path exists, so no
CNN/RNN is claimed). Torch is hundreds of megabytes, so it never ships by default.
