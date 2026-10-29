"""Model dispatcher: one validated spec in, one checked result out."""

from __future__ import annotations

from typing import Any

from .comps import build_comps
from .contracts import ModelError, ModelResult, normalize_spec, spec_hash
from .dcf import build_dcf
from .lbo import build_lbo
from .three_statement import build_three_statement


def _merge_statements(base: ModelResult, extra: ModelResult, *, include_statement_sections: bool = False) -> None:
    for name, section in extra.sections.items():
        if include_statement_sections or name not in base.sections:
            base.sections[name] = section
    existing_checks = {(check.name, check.detail, check.value) for check in base.checks}
    for check in extra.checks:
        key = (check.name, check.detail, check.value)
        if key not in existing_checks:
            base.checks.append(check)
            existing_checks.add(key)
    existing_warnings = set(base.warnings)
    for warning in extra.warnings:
        if warning not in existing_warnings:
            base.warnings.append(warning)
            existing_warnings.add(warning)
    for key, value in extra.meta.items():
        if key in ("kind", "company", "specHash", "engine"):
            continue
        base.meta.setdefault(key, value)


def _dcf_requested(spec: dict[str, Any]) -> bool:
    assumptions = spec.get("assumptions") if isinstance(spec.get("assumptions"), dict) else {}
    dcf = spec.get("dcf") if isinstance(spec.get("dcf"), dict) else {}
    return bool(
        assumptions.get("wacc")
        or assumptions.get("waccInputs")
        or assumptions.get("wacc_inputs")
        or dcf.get("wacc")
        or dcf.get("waccInputs")
        or dcf.get("wacc_inputs")
    )


def build_model(payload: Any) -> ModelResult:
    spec = normalize_spec(payload)
    kind = spec["kind"]
    statement: ModelResult | None = None
    lbo_block = spec.get("lbo") if isinstance(spec.get("lbo"), dict) else {}
    explicit_lbo_projection = lbo_block.get("ebitdaProjection") or lbo_block.get("ebitda_projection")
    needs_statement = (
        kind in ("three_statement", "dcf", "integrated")
        or (kind == "lbo" and not explicit_lbo_projection)
    )
    if needs_statement:
        statement = build_three_statement(spec)

    if kind == "three_statement":
        result = statement
    elif kind == "dcf":
        assert statement is not None
        result = build_dcf(spec, statement)
    elif kind == "lbo":
        result = build_lbo(spec, statement)
    elif kind == "comps":
        result = build_comps(spec)
    else:
        assert statement is not None
        result = statement
        result.kind = "integrated"
        if _dcf_requested(spec):
            dcf = build_dcf(spec, statement)
            _merge_statements(result, dcf)
        else:
            result.warnings.append(
                "DCF was not built: the spec has no assumptions.wacc (or dcf.wacc) block"
            )
        if spec.get("lbo"):
            lbo = build_lbo(spec, statement)
            _merge_statements(result, lbo)
        if spec.get("comps"):
            comps = build_comps(spec)
            _merge_statements(result, comps)

    result.meta["specHash"] = spec_hash(spec)
    result.meta["kind"] = kind
    result.meta["company"] = spec["company"]
    result.meta["checksPass"] = result.checks_pass()
    return result


def build_summary(result: ModelResult) -> dict[str, Any]:
    failures = [check.to_dict() for check in result.checks if check.status == "FAIL"]
    warnings = [check.to_dict() for check in result.checks if check.status == "WARN"]
    return {
        "kind": result.kind,
        "company": result.company,
        "currency": result.currency,
        "units": result.units,
        "years": result.years,
        "checksPass": result.checks_pass(),
        "failures": failures,
        "warnings": warnings + [{"name": "note", "status": "WARN", "detail": warning} for warning in result.warnings],
        "keyMetrics": {
            key: result.meta.get(key)
            for key in ("enterpriseValue", "equityValue", "valuePerShare", "irr", "moic", "wacc")
            if result.meta.get(key) is not None
        },
    }


__all__ = ["build_model", "build_summary"]
