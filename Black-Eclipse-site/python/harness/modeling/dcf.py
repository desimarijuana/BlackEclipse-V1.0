"""DCF composition over the existing deterministic valuation engine."""

from __future__ import annotations

from typing import Any

from ..finance_facts.valuation import (
    DcfInputs,
    WaccInputs,
    dcf_breakdown,
    dcf_sensitivity,
    wacc,
)
from .contracts import Check, ModelError, ModelResult, number, require
from .three_statement import build_three_statement


def _wacc_rate(assumptions: dict[str, Any]) -> float:
    block = assumptions.get("wacc")
    if not isinstance(block, dict):
        raise ModelError("INPUT_UNAVAILABLE", "assumptions.wacc is required for a DCF")
    inputs = WaccInputs(
        market_cap=number(require(block, "market_cap", "assumptions.wacc"), "wacc.market_cap"),
        total_debt=number(require(block, "total_debt", "assumptions.wacc"), "wacc.total_debt"),
        risk_free_rate=number(require(block, "risk_free_rate", "assumptions.wacc"), "wacc.risk_free_rate"),
        beta=number(require(block, "beta", "assumptions.wacc"), "wacc.beta"),
        equity_risk_premium=number(require(block, "equity_risk_premium", "assumptions.wacc"), "wacc.equity_risk_premium"),
        cost_of_debt=(number(block["cost_of_debt"], "wacc.cost_of_debt") if block.get("cost_of_debt") is not None else None),
        tax_rate=(number(block["tax_rate"], "wacc.tax_rate") if block.get("tax_rate") is not None else None),
        currency=block.get("currency"),
    )
    metric = wacc(inputs)
    return float(metric.value) / 100.0


