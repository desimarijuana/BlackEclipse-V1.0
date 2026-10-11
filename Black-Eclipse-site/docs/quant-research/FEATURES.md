# Feature Registry & Versioning

> `last-verified: 2026-10-10`
> Code: `python/harness/stats/feature_registry.py` (`FeatureRegistry`,
> `FeatureDefinition`), persistence in `store.py`.

A **feature** is an immutable-versioned definition plus metadata:
id, name, description, owner, visibility (personal/team/public), category, tags,
latest version, validation status, and per-version definition, dependency list,
point-in-time-safety flag and definition hash.

## Definition

A feature is defined by either:

- **`expression`** — a safe-formula string (see `FORMULA_LANGUAGE.md`), or
- **`pipeline`** — an ordered list of steps, each `{name, expression}`; steps
  execute in order, each producing a variable, and the **last step's name is the
  output** (e.g. build `ret`, then `vol = rolling_std(ret, 5)`).

## Immutable versions

Versions are semver (`1.0.0`). `save(... feature_id=...)` appends a new version
(`bump` = patch/minor/major); the old version is never modified. **`rollback`**
points `latestVersion` at an earlier version — it selects history, it does not
erase it. `compare(a, b)` reports whether two versions are semantically identical
(same definition hash). `clone` forks a feature at `1.0.0`.

## Dependencies

Free variables in an expression that are not base inputs (`close`, `returns`,
`high`, `low`, `volume`, `benchmark`, …) are treated as **other registered
features by name** and resolved recursively. `dependencies(id)` returns the
direct list and the full graph. A reference cycle is detected and rejected.

## Validation & preview

Both run the **real evaluator** on supplied sample data:

- `validate` runs checks: syntax, inputs, execution, numerical finiteness,
  coverage; returns `valid` / `warning` / `invalid` / `validated-static`, and
  records a validation run. A successful calculation is **not** a claim of
  predictive value — that is a separate evaluation.
- `preview` returns the computed series plus summary (observations, finite,
  missing count, coverage, mean/std/min/max) and the resolved dependency list.

## Persistence

Tables `StatsFeature` and `StatsFeatureVersion` on `agent-memory.db`. Every save
and rollback writes an audit event. Validation runs land in `StatsValidation`.
