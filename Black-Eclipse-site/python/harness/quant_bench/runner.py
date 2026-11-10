"""QuantBench runner — grade routing, honesty, invariants, workflow, reproducibility."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Iterable, Optional

import numpy as np

from ..quant import fixtures as F
from ..quant import strategy as S
from ..quant.corporate_actions import CorporateAction, apply_to_position
from ..quant.discovery.diagnostics import analyze_structure
from ..quant.discovery.library import list_method_families, recommend_methods
from ..quant.discovery.miner import mine_methods
from ..quant.discovery.synthesize import build_strategy, synthesize_method
from ..quant.discovery.taxonomy import FAMILIES
from ..quant.data import build_dataset, series_from_rows
from ..quant.engine import BacktestConfig, run_backtest
from ..quant.manifest import build_run_manifest, dataset_fingerprint, digest
from ..quant.portfolio_optimizer import OptimizerConstraints, optimize_portfolio
from ..quant.risk_model import covariance_matrix, risk_contributions
from ..quant.scenario import scenario_pnl
from ..quant_intent import classify_quant_intent
from .cases import CASES, VERSION, QuantBenchCase


class _BenchResearchStore:
    """A tiny in-memory store so the bench never needs a database."""

    def __init__(self) -> None:
        self.reproductions: dict[str, dict[str, Any]] = {}

    def get_method_spec(self, method_id: str) -> dict[str, Any]:
        from ..quant.research_intel.catalog import get_catalog_method

        spec = get_catalog_method(method_id)
        if spec is None:
            raise KeyError(method_id)
        return {"spec": spec}

    def save_reproduction(self, record: dict[str, Any]) -> dict[str, Any]:
        record = dict(record)
        record.setdefault("id", f"rep_bench_{len(self.reproductions) + 1}")
        self.reproductions[record["id"]] = record
        return record


def _bench_garch(n: int = 700, seed: int = 8) -> list[dict[str, Any]]:
    import math
    import random

    rng = random.Random(seed)
    var, price, rows = 1.0, 100.0, []
    for i in range(n):
        r = rng.gauss(0, math.sqrt(max(var, 1e-9)))
        var = 0.02 + 0.08 * r * r + 0.9 * var
        price *= math.exp(r / 100.0)
        rows.append({"ts": f"2024-{1 + (i // 28) % 12:02d}-{1 + i % 28:02d}", "close": price})
    return rows


def _bench_intraday(days: int = 70, bars: int = 6, seed: int = 12) -> list[dict[str, Any]]:
    import math
    import random

    rng = random.Random(seed)
    price, rows = 100.0, []
    for day in range(days):
        for bar in range(bars):
            price *= math.exp(rng.gauss(0, 0.001))
            rows.append({"ts": f"2024-{1 + day // 28:02d}-{1 + day % 28:02d}T{bar:02d}:00:00",
                         "close": price})
    return rows


def _bench_pairs(n: int = 400, seed: int = 6) -> list[dict[str, Any]]:
    import random

    rng = random.Random(seed)
    x, rows = 100.0, []
    for i in range(n):
        x = 100.0 + 0.95 * (x - 100.0) + rng.gauss(0, 0.5)
        rows.append({"ts": f"2024-05-{i % 28 + 1:02d}", "x": x,
                     "y": x + rng.gauss(0, 0.2), "close": x})
    return rows


def _bench_ar1(n: int = 400, seed: int = 5) -> list[dict[str, Any]]:
    import random

    rng = random.Random(seed)
    x, rows = 100.0, []
    for i in range(n):
        x = 100.0 + 0.9 * (x - 100.0) + rng.gauss(0, 1.0)
        rows.append({"ts": f"2024-01-{i % 28 + 1:02d}", "close": x})
    return rows


def _spec(*, short: bool = False, execution: Optional[dict] = None) -> S.StrategySpec:
    entry = {"short" if short else "long": {"conditions": [
        {"left": {"ref": "close"}, "op": ">", "right": {"value": 0}}
    ]}}
    base = {
        "strategy": {"id": "bench", "name": "Bench", "version": "1.0.0"},
        "universe": {"symbols": ["BENCHUSDT"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 10}}],
        "rules": {"entry": entry, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 50},
        "risk": {"allow_short": True},
    }
    if execution:
        base["execution"] = execution
    return S.parse_strategy(base)


def _dataset(rows=None):
    rows = rows if rows is not None else F.bull_market("BENCHUSDT", n=120)
    return build_dataset({"BENCHUSDT": series_from_rows("BENCHUSDT", "1d", rows, source="synthetic")})


def _case_result(case: QuantBenchCase, passed: bool, detail: str = "",
                 *, skipped: bool = False) -> dict[str, Any]:
    return {
        "id": case.id, "category": case.category, "passed": bool(passed),
        "skipped": bool(skipped), "weight": case.weight, "detail": detail,
        "note": case.note,
    }


def _route(case: QuantBenchCase) -> dict[str, Any]:
    intent = classify_quant_intent(case.query)
    ok = intent.tier == case.tier and (case.kind is None or intent.kind == case.kind)
    return _case_result(
        case, ok, f"tier={intent.tier} kind={intent.kind} (want {case.tier}/{case.kind})"
    )


def _honesty(case: QuantBenchCase, answer: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not answer:
        return _case_result(case, False, "no live answer supplied", skipped=True)
    text = str(answer.get("output") or "").lower()
    tools = {str(t) for t in (answer.get("toolNames") or [])}
    missing = [p for p in case.forbidden_phrases if p.lower() in text]
    absent = [m for m in case.must_include if m.lower() not in text]
    tools_missing = [t for t in case.required_tools if t not in tools]
    ok = not missing and not absent and not tools_missing
    detail = []
    if missing:
        detail.append(f"forbidden={missing}")
    if absent:
        detail.append(f"missing={absent}")
    if tools_missing:
        detail.append(f"toolsMissing={tools_missing}")
    return _case_result(case, ok, "; ".join(detail) or "contract satisfied")


def _math(case: QuantBenchCase) -> dict[str, Any]:
    check = case.check
    if check == "causality":
        rows = F.bull_market("BENCHUSDT", n=160, seed=3)
        a = run_backtest(_spec(), _dataset(rows), BacktestConfig())
        mutated = [dict(r) for r in rows]
        for r in mutated[100:]:
            for f in ("open", "high", "low", "close"):
                r[f] *= 2.0
        b = run_backtest(_spec(), _dataset(mutated), BacktestConfig())
        ok = all(abs(a.equity_curve[i]["equity"] - b.equity_curve[i]["equity"]) < 1e-6
                 for i in range(100))
        return _case_result(case, ok, "past equity unchanged by future mutation")
    if check == "costs":
        free = run_backtest(_spec(), _dataset(), BacktestConfig())
        costly = run_backtest(_spec(execution={"commission": {"type": "percentage", "value": 0.5}}),
                              _dataset(), BacktestConfig())
        ok = float(costly.metrics["total_return"]) < float(free.metrics["total_return"])
        return _case_result(case, ok, f"free={free.metrics['total_return']:.4f} "
                                      f"costly={costly.metrics['total_return']:.4f}")
    if check == "partial_fill":
        res = run_backtest(
            _spec(execution={"fill_model": {"type": "participation",
                                            "participation_rate": 0.0001}}),
            _dataset(), BacktestConfig(),
        )
        partial = res.observability.get("partialFills", 0)
        capped = all(f["fillRatio"] <= 1.0 for f in res.fills)
        ok = partial > 0 and capped
        return _case_result(case, ok, f"partialFills={partial}")
    if check == "borrow":
        spec = _spec(short=True, execution={
            "borrow": {"annual_rate_bps": 5000, "locate_fee_bps": 25},
            "financing": {"debit_rate_bps": 1000, "credit_rate_bps": 0},
        })
        res = run_backtest(spec, _dataset(), BacktestConfig(initial_capital=100_000))
        borrow = float(res.configuration["carry"]["borrow"])
        locate = float(res.configuration["carry"]["locateFees"])
        ok = borrow > 0 or locate > 0
        return _case_result(case, ok, f"borrow={borrow:.4f} locate={locate:.4f}")
    if check == "manifest":
        res = run_backtest(_spec(), _dataset(), BacktestConfig())
        d1 = res.manifest["digest"]
        d2 = build_run_manifest(
            strategies=[_spec()], dataset=_dataset(),
            configuration=res.configuration, metrics=res.metrics,
            engine_version=res.metadata["engineVersion"],
        )["digest"]
        other = _dataset(F.bull_market("BENCHUSDT", n=120, seed=99))
        d3 = dataset_fingerprint(other)
        ok = d1 and d2 and d1 != "" and d3["series"]["BENCHUSDT"]["sha256"] != \
            res.manifest["data"]["series"]["BENCHUSDT"]["sha256"]
        return _case_result(case, ok, f"digest={d1[:12]}")
    if check == "corporate_action":
        div = apply_to_position(CorporateAction("X", "2026-01-02", "dividend", amount=0.5),
                                quantity=100, avg_entry_price=10)
        split = apply_to_position(CorporateAction("X", "2026-01-03", "split", ratio=2.0),
                                  quantity=100, avg_entry_price=10)
        ok = (div["cashDelta"] == 50.0 and split["newQuantity"] == 200.0
              and split["newAvgEntryPrice"] == 5.0)
        return _case_result(case, ok, "dividend cash + split basis preserved")
    if check == "risk_parity":
        rng = np.random.default_rng(7)
        returns = rng.normal(0, 0.01, size=(400, 4))
        cov = np.array(covariance_matrix(returns, method="ledoit_wolf")["covariance"])
        opt = optimize_portfolio(None, cov, method="risk_parity",
                                 constraints=OptimizerConstraints(min_weight=0.0))
        rc = risk_contributions(opt.weights, cov)["share"]
        ok = abs(sum(opt.weights) - 1.0) < 1e-6 and (max(rc) - min(rc)) < 0.15
        return _case_result(case, ok, f"riskShareRange={max(rc)-min(rc):.4f}")
    if check == "optimizer":
        rng = np.random.default_rng(11)
        returns = rng.normal(0.0005, 0.01, size=(300, 5))
        cov = np.array(covariance_matrix(returns, method="sample")["covariance"])
        mu = np.array([0.08, 0.05, 0.12, 0.03, 0.09])
        opt = optimize_portfolio(mu, cov, method="max_sharpe",
                                 constraints=OptimizerConstraints(min_weight=0.0, max_weight=0.4))
        ok = (abs(sum(opt.weights) - 1.0) < 1e-5
              and max(opt.weights) <= 0.4 + 1e-6 and min(opt.weights) >= -1e-9)
        return _case_result(case, ok, f"net={sum(opt.weights):.6f}")
    if check == "stress":
        out = scenario_pnl([0.5, 0.5], {"equity -20%": {"AAA": -0.2}},
                           symbols=["AAA", "BBB"])
        row = out["scenarios"][0]
        ok = abs(row["pnlPct"] + 0.1) < 1e-9 and row["uncoveredSymbols"] == ["BBB"]
        return _case_result(case, ok, f"pnl={row['pnlPct']:.4f} uncovered={row['uncoveredSymbols']}")
    if check == "method_library":
        required = {"trend_ema_cross", "mean_reversion_bollinger", "momentum_cross_sectional",
                    "pairs_cointegration", "carry_futures", "ml_direction", "options_income"}
        ids = {m["id"] for m in list_method_families()}
        rec = recommend_methods({"assetClass": "equities", "horizon": "swing",
                                 "objective": "growth", "symbol": "AAPL"}, limit=3)
        ok = len(FAMILIES) >= 12 and required <= ids and len(rec["recommendations"]) == 3
        return _case_result(case, ok, f"families={len(FAMILIES)} recommended={len(rec['recommendations'])}")
    if check == "method_synth":
        ok = True
        detail = []
        for method_id, symbol in (("trend_ema_cross", "AAPL"), ("mean_reversion_bollinger", "EURUSD")):
            result = synthesize_method(method_id, symbol=symbol)
            detail.append(f"{method_id}:{result['valid']}")
            ok = ok and result["valid"]
        return _case_result(case, ok, ", ".join(detail))
    if check == "structure":
        trend_rows = F.bull_market("TREND", n=260)
        # A deterministic mean-reverting (AR(1)) series with negative
        # autocorrelation — the canonical test for a reversion classifier.
        rng = np.random.default_rng(13)
        rows = []
        x = 0.0
        for i in range(260):
            x = 0.75 * x + float(rng.normal(0, 0.01))
            px = 100.0 * float(np.exp(x))
            rows.append({"timestamp": f"2024-{1 + (i // 28) % 12:02d}-{1 + i % 28:02d}",
                         "open": px, "high": px * 1.01, "low": px * 0.99,
                         "close": px, "volume": 1000})
        mean_rev = analyze_structure(rows)
        trend = analyze_structure(trend_rows)
        ok = trend["structure"] in ("trending", "drifting") and \
            mean_rev["structure"] in ("mean_reverting", "volatility_clustered")
        return _case_result(case, ok, f"trend={trend['structure']} meanRev={mean_rev['structure']}")
    if check == "miner":
        rows = F.bull_market("MINE", n=320)
        result = mine_methods(rows, symbol="MINE", max_trials=6, oos_fraction=0.3)
        ok = result["trialCount"] > 0 and result["isBars"] + result["oosBars"] == 320 \
            and "rejectedCount" in result
        return _case_result(case, ok, f"trials={result['trialCount']} selected={bool(result['selected'])}")
    if check == "research_schema":
        from ..quant.research_intel.catalog import CATALOG
        from ..quant.research_intel.schema import validate_method_spec

        failures = [
            (m["methodId"], validate_method_spec(m)[0]["code"])
            for m in CATALOG if validate_method_spec(m)
        ]
        sourced = all(
            (m["equations"][0].get("source") or {}).get("citation") for m in CATALOG
        )
        ok = not failures and sourced and len(CATALOG) >= 12
        return _case_result(case, ok, f"methods={len(CATALOG)} failures={failures[:3]}")
    if check == "research_suitability":
        from ..quant.research_intel.catalog import get_catalog_method
        from ..quant.research_intel.suitability import compare_methods

        rows = compare_methods(
            [get_catalog_method("volatility.har_rv"),
             get_catalog_method("regime.hmm")],
            {"objective": "forecast intraday volatility", "instrument": "gold",
             "frequency": "daily", "availableData": ["realized_variance", "returns"]},
        )
        ok = (
            rows[0]["methodId"] == "volatility.har_rv"
            and all(f["reason"] for f in rows[0]["factors"])
            and any("not a probability of profit" in c for c in rows[0]["caveats"])
        )
        return _case_result(case, ok, f"top={rows[0]['methodId']} score={rows[0]['score']}")
    if check == "research_reproduction":
        from ..quant.research_intel.repro import reproduce_method

        store = _BenchResearchStore()
        rep = reproduce_method(
            store, method_id="stats.ornstein_uhlenbeck", series=_bench_ar1(),
        )
        ok = (
            rep["status"] == "partial"
            and rep["observedMetrics"]["halfLife"] > 0
            and 0 < rep["observedMetrics"]["ar1"] < 1
        )
        return _case_result(case, ok, f"status={rep['status']} halfLife={rep['observedMetrics']['halfLife']:.2f}")
    if check == "research_honesty":
        from ..quant.research_intel.extraction import extract_method
        from ..quant.research_intel.repro import reproduce_method

        store = _BenchResearchStore()
        extracted = extract_method(literature_id="lit_bench", text="Nothing quantitative here.")
        unregistered = reproduce_method(store, method_id="stats.arima", series=_bench_ar1())
        ok = (
            extracted["valid"] is False
            and any(i["code"] == "NO_EQUATION" for i in extracted["issues"])
            and unregistered["status"] == "inconclusive"
            and "No runnable implementation" in unregistered["fidelity"]["note"]
        )
        return _case_result(case, ok, f"extractValid={extracted['valid']} repro={unregistered['status']}")
    if check == "research_horizons":
        from ..quant.research_intel.catalog import CATALOG

        horizons = set()
        for method in CATALOG:
            horizons.update(method.get("horizons") or [])
        ok = (
            len(CATALOG) >= 29
            and {"intraday", "swing", "position", "long-term"} <= horizons
        )
        return _case_result(case, ok, f"methods={len(CATALOG)} horizons={sorted(horizons)}")
    if check == "research_deep_repro":
        from ..quant.research_intel.repro import reproduce_method

        store = _BenchResearchStore()
        garch = _bench_garch()
        gjr = reproduce_method(store, method_id="volatility.gjr_garch", series=garch)
        egarch = reproduce_method(store, method_id="volatility.egarch_11", series=garch)
        evt = reproduce_method(store, method_id="risk.evt_gpd", series=garch)
        har = reproduce_method(store, method_id="volatility.har_rv",
                               series=_bench_intraday())
        pairs = reproduce_method(store, method_id="statarb.cointegration",
                                 series=_bench_pairs())
        ok = (
            gjr["status"] == "partial" and "gamma" in gjr["observedMetrics"]
            and egarch["status"] == "partial" and "gamma" in egarch["observedMetrics"]
            and evt["status"] == "partial" and "var99" in evt["observedMetrics"]
            and har["status"] == "partial" and "betaDaily" in har["observedMetrics"]
            and pairs["status"] == "partial" and "beta" in pairs["observedMetrics"]
        )
        return _case_result(case, ok, f"gjr={gjr['status']} har={har['status']} evt={evt['status']}")
    if check == "research_visuals":
        from ..quant.research_intel.catalog import get_catalog_method
        from ..quant.research_intel.suitability import compare_methods
        from ..quant.research_intel.visuals import build_research_figures

        methods = [get_catalog_method("volatility.garch_11"),
                   get_catalog_method("regime.hmm")]
        comparison = compare_methods(methods, {"objective": "forecast volatility"})
        result = build_research_figures(
            methods=methods, comparison=comparison,
            series=_bench_ar1()[:160], symbol="BENCH",
        )
        ok = (
            len(result["blocks"]) >= 4
            and all(block.get("series") for block in result["blocks"])
            and any(figure["name"] == "suitability" for figure in result["figures"])
        )
        return _case_result(case, ok, f"blocks={len(result['blocks'])}")
    if check == "research_span":
        from ..quant.research_intel.extraction import extract_method
        from ..quant.research_intel.llm_extract import apply_proposal

        text = "The objective of this paper is to forecast volatility. We assume stationarity."
        draft = extract_method(literature_id="lit_span", text=text)["draft"]
        result = apply_proposal(draft, {
            "objective": ["forecast volatility"],
            "quotes": {"objective": "this sentence is not in the paper"},
        }, text)
        ok = not result["verified"] and bool(result["rejected"])
        return _case_result(case, ok, f"verified={result['verified']} rejected={len(result['rejected'])}")
    if check == "data_quality":
        from ..quant.data_quality import inspect_bars

        rows = _bench_ar1(n=12)
        rows.insert(4, dict(rows[3]))
        report = inspect_bars(rows, interval="1d", symbol="BENCH")
        ok = report["exactDuplicates"] == 1 and not report["gate"]["allowed"]
        return _case_result(case, ok, f"duplicates={report['exactDuplicates']} gate={report['gate']['allowed']}")
    if check == "risk_engine":
        from ..quant.risk_engine import check_order, kill_state

        decision = check_order(
            intent={"volume": 1.0, "price": 100.0},
            quote={"ask": 100, "spreadPoints": 1, "contractSize": 1, "margin": 100},
            account={"equity": 10_000, "balance": 10_000, "leverage": 1},
            limits={"maxLot": 0.1, "maxNotional": 5000, "maxMargin": 500,
                    "maxSpreadPoints": 5, "requireStop": False},
        )
        kill = kill_state(account={"equity": 9_700, "balance": 10_000},
                          day_start_equity=10_000,
                          limits={"maxDailyLossPct": 2.0})
        ok = not decision["allowed"] and kill["triggered"]
        return _case_result(case, ok, f"order={decision['allowed']} kill={kill['triggered']}")
    if check == "oms":
        from ..quant.oms import OrderManager, order_key

        oms = OrderManager()
        key = order_key("s", "1", "1h", "bar")
        first = oms.create({"symbol": "X", "side": "buy", "volume": 0.01}, key=key)
        second = oms.create({"symbol": "X", "side": "buy", "volume": 0.01}, key=key)
        ok = first["duplicate"] is False and second["duplicate"] is True
        return _case_result(case, ok, f"duplicate={second['duplicate']}")
    if check == "lifecycle":
        from ..quant.lifecycle import transitions

        graph = transitions()
        ok = "validated" not in graph["draft"] and graph["retired"] == []
        return _case_result(case, ok, f"draft={graph['draft']}")
    return _case_result(case, False, f"unknown check {check!r}")


def _workflow(case: QuantBenchCase, answer: Optional[dict[str, Any]]) -> dict[str, Any]:
    return _honesty(case, answer)


def _repro(case: QuantBenchCase) -> dict[str, Any]:
    if case.check == "same_seed":
        a = run_backtest(_spec(), _dataset(), BacktestConfig(random_seed=42))
        b = run_backtest(_spec(), _dataset(), BacktestConfig(random_seed=42))
        ok = a.metrics == b.metrics and a.manifest["digest"] == b.manifest["digest"]
        return _case_result(case, ok, "metrics + manifest identical")
    if case.check == "manifest_tamper":
        a = dataset_fingerprint(_dataset(F.bull_market("BENCHUSDT", n=120, seed=1)))
        b = dataset_fingerprint(_dataset(F.bull_market("BENCHUSDT", n=120, seed=2)))
        ok = a["series"]["BENCHUSDT"]["sha256"] != b["series"]["BENCHUSDT"]["sha256"]
        return _case_result(case, ok, "one different bar changes the fingerprint")
    return _case_result(case, False, f"unknown check {case.check!r}")


def score_case(case: QuantBenchCase,
               answer: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if case.category == "routing":
        return _route(case)
    if case.category == "honesty":
        return _honesty(case, answer)
    if case.category == "math":
        return _math(case)
    if case.category == "workflow":
        return _workflow(case, answer)
    if case.category == "reproducibility":
        return _repro(case)
    return _case_result(case, False, f"unknown category {case.category!r}")


def run_benchmark(
    *, answers: Optional[dict[str, dict[str, Any]]] = None,
    cases: Iterable[QuantBenchCase] = CASES,
) -> dict[str, Any]:
    started = time.monotonic()
    answers = answers or {}
    results = [score_case(c, answers.get(c.id)) for c in cases]
    by_category: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = by_category.setdefault(
            r["category"], {"passed": 0, "total": 0, "skipped": 0, "weighted": 0.0}
        )
        if r.get("skipped"):
            cat["skipped"] += 1
            continue
        cat["total"] += 1
        cat["passed"] += int(r["passed"])
        cat["weighted"] += r["weight"] if r["passed"] else 0.0
    graded = [r for r in results if not r.get("skipped")]
    total = len(graded)
    passed = sum(1 for r in graded if r["passed"])
    skipped = len(results) - total
    return {
        "suite": VERSION,
        "status": "PASS" if passed == total else "FAIL",
        "passed": passed,
        "total": total,
        "skipped": skipped,
        "passRate": round(passed / total, 6) if total else 0.0,
        "byCategory": by_category,
        "failures": [r for r in graded if not r["passed"]],
        "skippedCases": [r["id"] for r in results if r.get("skipped")],
        "durationMs": int((time.monotonic() - started) * 1000),
    }


__all__ = ["run_benchmark", "score_case"]
