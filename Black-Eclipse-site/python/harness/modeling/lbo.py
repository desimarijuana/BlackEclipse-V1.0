"""Leveraged buyout: sources & uses, debt schedule, exit returns and sensitivities."""

from __future__ import annotations

from typing import Any

from .contracts import Check, ModelError, ModelResult, number, numbers
from .three_statement import build_three_statement


def _irr(cashflows: list[float]) -> float | None:
    if not cashflows or cashflows[0] >= 0:
        return None
    if all(value <= 0 for value in cashflows[1:]):
        return None

    def npv(rate: float) -> float:
        return sum(value / ((1.0 + rate) ** index) for index, value in enumerate(cashflows))

    low, high = -0.9999, 10.0
    f_low, f_high = npv(low), npv(high)
    if f_low * f_high > 0:
        return None
    for _ in range(240):
        middle = (low + high) / 2.0
        value = npv(middle)
        if abs(value) < 1e-9:
            return middle
        if value * f_low <= 0:
            high = middle
        else:
            low = middle
            f_low = value
    return (low + high) / 2.0


def _lbo_inputs(spec: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    lbo = spec.get("lbo")
    if not isinstance(lbo, dict):
        raise ModelError("INPUT_UNAVAILABLE", "lbo is required for an LBO model")
    entry_multiple = number(lbo.get("entryMultiple", lbo.get("entry_multiple")), "lbo.entryMultiple")
    exit_multiple = number(lbo.get("exitMultiple", lbo.get("exit_multiple")), "lbo.exitMultiple")
    holding = int(lbo.get("holdingYears", lbo.get("holding_years") or 5))
    if holding < 1 or holding > 20:
        raise ModelError("INPUT_INVALID", "lbo.holdingYears must be between 1 and 20")
    ebitda = lbo.get("ebitdaProjection", lbo.get("ebitda_projection"))
    if ebitda is not None:
        ebitda_values = numbers(ebitda, "lbo.ebitdaProjection", length=holding)
        da_values = numbers(lbo.get("daProjection", lbo.get("da_projection") or 0.0), "lbo.daProjection", length=holding)
        capex_values = numbers(lbo.get("capexProjection", lbo.get("capex_projection") or 0.0), "lbo.capexProjection", length=holding)
        dnwc_values = numbers(lbo.get("nwcChangeProjection", lbo.get("nwc_change_projection") or 0.0), "lbo.nwcChangeProjection", length=holding)
        tax_rate = number(lbo.get("taxRate", lbo.get("tax_rate") or 0.25), "lbo.taxRate")
        entry_ebitda = ebitda_values[0]
    else:
        if projection is None:
            raise ModelError("INPUT_UNAVAILABLE", "an LBO needs ebitdaProjection or a history/assumptions block")
        ebitda_values = [float(value) for value in projection["ebitda"][:holding]]
        if len(ebitda_values) < holding:
            raise ModelError("INPUT_INVALID", "the forecast is shorter than lbo.holdingYears")
        da_values = [float(value) for value in projection["da"][:holding]]
        capex_values = [float(value) for value in projection["capex"][:holding]]
        dnwc_values = [float(value) for value in projection["deltaNwc"][:holding]]
        tax_rate = float(projection["taxRate"])
        entry_ebitda = ebitda_values[0]
    if entry_ebitda <= 0:
        raise ModelError("INPUT_INVALID", "entry EBITDA must be positive")
    tranches = lbo.get("debtTranches", lbo.get("debt_tranches"))
    if not isinstance(tranches, list) or not tranches:
        raise ModelError("INPUT_UNAVAILABLE", "lbo.debtTranches is required")
    clean_tranches = []
    for index, tranche in enumerate(tranches):
        if not isinstance(tranche, dict):
            raise ModelError("INPUT_INVALID", f"lbo.debtTranches[{index}] must be an object")
        pik = bool(tranche.get("pik")) or str(tranche.get("type") or "").casefold() == "pik"
        rate = number(tranche.get("rate", tranche.get("cashRate", 0.0)), f"lbo.debtTranches[{index}].rate")
        pik_rate = number(
            tranche.get("pikRate", rate if pik else 0.0),
            f"lbo.debtTranches[{index}].pikRate",
        )
        clean_tranches.append({
            "name": str(tranche.get("name") or f"Tranche {index + 1}"),
            "amount": number(tranche.get("amount"), f"lbo.debtTranches[{index}].amount"),
            "rate": rate,
            "pik": pik,
            "pikRate": pik_rate,
            "amortization": number(tranche.get("amortization", tranche.get("amortization_pct", 0.0)), f"lbo.debtTranches[{index}].amortization"),
        })
    if any(tranche["amount"] < 0 or tranche["rate"] < 0 for tranche in clean_tranches):
        raise ModelError("INPUT_INVALID", "debt amounts and rates must not be negative")
    return {
        "entry_multiple": entry_multiple, "exit_multiple": exit_multiple, "holding": holding,
        "ebitda": ebitda_values, "da": da_values, "capex": capex_values, "delta_nwc": dnwc_values,
        "tax_rate": tax_rate, "entry_ebitda": entry_ebitda, "tranches": clean_tranches,
        "transaction_fees_pct": number(lbo.get("transactionFeesPct", lbo.get("transaction_fees_pct") or 0.0), "lbo.transactionFeesPct"),
        "financing_fees_pct": number(lbo.get("financingFeesPct", lbo.get("financing_fees_pct") or 0.0), "lbo.financingFeesPct"),
        "existing_debt": number(lbo.get("existingDebt", lbo.get("existing_debt") or 0.0), "lbo.existingDebt"),
        "management_rollover": number(lbo.get("managementRollover", lbo.get("management_rollover") or 0.0), "lbo.managementRollover"),
        "management_exit_share": number(
            lbo.get("managementExitShare", lbo.get("management_exit_share") or 0.0),
            "lbo.managementExitShare",
        ),
        "revolver_capacity": number(lbo.get("revolverCapacity", lbo.get("revolver_capacity") or 0.0), "lbo.revolverCapacity"),
        "revolver_rate": number(lbo.get("revolverRate", lbo.get("revolver_rate") or 0.0), "lbo.revolverRate"),
        "minimum_cash": number(lbo.get("minimumCash", lbo.get("minimum_cash") or 0.0), "lbo.minimumCash"),
        "exit_year": int(lbo.get("exitYear", lbo.get("exit_year") or holding)),
    }


def _run_lbo(inputs: dict[str, Any], entry_multiple: float | None = None, exit_multiple: float | None = None) -> dict[str, Any]:
    entry = entry_multiple if entry_multiple is not None else inputs["entry_multiple"]
    exit_mult = exit_multiple if exit_multiple is not None else inputs["exit_multiple"]
    purchase_price = inputs["entry_ebitda"] * entry
    transaction_fees = purchase_price * inputs["transaction_fees_pct"]
    debt_amount = sum(tranche["amount"] for tranche in inputs["tranches"])
    financing_fees = debt_amount * inputs["financing_fees_pct"]
    uses = purchase_price + transaction_fees + financing_fees + inputs["existing_debt"]
    equity = uses - debt_amount - inputs["management_rollover"]
    if equity <= 0:
        raise ModelError("LBO_EQUITY_NON_POSITIVE", "the debt tranches finance the entire transaction; equity must be positive")
    schedule: list[dict[str, Any]] = []
    balances = [tranche["amount"] for tranche in inputs["tranches"]]
    revolver = 0.0
    warnings: list[str] = []
    for year in range(inputs["holding"]):
        opening = list(balances)
        opening_revolver = revolver
        interest = (
            sum(opening[i] * inputs["tranches"][i]["rate"] for i in range(len(opening)))
            + opening_revolver * inputs["revolver_rate"]
        )
        pik_accrual = [
            opening[i] * inputs["tranches"][i]["pikRate"] if inputs["tranches"][i]["pik"] else 0.0
            for i in range(len(opening))
        ]
        ebitda = inputs["ebitda"][year]
        da = inputs["da"][year]
        ebit = ebitda - da
        taxes = max(0.0, ebit - interest) * inputs["tax_rate"]
        net_income = ebit - interest - taxes
        fcf = net_income + da - inputs["capex"][year] - inputs["delta_nwc"][year]
        mandatory = [
            min(opening[i] + pik_accrual[i], opening[i] * inputs["tranches"][i]["amortization"])
            for i in range(len(opening))
        ]
        remaining = fcf
        available_revolver = max(0.0, inputs["revolver_capacity"] - revolver)
        if remaining < sum(mandatory) + inputs["minimum_cash"]:
            draw = min(available_revolver, sum(mandatory) + inputs["minimum_cash"] - remaining)
            revolver += draw
            remaining += draw
        paid = [0.0] * len(opening)
        for i in range(len(opening)):
            if remaining <= 0:
                break
            pay = min(mandatory[i], remaining)
            paid[i] = pay
            remaining -= pay
        sweep_pool = max(0.0, remaining - inputs["minimum_cash"])
        for i in range(len(opening)):
            if sweep_pool <= 0:
                break
            room = max(0.0, opening[i] + pik_accrual[i] - paid[i])
            sweep = min(room, sweep_pool)
            paid[i] += sweep
            sweep_pool -= sweep
            remaining -= sweep
        if sweep_pool > 0 and revolver > 0:
            pay = min(revolver, sweep_pool)
            revolver -= pay
            remaining -= pay
        balances = [max(0.0, opening[i] + pik_accrual[i] - paid[i]) for i in range(len(opening))]
        if remaining < -1e-9:
            warnings.append(f"year {year + 1}: cash shortfall of {abs(remaining):,.2f} after the revolver capacity")
        schedule.append({
            "year": year + 1,
            "opening": opening,
            "interest": interest,
            "taxes": taxes,
            "netIncome": net_income,
            "fcf": fcf,
            "repayment": paid,
            "pikAccrual": pik_accrual,
            "revolver": revolver,
            "cash": remaining,
            "closing": list(balances),
        })
    exit_ebitda = inputs["ebitda"][min(inputs["exit_year"], inputs["holding"]) - 1]
    exit_ev = exit_ebitda * exit_mult
    exit_debt = sum(balances) + revolver
    exit_equity = exit_ev - exit_debt
    total_equity = equity + inputs["management_rollover"]
    if total_equity <= 0:
        raise ModelError("LBO_EQUITY_NON_POSITIVE", "total equity (sponsor + management) must be positive")
    management_share = inputs["management_exit_share"]
    if management_share < 0 or management_share > 1:
        raise ModelError("INPUT_INVALID", "lbo.managementExitShare must be in [0, 1]")
    sponsor_share = (1.0 - management_share) if management_share > 0 else equity / total_equity
    sponsor_exit = exit_equity * sponsor_share
    management_exit = exit_equity - sponsor_exit
    cashflows = [-equity] + [0.0] * (inputs["exit_year"] - 1) + [sponsor_exit]
    irr = _irr(cashflows)
    moic = sponsor_exit / equity if equity else None
    return {
        "purchase_price": purchase_price, "transaction_fees": transaction_fees,
        "financing_fees": financing_fees, "uses": uses, "debt_amount": debt_amount,
        "equity": equity, "schedule": schedule, "exit_ev": exit_ev,
        "exit_debt": exit_debt, "exit_equity": exit_equity, "irr": irr, "moic": moic,
        "sponsor_share": sponsor_share, "sponsor_exit": sponsor_exit,
        "management_exit": management_exit, "revolver": revolver, "warnings": warnings,
    }


def build_lbo(spec: dict[str, Any], statement: ModelResult | None = None) -> ModelResult:
    projection = (statement.meta.get("projection") if statement is not None else None)
    inputs = _lbo_inputs(spec, projection)
    base = _run_lbo(inputs)
    result = ModelResult(
        kind="lbo",
        company=spec["company"]["name"],
        currency=spec["company"]["currency"],
        units=spec["company"]["units"],
        years=[f"Year {index + 1}" for index in range(inputs["holding"])],
        assumptions=spec.get("lbo") or {},
        meta={"engine": "lbo.v1", **{key: value for key, value in base.items() if key != "schedule"}, "schedule": base["schedule"]},
    )
    if statement is not None:
        result.checks.extend(statement.checks)
        result.warnings.extend(statement.warnings)
    result.warnings.extend(base.get("warnings") or [])

    tranche_names = [tranche["name"] for tranche in inputs["tranches"]]
    result.add_section(
        "Sources & Uses",
        columns=["Item", "Amount"],
        rows=[
            _metric("Purchase enterprise value", base["purchase_price"]),
            _metric("Transaction fees", base["transaction_fees"]),
            _metric("Financing fees", base["financing_fees"]),
            _metric("Refinanced existing debt", inputs["existing_debt"]),
            _metric("Total uses", base["uses"]),
            _metric("Debt financing", base["debt_amount"]),
            _metric("Management rollover", inputs["management_rollover"]),
            _metric("Sponsor equity", base["equity"]),
            _metric("Total sources", base["debt_amount"] + inputs["management_rollover"] + base["equity"]),
        ],
    )
    result.add_section(
        "Debt Schedule",
        columns=["Year", *tranche_names, "Revolver", "Total debt"],
        rows=[
            {
                "label": f"Year {row['year']}",
                "values": [
                    row["year"],
                    *[round(value, 6) for value in row["closing"]],
                    round(row["revolver"], 6),
                    round(sum(row["closing"]) + row["revolver"], 6),
                ],
                "kind": "calc",
            }
            for row in base["schedule"]
        ],
    )
    result.add_section(
        "LBO Returns",
        columns=["Metric", "Value"],
        rows=[
            _metric("Entry EBITDA", inputs["entry_ebitda"]),
            _metric("Entry multiple", inputs["entry_multiple"]),
            _metric("Exit EBITDA", inputs["ebitda"][min(inputs["exit_year"], inputs["holding"]) - 1]),
            _metric("Exit multiple", inputs["exit_multiple"]),
            _metric("Exit enterprise value", base["exit_ev"]),
            _metric("Exit debt", base["exit_debt"]),
            _metric("Exit equity value", base["exit_equity"]),
            _metric("Management rollover", inputs["management_rollover"]),
            _metric("Sponsor equity", base["equity"]),
            _metric("Sponsor share of exit equity", base["sponsor_share"]),
            _metric("Sponsor exit proceeds", base["sponsor_exit"]),
            _metric("Management exit proceeds", base["management_exit"]),
            _metric("MOIC", base["moic"]),
            _metric("IRR", base["irr"]),
        ],
    )

    entry_axis = [inputs["entry_multiple"] + offset for offset in (-1.0, 0.0, 1.0)]
    exit_axis = [inputs["exit_multiple"] + offset for offset in (-1.0, 0.0, 1.0)]
    grid_rows = []
    for entry_value in entry_axis:
        values: list[Any] = [entry_value]
        for exit_value in exit_axis:
            try:
                cell = _run_lbo(inputs, entry_multiple=max(0.1, entry_value), exit_multiple=max(0.1, exit_value))
                values.append(round(cell["irr"], 6) if cell["irr"] is not None else None)
            except ModelError:
                values.append(None)
        grid_rows.append({"label": f"{entry_value:.1f}x", "values": values, "kind": "calc"})
    result.add_section(
        "LBO Sensitivity",
        columns=["Entry \\ Exit"] + [f"{value:.1f}x" for value in exit_axis],
        rows=grid_rows,
    )

    tolerance = max(1e-6, abs(base["uses"]) * 1e-9)
    result.checks.append(Check("sources_equal_uses",
                               "PASS" if abs((base["debt_amount"] + inputs["management_rollover"] + base["equity"]) - base["uses"]) <= tolerance else "FAIL",
                               "sources of financing equal total uses"))
    result.checks.append(Check("debt_non_negative",
                               "PASS" if all(all(value >= -tolerance for value in row["closing"]) for row in base["schedule"]) else "FAIL",
                               "no debt tranche is repaid below zero"))
    result.checks.append(Check("exit_equity_positive",
                               "PASS" if base["exit_equity"] > 0 else "FAIL",
                               "exit equity value must be positive",
                               value=base["exit_equity"]))
    result.checks.append(Check("sponsor_exit_share_valid",
                               "PASS" if 0 <= base["sponsor_share"] <= 1 else "FAIL",
                               "sponsor and management exit proceeds reconcile to exit equity",
                               value=base["sponsor_share"]))
    if base["irr"] is None:
        result.checks.append(Check("irr_solved", "WARN", "IRR could not be solved from these cash flows"))
    else:
        result.checks.append(Check("irr_solved", "PASS", "IRR was solved from the dated equity cash flows", value=base["irr"]))
    result.checks.append(Check(
        "revolver_capacity_respected",
        "PASS" if all(row["revolver"] <= inputs["revolver_capacity"] + tolerance for row in base["schedule"]) else "FAIL",
        "the revolver never exceeds its stated capacity",
    ))
    result.checks.append(Check(
        "cash_shortfall_checked",
        "PASS" if not base.get("warnings") else "WARN",
        "cash stayed at or above the minimum, or a shortfall was recorded",
    ))
    return result


def _metric(label: str, value: Any) -> dict[str, Any]:
    return {"label": label, "values": [value], "kind": "calc", "formulas": None}


__all__ = ["build_lbo"]
