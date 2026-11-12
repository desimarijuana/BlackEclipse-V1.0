"""C8 conformance runner + manifest verification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .cases import CASES, CaseResult

_ROOT = Path(__file__).resolve().parents[4]
MANIFEST = _ROOT / "docs" / "harness" / "conformance.json"


@dataclass
class SuiteResult:
    cases: list[CaseResult] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra and all(case.ok for case in self.cases)

    @property
    def failed(self) -> list[CaseResult]:
        return [case for case in self.cases if not case.ok]

    def to_dict(self) -> dict[str, Any]:
        cases = [case.to_dict() for case in self.cases]
        return {
            "ok": self.ok,
            "total": len(cases),
            "passed": len([c for c in cases if c["ok"]]),
            "failed": len([c for c in cases if not c["ok"]]),
            "missing": self.missing,
            "extra": self.extra,
            "cases": cases,
        }


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {"version": 1, "cases": []}
    if not isinstance(data, dict):
        raise ValueError("conformance.json must be an object")
    return data


def run_conformance(
    *, only: Iterable[str] = (), quick: bool = False,
    factories: tuple[Callable[[], CaseResult], ...] = CASES,
    manifest_path: Path = MANIFEST,
) -> SuiteResult:
    wanted = {str(item) for item in only if item}
    manifest = load_manifest(manifest_path)
    declared = [str(case.get("id")) for case in manifest.get("cases") or [] if case.get("id")]
    selected = [
        factory for factory in factories
        if not wanted or getattr(factory, "__name__", "") in wanted
        or getattr(factory, "__name__", "").replace("_", ".") in wanted
    ]
    results: list[CaseResult] = []
    for factory in selected:
        name = factory.__name__
        if quick and name in ("contract_tool_manifest",):
            continue
        try:
            results.append(factory())
        except Exception as exc:  # noqa: BLE001 - a crashing case is a failed case
            results.append(CaseResult(name, "unknown", False, f"crashed: {exc}"))

    # Manifest ids are written with dots (fault.retry_429); map case function
    # names back to their declared ids for set comparison.
    result_ids = {case.id for case in results}
    missing = sorted(set(declared) - result_ids) if not wanted else []
    extra = sorted(result_ids - set(declared)) if not wanted and declared else []
    return SuiteResult(cases=results, missing=missing, extra=extra)


__all__ = ["MANIFEST", "SuiteResult", "load_manifest", "run_conformance"]
