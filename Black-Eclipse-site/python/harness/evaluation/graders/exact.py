"""Exact / normalized / tolerant comparison grader.

Deterministic comparison for numbers, strings, JSON, structured output, IDs,
URLs and files: exact equality, normalized equality, numeric tolerance, subset
matching and schema validation. No model is consulted.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Optional

from . import GradeContext, Grader, GraderResult

try:  # jsonschema is optional; schema validation degrades honestly
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except Exception:  # noqa: BLE001
    _HAS_JSONSCHEMA = False


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().lower()
    return value


def _extract_number(text: str, *, percent_as_fraction: bool = False) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?%?", text)
    if not match:
        return None
    token = match.group(0)
    raw = token.rstrip("%").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    # A fraction expected (0.25) and the model wrote "25%" are the same number.
    # Without this, every weight/return task written as a percentage failed.
    if percent_as_fraction and token.endswith("%"):
        value /= 100.0
    return value


def _subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(_subset(e, a) for a in actual) for e in expected)
    return expected == actual


class ExactGrader(Grader):
    name = "exact"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = {**self.config, **(getattr(ctx.task, "constraints", {}) or {})}
        expected = getattr(ctx.task, "expected_output", None)
        actual = ctx.final_output or ""
        mode = config.get("mode", "auto")
        tolerance = float(config.get("tolerance", 0.0))

        if expected is None:
            return GraderResult.unmeasured_result(self.name, "task has no expected_output")

        if isinstance(expected, dict) and any(
            key in expected for key in ("equals", "contains", "regex", "numeric", "json", "schema", "keywords")
        ):
            return self._grade_spec(expected, actual, mode, tolerance)

        # A bare scalar/list/dict: compare directly.
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            return self._numeric(float(expected), actual, tolerance)
        if isinstance(expected, (dict, list)):
            return self._structured(expected, actual)
        return self._string(str(expected), actual, config)

    def _grade_spec(self, spec: dict[str, Any], actual: str, mode: str, tolerance: float) -> GraderResult:
        if "numeric" in spec:
            node = spec["numeric"]
            if isinstance(node, dict):
                value, tol = float(node.get("value")), float(node.get("tolerance", tolerance))
            else:
                value, tol = float(node), tolerance
            return self._numeric(value, actual, tol)
        if "equals" in spec:
            want = spec["equals"]
            if spec.get("normalize", mode == "normalized"):
                ok = _normalize(want) == _normalize(actual)
            else:
                ok = str(want) == actual
            return GraderResult(self.name, 1.0 if ok else 0.0, ok,
                                details={"mode": "equals"}, failures=[] if ok else [f"expected {want!r}"])
        if "contains" in spec:
            needles = spec["contains"]
            needles = [needles] if isinstance(needles, str) else list(needles)
            missing = [n for n in needles if str(n) not in actual]
            ok = not missing
            score = 1.0 - (len(missing) / len(needles)) if needles else 1.0
            return GraderResult(self.name, score, ok, details={"missing": missing},
                                failures=[f"missing {m!r}" for m in missing])
        if "regex" in spec:
            ok = re.search(spec["regex"], actual) is not None
            return GraderResult(self.name, 1.0 if ok else 0.0, ok, details={"regex": spec["regex"]})
        if "json" in spec:
            return self._structured(spec["json"], actual, subset=bool(spec.get("subset", True)))
        if "schema" in spec:
            return self._schema(spec["schema"], actual)
        if "keywords" in spec:
            words = spec["keywords"]
            hits = [w for w in words if w.lower() in actual.lower()]
            ok = len(hits) == len(words)
            score = len(hits) / len(words) if words else 1.0
            return GraderResult(self.name, score, ok, details={"hits": hits},
                                failures=[f"missing keyword {w!r}" for w in words if w not in hits])
        return GraderResult.unmeasured_result(self.name, "unrecognised exact spec")

    def _numeric(self, expected: float, actual_text: str, tolerance: float) -> GraderResult:
        actual = _extract_number(actual_text, percent_as_fraction=abs(expected) < 1.0)
        if actual is None:
            return GraderResult(self.name, 0.0, False, failures=["no numeric value found in output"])
        diff = abs(expected - actual)
        ok = diff <= tolerance if tolerance > 0 else math.isclose(expected, actual, rel_tol=1e-9)
        score = 1.0 if ok else max(0.0, 1.0 - diff / (abs(expected) or 1.0))
        return GraderResult(self.name, score, ok,
                            details={"expected": expected, "actual": actual, "diff": diff, "tolerance": tolerance},
                            failures=[] if ok else [f"expected {expected} ±{tolerance}, got {actual}"])

    def _structured(self, expected: Any, actual: str, *, subset: bool = True) -> GraderResult:
        try:
            parsed = json.loads(actual)
        except (ValueError, TypeError):
            return GraderResult(self.name, 0.0, False, failures=["output is not valid JSON"])
        ok = _subset(expected, parsed) if subset else expected == parsed
        return GraderResult(self.name, 1.0 if ok else 0.0, ok,
                            details={"expected": expected, "subset": subset},
                            failures=[] if ok else ["structured output did not match"])

    def _schema(self, schema: dict[str, Any], actual: str) -> GraderResult:
        if not _HAS_JSONSCHEMA:
            return GraderResult.unmeasured_result(self.name, "jsonschema not installed")
        try:
            parsed = json.loads(actual)
            jsonschema.validate(parsed, schema)
        except Exception as exc:  # noqa: BLE001
            return GraderResult(self.name, 0.0, False, failures=[f"schema: {exc}"])
        return GraderResult(self.name, 1.0, True, details={"schema": "valid"})

    def _string(self, expected: str, actual: str, config: dict[str, Any]) -> GraderResult:
        if config.get("normalize"):
            ok = _normalize(expected) == _normalize(actual)
        else:
            ok = expected.strip() == actual.strip()
        return GraderResult(self.name, 1.0 if ok else 0.0, ok,
                            failures=[] if ok else [f"expected {expected!r}"])
