"""Financial-calculation grader.

Never relies on an LLM judge for a calculation. The grader INDEPENDENTLY computes
the expected value from the task's declared inputs (via ``harness.research.calculations``
and closed-form ratios) and compares it to the number the agent produced, within a
declared numeric tolerance.

The task config (``graders[].config`` or ``metadata.financial``) names the metric,
its inputs and the tolerance::

    {"metric": "sharpe",
     "inputs": {"observations": [...], "risk_free_rate": 0.02, "frequency": "daily"},
     "tolerance": 1e-3}
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import GradeContext, Grader, GraderResult


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
    if percent_as_fraction and token.endswith("%"):
        value /= 100.0
    return value


def _pct(value: Optional[float]) -> Optional[float]:
    return None if value is None else value


def _simple(metric: str, inputs: dict[str, Any]) -> Optional[float]:
    """Closed-form business ratios (percent where the name says margin/growth)."""
    g = inputs.get
    if metric in ("percentage_change", "return", "period_return"):
        start, end = g("start"), g("end")
        if start in (None, 0) or end is None:
            return None
        return (end - start) / abs(start) * 100.0
    if metric in ("gross_margin", "net_margin", "operating_margin", "margin"):
        num = g("gross_profit") if metric == "gross_margin" else (
            g("net_income") if metric == "net_margin" else g("operating_income", g("net_income"))
        )
        revenue = g("revenue")
        if revenue in (None, 0) or num is None:
            return None
        return num / revenue * 100.0
    if metric == "eps":
        ni, shares = g("net_income"), g("shares")
        if shares in (None, 0) or ni is None:
            return None
        return ni / shares
    if metric == "pe":
        price, eps = g("price"), g("eps")
        if eps in (None, 0) or price is None:
            return None
        return price / eps
    if metric == "ps":
        price, sps = g("price"), g("sales_per_share")
        if sps in (None, 0) or price is None:
            return None
        return price / sps
    if metric == "ev_ebitda":
        ev, ebitda = g("ev"), g("ebitda")
        if ebitda in (None, 0) or ev is None:
            return None
        return ev / ebitda
    if metric == "fcf":
        ocf, capex = g("operating_cash_flow"), g("capex", 0.0)
        if ocf is None:
            return None
        return ocf - (capex or 0.0)
    if metric == "cagr":
        start, end, years = g("start"), g("end"), g("years")
        if not all(v is not None for v in (start, end, years)) or start <= 0 or end <= 0 or years <= 0:
            return None
        return ((end / start) ** (1.0 / years) - 1.0) * 100.0
    if metric in ("portfolio_weights", "weight"):
        value, total = g("value"), g("total")
        if total in (None, 0) or value is None:
            return None
        return value / total
    if metric in ("position_size", "risk_reward", "risk_reward_ratio"):
        risk, reward = g("risk"), g("reward")
        if risk in (None, 0) or reward is None:
            return None
        return reward / abs(risk)
    return None


def compute_expected(metric: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Independently compute the expected value. Returns ``{"value", "source"}``.

    ``value`` is ``None`` when the metric is unknown or the inputs are
    insufficient — the caller then reports UNKNOWN rather than a fabricated
    number.
    """
    from ...research import calculations  # noqa: PLC0415

    direct = _simple(metric, inputs)
    if direct is not None or metric in {
        "percentage_change", "return", "period_return", "gross_margin", "net_margin",
        "operating_margin", "margin", "eps", "pe", "ps", "ev_ebitda", "fcf", "cagr",
        "portfolio_weights", "weight", "position_size", "risk_reward", "risk_reward_ratio",
    }:
        return {"value": direct, "source": "closed_form"}

    obs = inputs.get("observations")
    try:
        if metric in ("volatility", "annualized_volatility"):
            return {"value": calculations.annualized_volatility(
                obs, frequency=inputs.get("frequency", "daily"),
                method=inputs.get("method", "simple")).value, "source": "calculations"}
        if metric in ("max_drawdown", "drawdown"):
            return {"value": calculations.max_drawdown(obs).value, "source": "calculations"}
        if metric == "sharpe":
            return {"value": calculations.sharpe(
                obs, risk_free_rate=float(inputs["risk_free_rate"]),
                frequency=inputs.get("frequency", "daily")).value, "source": "calculations"}
        if metric == "sortino":
            return {"value": calculations.sortino(
                obs, risk_free_rate=float(inputs.get("risk_free_rate", 0.0)),
                frequency=inputs.get("frequency", "daily"),
                target=inputs.get("target")).value, "source": "calculations"}
        if metric in ("var", "value_at_risk"):
            return {"value": calculations.value_at_risk(
                obs, confidence=float(inputs.get("confidence", 0.95)),
                frequency=inputs.get("frequency", "daily"),
                horizon_periods=int(inputs.get("horizon_periods", 1))).value, "source": "calculations"}
        if metric == "beta":
            return {"value": calculations.beta(
                obs, inputs.get("benchmark"), frequency=inputs.get("frequency", "daily")).value,
                "source": "calculations"}
        if metric == "cumulative_return":
            return {"value": calculations.cumulative_return(
                obs, method=inputs.get("method", "simple")).value, "source": "calculations"}
        if metric == "annualized_return":
            return {"value": calculations.annualized_return(
                obs, frequency=inputs.get("frequency", "daily")).value, "source": "calculations"}
        if metric == "correlation":
            return {"value": calculations.correlation(
                obs, inputs.get("benchmark")).value, "source": "calculations"}
        if metric == "covariance":
            return {"value": calculations.covariance(
                obs, inputs.get("benchmark")).value, "source": "calculations"}
        if metric == "cvar":
            return {"value": calculations.cvar(
                obs, confidence=float(inputs.get("confidence", 0.95)),
                frequency=inputs.get("frequency", "daily")).value, "source": "calculations"}
    except Exception as exc:  # noqa: BLE001 - insufficient/invalid inputs = UNKNOWN
        return {"value": None, "source": f"error:{type(exc).__name__}", "detail": str(exc)}
    return {"value": None, "source": "unsupported_metric"}


