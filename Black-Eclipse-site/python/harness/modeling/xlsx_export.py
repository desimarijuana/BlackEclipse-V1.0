"""Formula-bearing workbook export.

The engine computes every value independently. The workbook carries the same
arithmetic as live Excel formulas so a user can change an assumption and see the
model recalculate. A `Values` sheet carries the engine's numbers for viewers that
do not calculate formulas. The workbook never claims to be recalculated by
Eclipse after a user edit.
"""

from __future__ import annotations

import io
from typing import Any, Optional

from .contracts import ModelError, ModelResult
from .three_statement import formula_rows

TS_SECTION_NAMES = ("Income Statement", "Cash Flow", "Balance Sheet", "Debt Schedule")
TS_ROWS = [
    ("Revenue", 4), ("EBITDA", 5), ("D&A", 6), ("EBIT", 7),
    ("Interest expense", 8), ("Taxes", 9), ("Net income", 10),
    ("Operating cash flow", 11), ("Capex", 12), ("Change in NWC", 13),
    ("Debt repayment", 14), ("Dividends", 15), ("Ending cash", 16),
    ("Net working capital", 17), ("Net PP&E", 18), ("Goodwill", 19),
    ("Total assets", 20), ("Debt", 21), ("Other liabilities", 22),
    ("Equity", 23), ("Total liabilities + equity", 24), ("Balance check", 25),
]


def _openpyxl() -> tuple[Any, Any, Any, Any]:
    try:
        from openpyxl import Workbook  # noqa: PLC0415
        from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
        from openpyxl.utils import get_column_letter  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise ModelError(
            "XLSX_LIBRARY_MISSING",
            "openpyxl is not installed, so the Excel model cannot be written",
        ) from exc
    return Workbook, Font, PatternFill, get_column_letter


def _style_header(cell: Any, fill: Any) -> None:
    from openpyxl.styles import Font  # noqa: PLC0415

    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = fill


def _write_checks(sheet: Any, result: ModelResult) -> None:
    sheet.append(["Check", "Status", "Detail", "Value"])
    for check in result.checks:
        sheet.append([check.name, check.status, check.detail, check.value])


def _write_assumptions(sheet: Any, spec: dict[str, Any], result: ModelResult) -> None:
    assumptions = spec.get("assumptions") or {}
    sheet.append(["Assumption", "Value"])
    sheet.append(["Forecast years", int(assumptions.get("forecastYears") or assumptions.get("forecast_years") or 0)])
    sheet.append(["Tax rate", float(assumptions.get("taxRate") or assumptions.get("tax_rate") or 0.0)])
    sheet.append(["Interest rate", float(assumptions.get("interestRate") or assumptions.get("interest_rate") or 0.0)])
    sheet.append(["D&A % revenue", float(assumptions.get("daPctRevenue") or assumptions.get("da_pct_revenue") or 0.0)])
    sheet.append(["Capex % revenue", float(assumptions.get("capexPctRevenue") or assumptions.get("capex_pct_revenue") or 0.0)])
    sheet.append(["NWC % revenue", float(assumptions.get("nwcPctRevenue") or assumptions.get("nwc_pct_revenue") or 0.0)])
    sheet.append(["Debt repayment %", float(assumptions.get("debtRepaymentPct") or assumptions.get("debt_repayment_pct") or 0.0)])
    sheet.append(["Dividend payout", float(assumptions.get("dividendPayout") or assumptions.get("dividend_payout") or 0.0)])
    sheet.append(["Min cash", float(assumptions.get("minCash") or assumptions.get("min_cash") or 0.0)])
    sheet.append([])
    sheet.append(["Year", "Revenue growth", "EBITDA margin"])
    years = result.years[1:]
    growth = assumptions.get("revenueGrowth") or assumptions.get("revenue_growth") or []
    margin = assumptions.get("ebitdaMargin") or assumptions.get("ebitda_margin") or []
    if isinstance(growth, (int, float)):
        growth = [growth] * len(years)
    if isinstance(margin, (int, float)):
        margin = [margin] * len(years)
    for index, year in enumerate(years):
        sheet.append([
            year,
            float(growth[index]) if index < len(growth) else None,
            float(margin[index]) if index < len(margin) else None,
        ])
    for row in range(2, 12):
        sheet.cell(row=row, column=2).number_format = "0.00%"
    for row in range(13, 13 + len(years)):
        sheet.cell(row=row, column=2).number_format = "0.00%"
        sheet.cell(row=row, column=3).number_format = "0.00%"


def _section_rows(result: ModelResult) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for section_name in TS_SECTION_NAMES:
        section = result.sections.get(section_name)
        if not section:
            continue
        for row in section["rows"]:
            rows.setdefault(row["label"], row)
    return rows


