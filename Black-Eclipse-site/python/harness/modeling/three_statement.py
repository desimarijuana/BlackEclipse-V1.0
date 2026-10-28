"""Integrated three-statement model.

Income statement, cash flow and balance sheet are built together so the
schedules can be checked against each other. The v1 projection uses a beginning
debt balance for interest (no circular interest-on-average-debt), which lets the
same arithmetic be written as a live Excel formula. A model that does not
balance is reported as FAIL rather than silently published.
"""

from __future__ import annotations

from typing import Any

from .contracts import Check, ModelError, ModelResult, history_block, latest, latest_optional, number, numbers

TOLERANCE = 1e-6


def _first(mapping: dict[str, Any], camel: str, snake: str, *, default: Any = None) -> Any:
    if camel in mapping and mapping[camel] is not None:
        return mapping[camel]
    if snake in mapping and mapping[snake] is not None:
        return mapping[snake]
    if default is not None:
        return default
    raise ModelError("INPUT_UNAVAILABLE", f"assumptions.{camel} is required")


def _check(result: ModelResult, name: str, okay: bool, detail: str, *, value: float = 0.0) -> None:
    result.checks.append(Check(name=name, status="PASS" if okay else "FAIL", detail=detail, value=value))


def build_three_statement(spec: dict[str, Any]) -> ModelResult:
    history = history_block(spec)
    assumptions = spec.get("assumptions") or {}
    forecast_years = int(assumptions.get("forecastYears") or assumptions.get("forecast_years") or 0)
    if forecast_years < 1 or forecast_years > 25:
        raise ModelError("INPUT_UNAVAILABLE", "assumptions.forecastYears must be between 1 and 25")
    growth = numbers(
        assumptions.get("revenueGrowth") or assumptions.get("revenue_growth"),
        "assumptions.revenueGrowth", length=forecast_years,
    )
    margin = numbers(
        assumptions.get("ebitdaMargin") or assumptions.get("ebitda_margin"),
        "assumptions.ebitdaMargin", length=forecast_years,
    )
    tax_rate = number(_first(assumptions, "taxRate", "tax_rate"), "assumptions.taxRate")
    interest_rate = number(_first(assumptions, "interestRate", "interest_rate"), "assumptions.interestRate")
    da_pct = number(_first(assumptions, "daPctRevenue", "da_pct_revenue"), "assumptions.daPctRevenue")
    capex_pct = number(_first(assumptions, "capexPctRevenue", "capex_pct_revenue"), "assumptions.capexPctRevenue")
    nwc_pct = number(_first(assumptions, "nwcPctRevenue", "nwc_pct_revenue"), "assumptions.nwcPctRevenue")
    repayment_pct = number(_first(assumptions, "debtRepaymentPct", "debt_repayment_pct", default=0.0), "assumptions.debtRepaymentPct")
    payout = number(_first(assumptions, "dividendPayout", "dividend_payout", default=0.0), "assumptions.dividendPayout")
    if not (0 <= tax_rate < 1):
        raise ModelError("INPUT_INVALID", "assumptions.taxRate must be in [0, 1)")
    if interest_rate < 0 or da_pct < 0 or capex_pct < 0 or nwc_pct < 0:
        raise ModelError("INPUT_INVALID", "rates and percentages must not be negative")
    if not (0 <= repayment_pct <= 1):
        raise ModelError("INPUT_INVALID", "assumptions.debtRepaymentPct must be in [0, 1]")
    if not (0 <= payout <= 1):
        raise ModelError("INPUT_INVALID", "assumptions.dividendPayout must be in [0, 1]")

    revenue0 = latest(history, "revenue")
    ebitda0 = latest_optional(history, "ebitda")
    da0 = latest_optional(history, "da")
    if ebitda0 is None:
        ebit0 = latest(history, "ebit")
        if da0 is None:
            raise ModelError("INPUT_UNAVAILABLE", "history needs ebitda or ebit+da")
        ebitda0 = ebit0 + da0
    if da0 is None:
        da0 = revenue0 * da_pct
    cash0 = latest(history, "cash")
    debt0 = latest(history, "debt")
    other_liabilities0 = latest(history, "other_liabilities") if history["series"].get("other_liabilities") else 0.0
    equity0 = latest(history, "equity")
    nwc0 = latest(history, "nwc")
    net_ppe0 = latest(history, "net_ppe")
    goodwill0 = latest_optional(history, "goodwill") or 0.0
    shares = latest_optional(history, "shares")

    assets0 = cash0 + nwc0 + net_ppe0 + goodwill0
    liabilities_equity0 = debt0 + other_liabilities0 + equity0
    if abs(assets0 - liabilities_equity0) > max(1e-6, abs(assets0) * TOLERANCE):
        raise ModelError(
            "HISTORICAL_BS_DOES_NOT_BALANCE",
            f"the latest historical balance sheet is out of balance by {assets0 - liabilities_equity0:,.6f}",
            detail={"assets": assets0, "liabilitiesAndEquity": liabilities_equity0},
        )

    history_year = history["years"][-1]
    years = [f"FY{int(history_year) + index}" if history_year.isdigit() else f"Y{index + 1}"
             for index in range(forecast_years + 1)]
    years[0] = history_year

    revenue = [revenue0]
    ebitda = [ebitda0]
    da = [da0]
    ebit = [ebitda0 - da0]
    interest = [0.0]
    taxes = [0.0]
    net_income = [0.0]
    cfo = [0.0]
    capex = [0.0]
    nwc = [nwc0]
    delta_nwc = [0.0]
    repayment = [0.0]
    dividends = [0.0]
    cash = [cash0]
    net_ppe = [net_ppe0]
    goodwill = [goodwill0]
    total_assets = [assets0]
    debt = [debt0]
    other_liabilities = [other_liabilities0]
    equity = [equity0]
    total_le = [liabilities_equity0]
    balance_delta = [assets0 - liabilities_equity0]

    for index in range(forecast_years):
        previous = index
        revenue_value = revenue[previous] * (1.0 + growth[index])
        ebitda_value = revenue_value * margin[index]
        da_value = revenue_value * da_pct
        ebit_value = ebitda_value - da_value
        interest_value = interest_rate * debt[previous]
        taxable = max(0.0, ebit_value - interest_value)
        tax_value = taxable * tax_rate
        net_value = ebit_value - interest_value - tax_value
        nwc_value = revenue_value * nwc_pct
        delta_nwc_value = nwc_value - nwc[previous]
        capex_value = revenue_value * capex_pct
        cfo_value = net_value + da_value - delta_nwc_value
        repayment_value = min(debt[previous], debt[previous] * repayment_pct)
        dividend_value = max(0.0, net_value * payout)
        cash_value = cash[previous] + cfo_value - capex_value - repayment_value - dividend_value
        ppe_value = net_ppe[previous] + capex_value - da_value
        debt_value = debt[previous] - repayment_value
        equity_value = equity[previous] + net_value - dividend_value
        assets_value = cash_value + nwc_value + ppe_value + goodwill[previous]
        le_value = debt_value + other_liabilities[previous] + equity_value

        revenue.append(revenue_value)
        ebitda.append(ebitda_value)
        da.append(da_value)
        ebit.append(ebit_value)
        interest.append(interest_value)
        taxes.append(tax_value)
        net_income.append(net_value)
        cfo.append(cfo_value)
        capex.append(capex_value)
        nwc.append(nwc_value)
        delta_nwc.append(delta_nwc_value)
        repayment.append(repayment_value)
        dividends.append(dividend_value)
        cash.append(cash_value)
        net_ppe.append(ppe_value)
        goodwill.append(goodwill[previous])
        total_assets.append(assets_value)
        debt.append(debt_value)
        other_liabilities.append(other_liabilities[previous])
        equity.append(equity_value)
        total_le.append(le_value)
        balance_delta.append(assets_value - le_value)

    result = ModelResult(
        kind="three_statement",
        company=spec["company"]["name"],
        currency=spec["company"]["currency"],
        units=spec["company"]["units"],
        years=years,
        assumptions=assumptions,
        meta={"engine": "three_statement.v1", "shares": shares},
    )
    result.add_section(
        "Income Statement",
        columns=years,
        rows=[
            _row("Revenue", revenue, "calc"),
            _row("EBITDA", ebitda, "calc"),
            _row("D&A", da, "calc"),
            _row("EBIT", ebit, "calc"),
            _row("Interest expense", interest, "calc"),
            _row("Taxes", taxes, "calc"),
            _row("Net income", net_income, "calc"),
        ],
    )
    result.add_section(
        "Cash Flow",
        columns=years,
        rows=[
            _row("Net income", net_income, "calc"),
            _row("D&A", da, "calc"),
            _row("Change in NWC", delta_nwc, "calc"),
            _row("Operating cash flow", cfo, "calc"),
            _row("Capex", capex, "calc"),
            _row("Debt repayment", repayment, "calc"),
            _row("Dividends", dividends, "calc"),
            _row("Ending cash", cash, "calc"),
        ],
    )
    result.add_section(
        "Balance Sheet",
        columns=years,
        rows=[
            _row("Cash", cash, "calc"),
            _row("Net working capital", nwc, "calc"),
            _row("Net PP&E", net_ppe, "calc"),
            _row("Goodwill", goodwill, "calc"),
            _row("Total assets", total_assets, "calc"),
            _row("Debt", debt, "calc"),
            _row("Other liabilities", other_liabilities, "calc"),
            _row("Equity", equity, "calc"),
            _row("Total liabilities + equity", total_le, "calc"),
            _row("Balance check", balance_delta, "check"),
        ],
    )
    result.add_section(
        "Debt Schedule",
        columns=years,
        rows=[
            _row("Opening debt", [debt[0]] + debt[:-1], "calc"),
            _row("Repayment", repayment, "calc"),
            _row("Closing debt", debt, "calc"),
        ],
    )

    max_delta = max(abs(value) for value in balance_delta)
    tolerance = max(1e-6, max(abs(value) for value in total_assets) * TOLERANCE)
    _check(result, "balance_sheet_balances", max_delta <= tolerance,
           f"maximum |assets - liabilities/equity| = {max_delta:,.6f}", value=max_delta)
    _check(result, "cash_flow_ties", all(
        abs(cash[index] - (cash[index - 1] + cfo[index] - capex[index] - repayment[index] - dividends[index])) <= tolerance
        for index in range(1, len(cash))
    ), "ending cash equals prior cash plus operating cash flow less capex, debt repayment and dividends")
    _check(result, "debt_schedule_ties", all(
        abs(debt[index] - (debt[index - 1] - repayment[index])) <= tolerance
        for index in range(1, len(debt))
    ), "closing debt equals opening debt less repayment")
    _check(result, "revenue_positive", all(value > 0 for value in revenue[1:]),
           "forecast revenue must remain positive")
    _check(result, "cash_non_negative", all(value >= -tolerance for value in cash[1:]),
           "forecast cash must not go negative (add a revolver or reduce distributions if it does)")
    if assumptions.get("cashSweep") or assumptions.get("cash_sweep"):
        result.warnings.append("cash sweep/revolver is not modelled in v1; debt amortisation is the explicit schedule")
    result.meta["latestHistory"] = {
        "revenue": revenue0, "ebitda": ebitda0, "da": da0, "cash": cash0, "debt": debt0,
        "nwc": nwc0, "net_ppe": net_ppe0, "goodwill": goodwill0,
        "other_liabilities": other_liabilities0, "equity": equity0, "shares": shares,
    }
    result.meta["freeCashFlowToFirm"] = [
        ebit[index] * (1.0 - tax_rate) + da[index] - capex[index] - delta_nwc[index]
        for index in range(1, len(years))
    ]
    result.meta["fcffYears"] = years[1:]
    result.meta["projection"] = {
        "revenue": revenue[1:],
        "ebitda": ebitda[1:],
        "da": da[1:],
        "ebit": ebit[1:],
        "capex": capex[1:],
        "deltaNwc": delta_nwc[1:],
        "taxRate": tax_rate,
    }
    return result