class FinancialGrader(Grader):
    name = "financial"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config)
        financial = getattr(ctx.task, "metadata", {}).get("financial") or {}
        metric = config.get("metric") or financial.get("metric")
        inputs = config.get("inputs") or financial.get("inputs") or {}
        tolerance = float(config.get("tolerance", financial.get("tolerance", 1e-2)))
        if not metric:
            return GraderResult.unmeasured_result(self.name, "no financial metric declared")

        computed = compute_expected(metric, inputs)
        expected = computed.get("value")
        if expected is None:
            return GraderResult.unmeasured_result(
                self.name, f"could not independently compute {metric} ({computed.get('source')})"
            )

        actual = _extract_number(
            ctx.final_output or "", percent_as_fraction=abs(float(expected)) < 1.0,
        )
        details: dict[str, Any] = {
            "metric": metric,
            "expected": round(float(expected), 6),
            "source": computed.get("source"),
            "tolerance": tolerance,
        }
        if actual is None:
            return GraderResult(self.name, 0.0, False, details=details,
                                failures=["no numeric value in the agent output"])

        # A declared expected value is a cross-check on the independent compute.
        declared = config.get("expected_value", financial.get("expected_value"))
        if declared is not None and abs(float(declared) - float(expected)) > tolerance:
            return GraderResult(
                self.name, 0.0, False, details={**details, "declared": declared},
                failures=[f"independent compute {expected} disagrees with declared {declared}"],
            )

        diff = abs(float(expected) - actual)
        passed = diff <= tolerance
        details["actual"] = actual
        details["diff"] = round(diff, 6)
        score = 1.0 if passed else max(0.0, 1.0 - diff / (abs(float(expected)) or 1.0))
        return GraderResult(
            self.name, score, passed, details=details,
            failures=[] if passed else [f"{metric}: expected {expected} ±{tolerance}, got {actual}"],
            evidence=[{"metric": metric, "inputs": inputs}],
        )
