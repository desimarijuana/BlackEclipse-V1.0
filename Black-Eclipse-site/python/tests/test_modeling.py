from __future__ import annotations

import io

import pytest

from harness.modeling import build_model, build_model_report, build_summary, build_workbook_bytes
from harness.modeling.contracts import ModelError


def _history() -> dict:
    return {
        "years": ["2024"],
        "series": {
            "revenue": [1000.0],
            "ebitda": [200.0],
            "da": [50.0],
            "capex": [60.0],
            "nwc": [100.0],
            "cash": [80.0],
            "debt": [400.0],
            "other_liabilities": [50.0],
            "equity": [430.0],
            "net_ppe": [600.0],
            "goodwill": [100.0],
            "shares": [100.0],
        },
    }


def _assumptions() -> dict:
    return {
        "forecastYears": 3,
        "revenueGrowth": [0.10, 0.08, 0.06],
        "ebitdaMargin": [0.20, 0.21, 0.22],
        "taxRate": 0.25,
        "interestRate": 0.06,
        "daPctRevenue": 0.05,
        "capexPctRevenue": 0.06,
        "nwcPctRevenue": 0.10,
        "debtRepaymentPct": 0.05,
        "dividendPayout": 0.20,
        "terminalGrowth": 0.025,
        "netDebt": 320.0,
        "sharesOutstanding": 100.0,
        "wacc": {
            "market_cap": 5000.0,
            "total_debt": 400.0,
            "risk_free_rate": 0.04,
            "beta": 1.1,
            "equity_risk_premium": 0.055,
            "cost_of_debt": 0.06,
            "tax_rate": 0.25,
        },
    }


def _three_statement_spec() -> dict:
    return {"kind": "three_statement", "company": {"name": "Example Co", "currency": "USD", "units": "millions"},
            "history": _history(), "assumptions": _assumptions()}


def _peer(name: str, ebitda: float) -> dict:
    return {
        "name": name, "price": 50.0, "shares": 100.0, "debt": 200.0, "cash": 50.0,
        "revenue": 500.0, "ebitda": ebitda, "ebit": ebitda * 0.8, "eps": 3.0,
        "period": "LTM 2024", "source": "fixture", "currency": "USD",
    }


def test_three_statement_balances_and_ties():
    result = build_model(_three_statement_spec())
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    sections = result.sections
    balance = next(row for row in sections["Balance Sheet"]["rows"] if row["label"] == "Balance check")
    assert max(abs(value) for value in balance["values"]) < 1e-6
    cash = next(row for row in sections["Cash Flow"]["rows"] if row["label"] == "Ending cash")
    assert cash["values"][-1] > 0


def test_dcf_uses_wacc_and_projects_per_share():
    spec = {"kind": "dcf", "company": {"name": "Example Co"}, "history": _history(), "assumptions": _assumptions()}
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    assert result.meta["wacc"] > 0
    assert result.meta["enterpriseValue"] > 0
    assert result.meta["valuePerShare"] is not None
    assert "DCF" in result.sections


def test_dcf_mid_year_convention():
    spec = {"kind": "dcf", "company": {"name": "Example Co"}, "history": _history(), "assumptions": _assumptions()}
    spec["assumptions"]["midYear"] = True
    result = build_model(spec)
    assert result.meta["midYear"] is True
    schedule = result.sections["DCF Schedule"]["rows"]
    assert schedule[0]["values"][2] == pytest.approx(1.0 / (1.0 + result.meta["wacc"]) ** 0.5)
    assert any("mid-year" in warning.lower() for warning in result.warnings)


def test_integrated_model_exposes_dcf_key_metrics_to_the_audit():
    spec = {
        "kind": "integrated",
        "company": {"name": "Example Co", "currency": "USD", "units": "millions"},
        "history": _history(),
        "assumptions": _assumptions(),
    }
    result = build_model(spec)
    assert result.meta.get("enterpriseValue") is not None
    assert result.meta.get("equityValue") is not None
    assert result.meta.get("valuePerShare") is not None
    summary = build_summary(result)
    assert summary["keyMetrics"]["enterpriseValue"] == result.meta["enterpriseValue"]
    assert summary["keyMetrics"]["valuePerShare"] == result.meta["valuePerShare"]


