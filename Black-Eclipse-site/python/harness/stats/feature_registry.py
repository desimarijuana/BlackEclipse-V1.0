"""Feature registry — versioned, validated, reusable feature definitions.

A feature is an immutable-versioned definition (a safe-language expression or a
multi-step pipeline) plus metadata. Versions are append-only: a rollback selects
an earlier version, it never erases history. Dependencies are tracked and
resolved recursively (a feature may reference another feature by name), with
cycle detection.

Validation and preview run the real evaluator, so a definition that "validates"
is one that actually executes on the supplied sample and reports its warm-up,
missingness and point-in-time safety.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .base import INVALID_INPUT, StatsError
from .formula import FUNCTIONS, FormulaError, evaluate, parse
from ..persistence import now_iso

_KNOWN_INPUTS = ("price", "close", "open", "high", "low", "volume", "returns", "benchmark")
_MAX_DEPTH = 8


def bump_semver(version: str, part: str = "patch") -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version.strip())
    if not m:
        raise StatsError(INVALID_INPUT, f"invalid semver: {version}")
    major, minor, patch = (int(x) for x in m.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "feature"
    return f"{base}-{uuid.uuid4().hex[:6]}"


@dataclass
class FeatureDefinition:
    expression: Optional[str] = None
    pipeline: Optional[list[dict]] = None
    param_schema: dict = field(default_factory=dict)
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    changelog: Optional[str] = None

    def steps(self) -> list[dict]:
        if self.pipeline:
            return list(self.pipeline)
        if self.expression:
            return [{"name": "__out__", "expression": self.expression}]
        raise StatsError(INVALID_INPUT, "a feature needs an expression or a pipeline")

    def output_name(self) -> str:
        steps = self.steps()
        return steps[-1]["name"]


def _collect_free_variables(definition: FeatureDefinition) -> list[str]:
    variables: set[str] = set()
    for step in definition.steps():
        parsed = parse(step.get("expression", ""))
        variables.update(parsed.variables)
    names = {s["name"] for s in definition.steps()}
    return sorted(v for v in variables if v not in names)


def _eval_definition(definition: FeatureDefinition, base: dict[str, Any],
                     store: "Any", *, depth: int, seen: list[str]) -> tuple[np.ndarray, list[str]]:
    if depth > _MAX_DEPTH:
        raise StatsError(INVALID_INPUT, "feature dependency depth exceeded (possible cycle)")
    context = dict(base)
    deps: list[str] = []
    steps = definition.steps()
    result: Optional[np.ndarray] = None
    for step in steps:
        expr = step.get("expression")
        if not expr:
            raise StatsError(INVALID_INPUT, f"pipeline step {step.get('name')!r} has no expression")
        parsed = parse(expr)
        # Resolve any free variable that names another registered feature.
        for var in parsed.variables:
            if var in context or var in _KNOWN_INPUTS:
                continue
            if var in seen:
                raise StatsError(INVALID_INPUT, f"dependency cycle involving feature {var!r}")
            if store is None:
                raise StatsError(INVALID_INPUT, f"unresolved variable {var!r} (no registry available)")
            dep = store.get_feature_by_name(var)
            if dep is None:
                raise StatsError(INVALID_INPUT, f"unknown variable {var!r} (no such input or feature)")
            dep_def = _definition_from_record(
                store.get_feature_version(dep["id"], dep["latestVersion"]))
            values, _ = _eval_definition(dep_def, base, store, depth=depth + 1, seen=[*seen, var])
            context[var] = values
            deps.append(var)
        result, _ = evaluate(expr, context)
        context[step["name"]] = result
    if result is None:
        raise StatsError(INVALID_INPUT, "feature pipeline produced no output")
    return result, deps


def _definition_from_record(record: dict) -> FeatureDefinition:
    return FeatureDefinition(
        expression=record.get("expression"),
        pipeline=record.get("pipeline"),
        param_schema=record.get("paramSchema") or {},
        input_schema=record.get("inputSchema") or {},
        output_schema=record.get("outputSchema") or {},
        changelog=record.get("changelog"),
    )


class FeatureRegistry:
    def __init__(self, store: Any) -> None:
        self._store = store

    # ── create / version ─────────────────────────────────────────────────────
    def save(self, *, name: str, definition: FeatureDefinition, description: Optional[str] = None,
             owner: Optional[str] = None, visibility: str = "personal", category: Optional[str] = None,
             tags: Optional[list[str]] = None, feature_id: Optional[str] = None,
             bump: str = "patch") -> dict:
        if visibility not in ("personal", "team", "public"):
            raise StatsError(INVALID_INPUT, "visibility must be personal, team or public")
        if not name.strip():
            raise StatsError(INVALID_INPUT, "feature name is required")
        self._assert_valid(definition)

        if feature_id:
            existing = self._store.get_feature(feature_id)
            if existing is None:
                raise StatsError(INVALID_INPUT, f"unknown feature {feature_id!r}", 404)
            version = bump_semver(existing["latestVersion"], bump)
        else:
            feature_id = _slug(name)
            version = "1.0.0"

        deps = _collect_free_variables(definition)
        self._store.add_feature_version(
            feature_id=feature_id, version=version, expression=definition.expression,
            pipeline=definition.pipeline, param_schema=definition.param_schema,
            input_schema=definition.input_schema, output_schema=definition.output_schema,
            dependencies=deps, changelog=definition.changelog, pit_safe=True,
        )
        feature = self._store.upsert_feature_metadata(
            feature_id=feature_id, name=name, description=description, owner=owner,
            visibility=visibility, category=category, tags=tags or [], latest_version=version,
        )
        self._store.audit(action="feature.save", subject_type="feature", subject_id=feature_id,
                          actor=owner, detail={"version": version})
        return feature

    def clone(self, feature_id: str, *, name: Optional[str] = None, owner: Optional[str] = None) -> dict:
        src = self._store.get_feature(feature_id)
        if src is None:
            raise StatsError(INVALID_INPUT, f"unknown feature {feature_id!r}", 404)
        version = self._store.get_feature_version(feature_id, src["latestVersion"])
        return self.save(name=name or f"{src['name']} (copy)",
                         definition=_definition_from_record(version), owner=owner or src["owner"],
                         visibility=src["visibility"], category=src["category"], tags=src["tags"])

    def rollback(self, feature_id: str, version: str) -> dict:
        feature = self._store.get_feature(feature_id)
        if feature is None:
            raise StatsError(INVALID_INPUT, f"unknown feature {feature_id!r}", 404)
        target = self._store.get_feature_version(feature_id, version)
        if target is None:
            raise StatsError(INVALID_INPUT, f"feature {feature_id!r} has no version {version}", 404)
        self._store._db.execute(
            "UPDATE StatsFeature SET latestVersion=?, updatedAt=? WHERE id=?",
            (version, now_iso(), feature_id))
        self._store._db.commit()
        self._store.audit(action="feature.rollback", subject_type="feature", subject_id=feature_id,
                          detail={"to": version})
        return self._store.get_feature(feature_id)

    # ── read ─────────────────────────────────────────────────────────────────
    def get(self, feature_id: str, version: Optional[str] = None) -> dict:
        feature = self._store.get_feature(feature_id)
        if feature is None:
            raise StatsError(INVALID_INPUT, f"unknown feature {feature_id!r}", 404)
        ver = version or feature["latestVersion"]
        record = self._store.get_feature_version(feature_id, ver)
        if record is None:
            raise StatsError(INVALID_INPUT, f"feature {feature_id!r} has no version {ver}", 404)
        return {"feature": feature, "version": record}

    def list(self, **kwargs: Any) -> list[dict]:
        return self._store.list_features(**kwargs)

    def versions(self, feature_id: str) -> list[dict]:
        return self._store.list_feature_versions(feature_id)

    def dependencies(self, feature_id: str, version: Optional[str] = None) -> dict:
        record = self.get(feature_id, version)["version"]
        direct = list(record.get("dependencies") or [])
        graph: dict[str, list[str]] = {feature_id: direct}
        seen = {feature_id}
        queue = list(direct)
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            dep = self._store.get_feature_by_name(name)
            if dep is None:
                continue
            dep_rec = self._store.get_feature_version(dep["id"], dep["latestVersion"])
            graph[name] = list((dep_rec or {}).get("dependencies") or [])
            queue.extend(graph[name])
        return {"root": feature_id, "direct": direct, "graph": graph}

    def compare(self, feature_id: str, version_a: str, version_b: str) -> dict:
        a = self._store.get_feature_version(feature_id, version_a)
        b = self._store.get_feature_version(feature_id, version_b)
        if a is None or b is None:
            raise StatsError(INVALID_INPUT, "both versions must exist", 404)
        return {
            "featureId": feature_id, "a": {"version": version_a, "definition": a},
            "b": {"version": version_b, "definition": b},
            "identical": a.get("definitionHash") == b.get("definitionHash"),
        }

    # ── validate / preview ───────────────────────────────────────────────────
    def _assert_valid(self, definition: FeatureDefinition) -> None:
        steps = definition.steps()
        if not steps:
            raise StatsError(INVALID_INPUT, "feature has no steps")
        for step in steps:
            if "expression" in step:
                parse(step["expression"])  # raises FormulaError on bad syntax / unknown functions
        names = [s.get("name") for s in steps]
        if len(names) != len(set(names)):
            raise StatsError(INVALID_INPUT, "duplicate step names in pipeline")

    def validate(self, *, feature_id: Optional[str] = None, definition: Optional[FeatureDefinition] = None,
                 version: Optional[str] = None, sample: Optional[dict] = None) -> dict:
        if definition is None:
            record = self.get(feature_id, version)  # type: ignore[arg-type]
            definition = _definition_from_record(record["version"])
            version = record["version"]["version"]
        checks: list[dict] = []
        status = "valid"

        try:
            self._assert_valid(definition)
            checks.append({"check": "syntax", "passed": True})
        except (StatsError, FormulaError) as exc:
            checks.append({"check": "syntax", "passed": False, "message": str(exc)})
            status = "invalid"
            self._record(feature_id, version, status, {"checks": checks})
            return {"status": status, "checks": checks}

        deps = _collect_free_variables(definition)
        has_data = sample is not None
        checks.append({"check": "inputs", "passed": True, "variables": deps})

        if has_data:
            base = _base_context(sample)
            try:
                series, resolved = _eval_definition(definition, base, self._store, depth=0,
                                                    seen=[feature_id] if feature_id else [])
                finite = series[np.isfinite(series)]
                checks.append({"check": "execution", "passed": True,
                               "finite": int(finite.size), "total": int(series.size)})
                checks.append({"check": "numerical", "passed": bool(finite.size > 0)})
                coverage = float(finite.size / series.size) if series.size else 0.0
                checks.append({"check": "coverage", "passed": coverage > 0,
                               "coverage": round(coverage, 4)})
                if finite.size < 2:
                    status = "warning"
            except (StatsError, FormulaError) as exc:
                checks.append({"check": "execution", "passed": False, "message": str(exc)})
                status = "invalid"
        else:
            checks.append({"check": "execution", "passed": None,
                           "message": "no sample data provided; execution not verified"})
            if status == "valid":
                status = "validated-static"

        self._record(feature_id, version, status, {"checks": checks})
        if feature_id:
            self._store.set_feature_validation(feature_id, status)
        return {"status": status, "checks": checks, "dependencies": deps}

    def _record(self, feature_id: Optional[str], version: Optional[str], status: str, detail: dict) -> None:
        if feature_id is None:
            return
        self._store.record_validation(feature_id=feature_id, version=version, status=status, detail=detail)

    def preview(self, *, feature_id: Optional[str] = None, definition: Optional[FeatureDefinition] = None,
                version: Optional[str] = None, sample: Optional[dict] = None) -> dict:
        if definition is None:
            record = self.get(feature_id, version)  # type: ignore[arg-type]
            definition = _definition_from_record(record["version"])
        if sample is None:
            raise StatsError(INVALID_INPUT, "preview requires sample data")
        base = _base_context(sample)
        try:
            series, resolved = _eval_definition(definition, base, self._store, depth=0,
                                                seen=[feature_id] if feature_id else [])
        except (StatsError, FormulaError) as exc:
            raise StatsError(INVALID_INPUT, f"preview failed: {exc}") from exc
        finite = series[np.isfinite(series)]
        return {
            "outputName": definition.output_name(),
            "values": [None if not np.isfinite(v) else float(v) for v in series],
            "summary": {
                "observations": int(series.size),
                "finite": int(finite.size),
                "missingCount": int(np.isnan(series).sum()),
                "coverage": round(float(finite.size / series.size), 4) if series.size else 0.0,
                "mean": float(finite.mean()) if finite.size else None,
                "std": float(finite.std(ddof=1)) if finite.size > 1 else None,
                "min": float(finite.min()) if finite.size else None,
                "max": float(finite.max()) if finite.size else None,
            },
            "resolvedDependencies": resolved,
        }


def _base_context(sample: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key, value in sample.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)) or isinstance(value, np.ndarray):
            arr = np.asarray(value, dtype=float)
            if arr.ndim == 1:
                context[key] = np.where(np.isfinite(arr), arr, np.nan)
    if "close" not in context and "price" in context:
        context["close"] = context["price"]
    if "price" not in context and "close" in context:
        context["price"] = context["close"]
    if "close" in context and "returns" not in context:
        close = context["close"]
        r = np.full(close.size, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            r[1:] = close[1:] / close[:-1] - 1.0
        context["returns"] = r
    return context


__all__ = ["FeatureRegistry", "FeatureDefinition", "bump_semver"]