def _row(label: str, values: list[float], kind: str = "calc", formulas: list[str] | None = None) -> dict[str, Any]:
    return {"label": label, "values": [round(value, 8) for value in values], "kind": kind, "formulas": formulas}


def formula_rows(spec: dict[str, Any], result: ModelResult) -> dict[str, list[str]]:
    """A1 formulas for the projection columns (C..), matching the engine's simple path."""
    assumptions = spec.get("assumptions") or {}
    forecast_years = int(assumptions.get("forecastYears") or 0)
    rows: dict[str, list[str]] = {}
    for index in range(forecast_years):
        column = _col(3 + index)
        previous = _col(2 + index)
        assumption_row = 13 + index
        rows.setdefault("Revenue", []).append(f"={previous}4*(1+Assumptions!$B${assumption_row})")
        rows.setdefault("EBITDA", []).append(f"={column}4*Assumptions!$C${assumption_row}")
        rows.setdefault("D&A", []).append(f"={column}4*Assumptions!$B$5")
        rows.setdefault("EBIT", []).append(f"={column}5-{column}6")
        rows.setdefault("Interest expense", []).append(f"=Assumptions!$B$4*{previous}21")
        rows.setdefault("Taxes", []).append(f"=MAX(0,{column}7-{column}8)*Assumptions!$B$3")
        rows.setdefault("Net income", []).append(f"={column}7-{column}8-{column}9")
        rows.setdefault("Operating cash flow", []).append(f"={column}10+{column}6-({column}17-{previous}17)")
        rows.setdefault("Capex", []).append(f"={column}4*Assumptions!$B$6")
        rows.setdefault("Change in NWC", []).append(f"={column}17-{previous}17")
        rows.setdefault("Debt repayment", []).append(f"=MIN({previous}21,{previous}21*Assumptions!$B$8)")
        rows.setdefault("Dividends", []).append(f"=MAX(0,{column}10*Assumptions!$B$9)")
        rows.setdefault("Ending cash", []).append(f"={previous}16+{column}11-{column}12-{column}14-{column}15")
        rows.setdefault("Net working capital", []).append(f"={column}4*Assumptions!$B$7")
        rows.setdefault("Net PP&E", []).append(f"={previous}18+{column}12-{column}6")
        rows.setdefault("Goodwill", []).append(f"={previous}19")
        rows.setdefault("Total assets", []).append(f"={column}16+{column}17+{column}18+{column}19")
        rows.setdefault("Debt", []).append(f"={previous}21-{column}14")
        rows.setdefault("Other liabilities", []).append(f"={previous}22")
        rows.setdefault("Equity", []).append(f"={previous}23+{column}10-{column}15")
        rows.setdefault("Total liabilities + equity", []).append(f"={column}21+{column}22+{column}23")
        rows.setdefault("Balance check", []).append(f"={column}20-{column}24")
    return rows


def _col(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


__all__ = ["build_three_statement", "formula_rows"]