def _write_three_statement(workbook: Any, sheet: Any, spec: dict[str, Any], result: ModelResult, fill: Any) -> None:
    from openpyxl.utils import get_column_letter  # noqa: PLC0415

    rows = _section_rows(result)
    formulas = formula_rows(spec, result)
    sheet.append([result.company, ""] + result.years)
    sheet.append([f"{result.units} · {result.currency}", ""] + [""] * (len(result.years) - 1))
    sheet.append(["Line item", *result.years])
    for cell in sheet[3]:
        _style_header(cell, fill)
    for label, row_number in TS_ROWS:
        source = rows.get(label)
        values = source["values"] if source else [None] * len(result.years)
        formula_list = formulas.get(label, [])
        sheet.cell(row=row_number, column=1, value=label)
        for index, value in enumerate(values):
            column = 2 + index
            cell = sheet.cell(row=row_number, column=column)
            formula_index = index - 1
            if index > 0 and formula_index < len(formula_list) and formula_list[formula_index]:
                cell.value = formula_list[formula_index]
            else:
                cell.value = value
            cell.number_format = "#,##0.0"
        if label == "Balance check":
            for index in range(len(values)):
                sheet.cell(row=row_number, column=2 + index).number_format = "#,##0.000000"
    sheet.freeze_panes = "B4"
    sheet.column_dimensions["A"].width = 30
    for index in range(len(result.years)):
        sheet.column_dimensions[get_column_letter(2 + index)].width = 14


def _write_table(sheet: Any, section: dict[str, Any], fill: Any) -> None:
    from openpyxl.utils import get_column_letter  # noqa: PLC0415

    columns = section.get("columns") or []
    sheet.append(list(columns))
    for cell in sheet[1]:
        _style_header(cell, fill)
    for row in section.get("rows") or []:
        values = row.get("values") or []
        if len(columns) == len(values):
            sheet.append(list(values))
        else:
            sheet.append([row.get("label") or ""] + list(values))
    sheet.freeze_panes = "A2"
    for index in range(1, len(columns) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 18


def _write_values_sheet(sheet: Any, result: ModelResult, fill: Any) -> None:
    sheet.append(["Section", "Line", *result.years])
    for cell in sheet[1]:
        _style_header(cell, fill)
    for section_name, section in result.sections.items():
        for row in section.get("rows") or []:
            values = row.get("values") or []
            padded = list(values) + [None] * max(0, len(result.years) - len(values))
            sheet.append([section_name, row.get("label") or ""] + padded[: len(result.years)])
    sheet.freeze_panes = "C2"


def build_workbook_bytes(spec: dict[str, Any], result: ModelResult) -> bytes:
    Workbook, Font, PatternFill, get_column_letter = _openpyxl()
    workbook = Workbook()
    header_fill = PatternFill("solid", fgColor="1F2937")
    title_font = Font(bold=True, size=14)
    input_font = Font(color="1D4ED8")

    cover = workbook.active
    cover.title = "Cover"
    cover["A1"] = result.company
    cover["A1"].font = title_font
    cover["A2"] = f"{result.kind.replace('_', ' ').title()} model"
    cover["A3"] = f"{result.units} · {result.currency}"
    cover["A4"] = "Generated by Eclipse. Values on the model sheets are live formulas; see the Values sheet for the engine's computed numbers."
    cover["A5"] = f"Spec hash: {result.meta.get('specHash', '')}"
    cover["A6"] = "Checks: " + ("PASS" if result.checks_pass() else "FAIL")
    cover.column_dimensions["A"].width = 120

    assumptions = workbook.create_sheet("Assumptions")
    _write_assumptions(assumptions, spec, result)
    for row in range(2, 12):
        assumptions.cell(row=row, column=2).font = input_font

    if any(name in result.sections for name in TS_SECTION_NAMES):
        ts = workbook.create_sheet("Three Statement")
        _write_three_statement(workbook, ts, spec, result, header_fill)

    for section_name, section in result.sections.items():
        if section_name in TS_SECTION_NAMES:
            continue
        sheet = workbook.create_sheet(str(section_name)[:31])
        _write_table(sheet, section, header_fill)

    values = workbook.create_sheet("Values")
    _write_values_sheet(values, result, header_fill)

    checks = workbook.create_sheet("Checks")
    _write_checks(checks, result)
    for row in range(2, 2 + len(result.checks)):
        status = checks.cell(row=row, column=2).value
        if status == "FAIL":
            checks.cell(row=row, column=2).font = Font(bold=True, color="B91C1C")
        elif status == "PASS":
            checks.cell(row=row, column=2).font = Font(color="047857")
    checks.column_dimensions["A"].width = 34
    checks.column_dimensions["C"].width = 80

    warnings = workbook.create_sheet("Warnings")
    warnings.append(["Warning"])
    for warning in result.warnings:
        warnings.append([warning])

    calculation = getattr(workbook, "calculation", None)
    if calculation is not None:
        try:
            calculation.fullCalcOnLoad = True
            calculation.forceFullCalc = True
        except Exception:  # noqa: BLE001 - the property is advisory
            pass

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


__all__ = ["build_workbook_bytes"]