def test_integrated_accepts_wacc_aliases_and_deduplicates_checks():
    spec = {
        "kind": "integrated",
        "company": {"name": "Example Co", "currency": "USD", "units": "millions"},
        "history": _history(),
        "assumptions": _assumptions(),
    }
    wacc = spec["assumptions"].pop("wacc")
    spec["assumptions"]["waccInputs"] = {
        "marketCap": wacc["market_cap"],
        "totalDebt": wacc["total_debt"],
        "riskFreeRate": wacc["risk_free_rate"],
        "beta": wacc["beta"],
        "equityRiskPremium": wacc["equity_risk_premium"],
        "costOfDebt": wacc["cost_of_debt"],
        "taxRate": wacc["tax_rate"],
    }
    spec["dcf"] = {"midYear": True}
    result = build_model(spec)
    assert "DCF" in result.sections
    assert result.meta.get("enterpriseValue") is not None
    assert result.meta.get("valuePerShare") is not None
    check_keys = [(check.name, check.detail, check.value) for check in result.checks]
    assert len(check_keys) == len(set(check_keys))
    summary = build_summary(result)
    assert summary["keyMetrics"]["enterpriseValue"] is not None


def test_comps_accepts_camel_case_target_and_peer_fields():
    peer = _peer("Alias Co", 100.0)
    peer.pop("debt", None)
    peer.pop("cash", None)
    peer.pop("shares", None)
    peer.pop("net_income", None)
    peer.update({
        "totalDebt": 200.0,
        "cashAndCashEquivalents": 50.0,
        "sharesOutstanding": 100.0,
        "netIncome": 50.0,
    })
    spec = {
        "kind": "comps",
        "company": {"name": "Example Co", "currency": "USD"},
        "comps": {
            "peers": [peer, _peer("Alias Co 2", 110.0), _peer("Alias Co 3", 90.0)],
            "target": {"metric": "ebitda", "value": 150.0, "netDebt": 300.0, "sharesOutstanding": 100.0},
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    row = result.sections["Implied Valuation"]["rows"][0]["values"]
    assert row[4] == pytest.approx(row[3] - 300.0)
    assert row[5] == pytest.approx((row[3] - 300.0) / 100.0)


def test_lbo_sources_uses_and_returns():
    spec = {
        "kind": "lbo",
        "company": {"name": "Example Co"},
        "lbo": {
            "entryMultiple": 8.0,
            "exitMultiple": 9.0,
            "holdingYears": 3,
            "ebitdaProjection": [220.0, 240.0, 260.0],
            "daProjection": [50.0, 52.0, 54.0],
            "capexProjection": [60.0, 62.0, 64.0],
            "nwcChangeProjection": [0.0, 0.0, 0.0],
            "taxRate": 0.25,
            "transactionFeesPct": 0.02,
            "financingFeesPct": 0.015,
            "debtTranches": [
                {"name": "Term Loan", "amount": 800.0, "rate": 0.07, "amortization": 0.05},
                {"name": "Notes", "amount": 400.0, "rate": 0.09, "amortization": 0.0},
            ],
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    assert result.meta["irr"] is not None
    assert result.meta["moic"] is not None and result.meta["moic"] > 0
    assert "Sources & Uses" in result.sections


def test_lbo_management_rollover_is_split_at_exit():
    spec = {
        "kind": "lbo",
        "company": {"name": "Example Co"},
        "lbo": {
            "entryMultiple": 8.0,
            "exitMultiple": 9.0,
            "holdingYears": 3,
            "ebitdaProjection": [220.0, 240.0, 260.0],
            "daProjection": [50.0, 52.0, 54.0],
            "capexProjection": [60.0, 62.0, 64.0],
            "nwcChangeProjection": [0.0, 0.0, 0.0],
            "taxRate": 0.25,
            "managementRollover": 100.0,
            "managementExitShare": 0.20,
            "debtTranches": [
                {"name": "Term Loan", "amount": 800.0, "rate": 0.07, "amortization": 0.05},
            ],
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    assert result.meta["sponsor_share"] == pytest.approx(0.80)
    assert result.meta["sponsor_exit"] + result.meta["management_exit"] == pytest.approx(result.meta["exit_equity"])
    assert result.meta["irr"] is not None


def test_lbo_revolver_and_pik_tranche():
    spec = {
        "kind": "lbo",
        "company": {"name": "Example Co"},
        "lbo": {
            "entryMultiple": 8.0,
            "exitMultiple": 9.0,
            "holdingYears": 3,
            "ebitdaProjection": [150.0, 240.0, 260.0],
            "daProjection": [50.0, 50.0, 50.0],
            "capexProjection": [200.0, 60.0, 60.0],
            "nwcChangeProjection": [0.0, 0.0, 0.0],
            "taxRate": 0.25,
            "transactionFeesPct": 0.02,
            "financingFeesPct": 0.015,
            "revolverCapacity": 300.0,
            "revolverRate": 0.09,
            "minimumCash": 10.0,
            "debtTranches": [
                {"name": "Term Loan", "amount": 600.0, "rate": 0.08, "amortization": 0.05},
                {"name": "PIK Notes", "amount": 400.0, "rate": 0.0, "pik": True, "pikRate": 0.10, "amortization": 0.0},
            ],
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    assert any(row["revolver"] > 0 for row in result.meta["schedule"])
    assert any(sum(row["pikAccrual"]) > 0 for row in result.meta["schedule"])
    assert all(row["cash"] >= 10.0 - 1e-6 for row in result.meta["schedule"])


def test_comps_statistics_and_implied_valuation():
    spec = {
        "kind": "comps",
        "company": {"name": "Example Co"},
        "comps": {
            "peers": [_peer("A", 100.0), _peer("B", 120.0), _peer("C", 80.0)],
            "target": {"metric": "ebitda", "value": 150.0, "net_debt": 300.0, "shares": 100.0},
            "multiples": ["ev_ebitda", "ev_revenue", "pe"],
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    stats = result.meta["stats"]
    assert stats["ev_ebitda"]["count"] == 3
    implied = result.sections["Implied Valuation"]["rows"]
    assert implied
    assert all(row["values"][-1] is not None for row in implied)


def test_comps_fx_and_strict_calendarization():
    peer = _peer("EUR Co", 100.0)
    peer.update({
        "currency": "EUR", "period": "2024-12-31", "fiscalYearEnd": "12-31",
        "revenue": 100.0, "ebitda": 20.0, "ebit": 16.0,
    })
    spec = {
        "kind": "comps",
        "company": {"name": "Example Co", "currency": "USD", "fiscalYearEnd": "12-31"},
        "comps": {
            "peers": [peer],
            "fx": {"EUR": 1.10},
            "target": {"metric": "ebitda", "value": 150.0, "net_debt": 300.0, "shares": 100.0},
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    row = result.sections["Peer Multiples"]["rows"][0]["values"]
    assert row[9] == "USD"
    assert row[10] == pytest.approx(1.10)
    assert row[11] == pytest.approx(1.0)
    assert row[12] == "none"
    assert row[1] == pytest.approx(50.0 * 1.10 * 100.0)
    assert row[3] == pytest.approx(row[2] / (100.0 * 1.10))

    peer["currency"] = "EUR"
    spec["comps"]["fx"] = {}
    result = build_model(spec)
    assert result.meta["validPeers"] == 0
    assert any("no fxRate" in item["reason"] for item in result.meta["excluded"])


def test_comps_calendarization_requires_quarterly_or_explicit_factor():
    peer = _peer("June Co", 100.0)
    peer.update({"period": "2024-06-30", "fiscalYearEnd": "06-30"})
    spec = {
        "kind": "comps",
        "company": {"name": "Example Co", "currency": "USD", "fiscalYearEnd": "12-31"},
        "comps": {
            "peers": [peer],
            "target": {"metric": "ebitda", "value": 150.0, "net_debt": 300.0, "shares": 100.0},
        },
    }
    result = build_model(spec)
    assert result.meta["validPeers"] == 0
    assert any("fiscal year end differs" in item["reason"] for item in result.meta["excluded"])

    peer["calendarizationFactor"] = 1.5
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    row = result.sections["Peer Multiples"]["rows"][0]["values"]
    assert row[11] == pytest.approx(1.5)
    assert row[12] == "explicit_factor"


def test_comps_exact_quarterly_calendarization():
    peer = _peer("TTM Co", 999.0)
    peer.update({
        "period": "2024-12-31", "fiscalYearEnd": "12-31",
        "revenue": 999.0, "ebitda": 999.0, "ebit": 999.0, "net_income": 999.0, "eps": 999.0,
        "quarterly": [
            {"endDate": "2024-03-31", "revenue": 10.0, "ebitda": 2.0, "operatingIncome": 1.5, "netIncome": 1.0, "eps": 0.1},
            {"endDate": "2024-06-30", "revenue": 10.0, "ebitda": 2.0, "operatingIncome": 1.5, "netIncome": 1.0, "eps": 0.1},
            {"endDate": "2024-09-30", "revenue": 10.0, "ebitda": 2.0, "operatingIncome": 1.5, "netIncome": 1.0, "eps": 0.1},
            {"endDate": "2024-12-31", "revenue": 10.0, "ebitda": 2.0, "operatingIncome": 1.5, "netIncome": 1.0, "eps": 0.1},
        ],
    })
    spec = {
        "kind": "comps",
        "company": {"name": "Example Co", "currency": "USD", "fiscalYearEnd": "12-31"},
        "comps": {
            "peers": [peer],
            "target": {"metric": "ebitda", "value": 150.0, "net_debt": 300.0, "shares": 100.0},
        },
    }
    result = build_model(spec)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    row = result.sections["Peer Multiples"]["rows"][0]["values"]
    assert row[3] == pytest.approx(5150.0 / 40.0)
    assert row[4] == pytest.approx(5150.0 / 8.0)
    assert row[6] == pytest.approx(50.0 / 0.4)
    assert row[12] == "quarterly_ttm"
    assert not any("approximate" in warning for warning in result.warnings)


def test_comps_peer_symbols_are_hydrated_through_the_bridge():
    import asyncio

    from harness.modeling.tools import _hydrate_comps
    from harness.tools import ToolContext

    class Bridge:
        async def fetch(self, capability, params):
            if capability == "market_snapshot":
                return {"status": "OK", "currency": "USD", "price": {"price": 50.0, "marketCap": 5000.0}}
            if capability == "financial_statements":
                return {
                    "status": "OK", "currency": "USD", "statementSource": "fixture",
                    "periods": [{
                        "endDate": "2024-12-31", "fiscalYear": 2024,
                        "revenue": 500.0, "ebitda": 100.0, "operatingIncome": 80.0,
                        "netIncome": 50.0, "eps": 3.0, "totalDebt": 200.0,
                        "cash": 50.0, "sharesOutstanding": 100.0,
                    }],
                }
            return {"status": "UNAVAILABLE"}

    spec = {
        "kind": "comps",
        "company": {"name": "Example Co"},
        "comps": {
            "peerSymbols": ["AAA", "BBB"],
            "target": {"metric": "ebitda", "value": 150.0, "net_debt": 300.0, "shares": 100.0},
        },
    }
    context = ToolContext(run_id="run_test", log=lambda *args, **kwargs: None, data_bridge=Bridge())
    hydrated = asyncio.run(_hydrate_comps(spec, context))
    assert len(hydrated["comps"]["peers"]) == 2
    assert hydrated["comps"]["peers"][0]["revenue"] == 500.0
    result = build_model(hydrated)
    assert result.checks_pass(), [check.to_dict() for check in result.checks]
    assert result.meta["stats"]["ev_ebitda"]["count"] == 2


def test_workbook_contains_formulas_and_checks():
    spec = _three_statement_spec()
    result = build_model(spec)
    data = build_workbook_bytes(spec, result)
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), data_only=False)
    assert "Three Statement" in workbook.sheetnames
    assert "Values" in workbook.sheetnames
    assert "Checks" in workbook.sheetnames
    sheet = workbook["Three Statement"]
    assert sheet["C4"].value.startswith("=")
    assert workbook["Checks"]["B2"].value in ("PASS", "FAIL", "WARN")


def test_model_reports_export_pdf_docx_and_pptx():
    spec = _three_statement_spec()
    result = build_model(spec)
    pdf = build_model_report("pdf", spec, result)
    docx = build_model_report("docx", spec, result)
    pptx = build_model_report("pptx", spec, result)
    assert pdf.startswith(b"%PDF")
    assert docx[:2] == b"PK"
    assert pptx[:2] == b"PK"

    from docx import Document
    from pptx import Presentation

    assert Document(io.BytesIO(docx)).paragraphs
    assert len(Presentation(io.BytesIO(pptx)).slides) >= 2


def test_missing_input_is_named():
    spec = {"kind": "three_statement", "company": {"name": "Example Co"}, "history": {"years": ["2024"], "series": {"revenue": [1.0]}}, "assumptions": {"forecastYears": 1}}
    with pytest.raises(ModelError) as caught:
        build_model(spec)
    assert caught.value.code in ("INPUT_UNAVAILABLE", "INPUT_INVALID")


def test_financial_model_build_tool_registers_workbook(tmp_path):
    import asyncio

    from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
    from harness.modeling.tools import register_modeling_tools
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext, ToolRegistry

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
        registry = ToolRegistry()
        register_modeling_tools(registry)
        context = ToolContext(
            run_id="run_test", log=lambda *args, **kwargs: None,
            artifact_service=service, agent_id="eclipse-agent",
        )
        text, data = asyncio.run(registry.get("financial_model_build").handler({
            "spec": _three_statement_spec(),
            "filename": "Example-Co-model",
            "formats": ["xlsx", "pdf", "docx", "pptx"],
        }, context))
        assert data["status"] == "OK", (text, data)
        assert data["summary"]["checksPass"] is True
        assert len(data["artifacts"]) == 4
        assert {item["extension"] for item in data["artifacts"]} == {"xlsx", "pdf", "docx", "pptx"}
        assert data["artifact"]["category"] == "financial"
        handle, _ = service.open_content(data["artifact"]["id"])
        try:
            payload = handle.read()
        finally:
            handle.close()
        assert payload[:2] == b"PK"

        _text2, again = asyncio.run(registry.get("financial_model_build").handler({
            "spec": _three_statement_spec(),
            "filename": "Example-Co-model",
            "formats": ["xlsx", "pdf", "docx", "pptx"],
        }, context))
        assert [item["id"] for item in again["artifacts"]] == [item["id"] for item in data["artifacts"]]
    finally:
        store.close()
