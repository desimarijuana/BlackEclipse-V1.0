"""Contracts and validation for the financial modeling engine.

The model spec is deliberately boring: numbers, named assumptions, provenance
records and a closed kind. Every required input is named when it is missing; no
financial value is defaulted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

KINDS = ("three_statement", "dcf", "lbo", "comps", "integrated")
MAX_FORECAST_YEARS = 25
MAX_PEERS = 100


class ModelError(Exception):
    def __init__(self, code: str, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    value: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "value": self.value}


@dataclass
class ModelResult:
    kind: str
    company: str
    currency: str
    units: str
    years: list[str] = field(default_factory=list)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def add_section(self, name: str, *, columns: list[str], rows: list[dict[str, Any]]) -> None:
        self.sections[name] = {"columns": columns, "rows": rows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "company": self.company,
            "currency": self.currency,
            "units": self.units,
            "years": list(self.years),
            "sections": self.sections,
            "checks": [check.to_dict() for check in self.checks],
            "warnings": list(self.warnings),
            "assumptions": self.assumptions,
            "meta": self.meta,
        }

    def checks_pass(self) -> bool:
        return not any(check.status == "FAIL" for check in self.checks)


def number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ModelError("INPUT_INVALID", f"{label} must be a number, got {value!r}") from None
    if result != result or result in (float("inf"), float("-inf")):
        raise ModelError("INPUT_INVALID", f"{label} must be finite, got {value!r}")
    return result


def optional_number(value: Any, label: str) -> Optional[float]:
    if value is None:
        return None
    return number(value, label)


def numbers(value: Any, label: str, *, length: Optional[int] = None) -> list[float]:
    if value is None:
        raise ModelError("INPUT_UNAVAILABLE", f"{label} is required")
    if isinstance(value, (int, float)):
        result = [float(value)]
    elif isinstance(value, (list, tuple)):
        result = [number(item, f"{label}[{index}]") for index, item in enumerate(value)]
    else:
        raise ModelError("INPUT_INVALID", f"{label} must be a number or an array of numbers")
    if length is not None:
        if len(result) == 1:
            result = result * length
        if len(result) != length:
            raise ModelError("INPUT_INVALID", f"{label} must have {length} values, got {len(result)}")
    return result


def require(mapping: Any, key: str, label: str) -> Any:
    if not isinstance(mapping, dict):
        raise ModelError("INPUT_INVALID", f"{label} must be an object")
    if key not in mapping or mapping[key] is None:
        raise ModelError("INPUT_UNAVAILABLE", f"{label}.{key} is required")
    return mapping[key]


def _period_matches(period: str, year: str) -> bool:
    text = str(period or "").strip()
    return text == year or text.endswith(year) or text.replace("FY", "").strip() == year


def history_block(spec: dict[str, Any]) -> dict[str, Any]:
    history = spec.get("history")
    if not isinstance(history, dict):
        raise ModelError("INPUT_UNAVAILABLE", "history is required")
    years = [str(year) for year in (history.get("years") or [])]
    series: dict[str, list[float]] = {}
    raw_series = history.get("series") or {}
    if isinstance(raw_series, dict):
        for metric, values in raw_series.items():
            if isinstance(values, (list, tuple)):
                series[str(metric)] = [number(value, f"history.series.{metric}") for value in values]
            else:
                series[str(metric)] = [number(values, f"history.series.{metric}")]
    facts = history.get("facts") or []
    if isinstance(facts, list):
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            metric = str(fact.get("metric") or "").strip()
            if not metric:
                continue
            value = number(fact.get("value"), f"history.facts.{metric}")
            period = str(fact.get("period") or "").strip()
            if years:
                index = next((i for i, year in enumerate(years) if _period_matches(period, year)), None)
                if index is None:
                    continue
                existing = series.get(metric)
                if existing is None or len(existing) != len(years):
                    existing = [None] * len(years)  # type: ignore[list-item]
                existing[index] = value
                series[metric] = existing  # type: ignore[assignment]
            else:
                series[metric] = [value]
                years = [period or "latest"]
    if not years:
        years = ["latest"]
    for metric, values in list(series.items()):
        if len(values) != len(years):
            series[metric] = [values[-1]] if values else []
    return {"years": years, "series": series, "facts": facts}


def latest(history: dict[str, Any], metric: str, *, label: Optional[str] = None) -> float:
    values = history["series"].get(metric)
    if not values:
        raise ModelError("INPUT_UNAVAILABLE", f"history.{label or metric} is required")
    return float(values[-1])


def latest_optional(history: dict[str, Any], metric: str) -> Optional[float]:
    values = history["series"].get(metric)
    return float(values[-1]) if values else None


def normalize_spec(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ModelError("MODEL_INVALID", "the model spec must be an object")
    kind = str(payload.get("kind") or "").strip().casefold()
    if kind not in KINDS:
        raise ModelError("MODEL_KIND_UNSUPPORTED", f"kind must be one of {list(KINDS)}")
    company = payload.get("company") or {}
    if not isinstance(company, dict):
        raise ModelError("MODEL_INVALID", "company must be an object")
    spec: dict[str, Any] = {
        "kind": kind,
        "company": {
            "name": str(company.get("name") or "Unnamed company"),
            "ticker": str(company.get("ticker") or ""),
            "currency": str(company.get("currency") or "USD"),
            "units": str(company.get("units") or "millions"),
            "fiscalYearEnd": str(company.get("fiscalYearEnd") or "12-31"),
        },
    }
    if "history" in payload:
        spec["history"] = history_block(payload)
    if "assumptions" in payload:
        assumptions = payload.get("assumptions")
        if not isinstance(assumptions, dict):
            raise ModelError("MODEL_INVALID", "assumptions must be an object")
        spec["assumptions"] = assumptions
    for key in ("lbo", "comps", "scenarios", "outputs", "name"):
        if key in payload and payload[key] is not None:
            spec[key] = payload[key]
    return spec


def spec_hash(spec: dict[str, Any]) -> str:
    data = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


__all__ = [
    "Check",
    "KINDS",
    "MAX_FORECAST_YEARS",
    "MAX_PEERS",
    "ModelError",
    "ModelResult",
    "history_block",
    "latest",
    "latest_optional",
    "normalize_spec",
    "number",
    "numbers",
    "optional_number",
    "require",
    "spec_hash",
]