def build_dcf(spec: dict[str, Any], statement: ModelResult | None = None) -> ModelResult:
    assumptions = spec.get("assumptions") or {}
    statement = statement or build_three_statement(spec)
    fcff = statement.meta.get("freeCashFlowToFirm") or []
    if not fcff:
        raise ModelError("INPUT_UNAVAILABLE", "the three-statement model produced no forecast free cash flow")
    rate = _wacc_rate(assumptions)
    if not (0.0 < rate < 1.0):
        raise ModelError("INPUT_INVALID", f"the computed WACC is outside (0, 1): {rate!r}")
    terminal_growth = assumptions.get("terminalGrowth", assumptions.get("terminal_growth"))
    exit_multiple = assumptions.get("exitMultiple", assumptions.get("exit_multiple"))
    terminal_metric = assumptions.get("terminalMetric", assumptions.get("terminal_metric"))
    if (terminal_growth is None) == (exit_multiple is None):
        raise ModelError("INPUT_INVALID", "a DCF needs exactly one of terminalGrowth or exitMultiple")
    net_debt = assumptions.get("netDebt", assumptions.get("net_debt"))
    if net_debt is None:
        latest = statement.meta.get("latestHistory") or {}
        net_debt = float(latest.get("debt", 0.0)) - float(latest.get("cash", 0.0))
    shares = assumptions.get("sharesOutstanding", assumptions.get("shares_outstanding"))
    if shares is None:
        shares = (statement.meta.get("latestHistory") or {}).get("shares")
    inputs = DcfInputs(
        free_cash_flows=tuple(float(value) for value in fcff),
        discount_rate=rate,
        terminal_growth=(float(terminal_growth) if terminal_growth is not None else None),
        exit_multiple=(float(exit_multiple) if exit_multiple is not None else None),
        terminal_metric=(float(terminal_metric) if terminal_metric is not None else None),
        net_debt=float(net_debt),
        shares_outstanding=(float(shares) if shares is not None else None),
        currency=spec["company"]["currency"],
        mid_year=bool(assumptions.get("midYear", assumptions.get("mid_year", False))),
    )
    breakdown = dcf_breakdown(inputs)

    result = ModelResult(
        kind="dcf",
        company=spec["company"]["name"],
        currency=spec["company"]["currency"],
        units=spec["company"]["units"],
        years=list(statement.years),
        assumptions=assumptions,
        meta={
            "engine": "dcf.v1",
            "wacc": rate,
            "enterpriseValue": breakdown.enterprise_value,
            "equityValue": breakdown.equity_value,
            "valuePerShare": breakdown.per_share,
            "terminalValue": breakdown.terminal_value,
            "terminalDescription": breakdown.terminal_desc,
            "midYear": inputs.mid_year,
            "freeCashFlows": list(breakdown.fcf),
            "netDebt": breakdown.net_debt,
            "sharesOutstanding": inputs.shares_outstanding,
        },
    )
    result.sections.update(statement.sections)
    result.checks.extend(statement.checks)
    result.warnings.extend(statement.warnings)
    if inputs.mid_year:
        result.warnings.append(
            "mid-year convention discounts explicit FCF at t+0.5; terminal value is discounted at n"
        )

    result.add_section(
        "DCF",
        columns=["Metric", "Value"],
        rows=[
            _metric("WACC", rate, "0.00%"),
            _metric("Terminal method", breakdown.terminal_desc, None),
            _metric("PV of explicit FCF", breakdown.pv_explicit, "number"),
            _metric("PV of terminal value", breakdown.pv_terminal, "number"),
            _metric("Enterprise value", breakdown.enterprise_value, "number"),
            _metric("Less: net debt", -breakdown.net_debt, "number"),
            _metric("Equity value", breakdown.equity_value, "number"),
            _metric("Shares outstanding", inputs.shares_outstanding, "number"),
            _metric("Value per share", breakdown.per_share, "number"),
        ],
    )
    result.add_section(
        "DCF Schedule",
        columns=["Period", "FCF", "Discount factor", "Present value"],
        rows=[
            {
                "label": f"Year {row['period']}",
                "values": [row["period"], row["freeCashFlow"], row["discountFactor"], row["presentValue"]],
                "kind": "calc",
            }
            for row in breakdown.schedule
        ],
    )

    try:
        sensitivity = dcf_sensitivity(inputs)
        detail = sensitivity.detail
        growths = detail.get("terminalGrowths") or []
        matrix = detail.get("enterpriseValue") or []
        rates = detail.get("discountRates") or []
        result.add_section(
            "DCF Sensitivity",
            columns=["WACC \\ g"] + [f"{value:.2%}" for value in growths],
            rows=[
                {
                    "label": f"{rate_value:.2%}",
                    "values": [rate_value] + [None if cell is None else cell for cell in row],
                    "kind": "calc",
                }
                for rate_value, row in zip(rates, matrix)
            ],
        )
    except Exception as exc:  # noqa: BLE001 - a sensitivity is additive to the base DCF
        result.warnings.append(f"DCF sensitivity unavailable: {exc}")

    tolerance = max(1e-6, abs(breakdown.enterprise_value) * 1e-9)
    result.checks.append(Check(
        "dcf_bridge_ties",
        "PASS" if abs((breakdown.pv_explicit + breakdown.pv_terminal) - breakdown.enterprise_value) <= tolerance else "FAIL",
        "enterprise value equals the sum of the explicit and terminal present values",
    ))
    result.checks.append(Check(
        "dcf_terminal_method",
        "PASS",
        breakdown.terminal_desc,
    ))
    if breakdown.per_share is not None:
        result.checks.append(Check(
            "dcf_per_share_positive",
            "PASS" if breakdown.per_share > 0 else "WARN",
            "a negative per-share value is possible when net debt exceeds enterprise value",
            value=breakdown.per_share,
        ))
    return result


def _metric(label: str, value: Any, kind: str | None) -> dict[str, Any]:
    return {"label": label, "values": [value], "kind": kind or "calc", "formulas": None}


__all__ = ["build_dcf"]
