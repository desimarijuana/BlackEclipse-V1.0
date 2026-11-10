"""Desk tools — the new research, portfolio and reproducibility surfaces.

Kept in a separate module so `tools.py` stays under its size budget. Every tool
is a thin adapter over the deterministic modules; none computes a statistic of
its own. Registration happens from `tools.register_quant_tools`.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import QuantError
from .manifest import compare_metrics

DESK_TOOLS: tuple[str, ...] = (
    "get_run_manifest", "reproduce_experiment",
    "start_research_session", "pre_register_hypothesis", "record_trial",
    "research_journal", "list_research_sessions",
    "optimize_portfolio", "analyze_portfolio_risk", "stress_portfolio",
    "backtest_option_chain", "futures_term_structure", "futures_roll_cost",
    "export_research_report", "run_quant_bench",
)


def _store(ctx: Any):
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise QuantError("the quant store is not configured in this runtime")
    return store


def _gateway(ctx: Any):
    from ..market.tools import _gateway as market_gateway  # noqa: PLC0415

    return market_gateway(ctx)


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}",
                {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


# ── Reproducibility ──────────────────────────────────────────────────────────

async def get_run_manifest(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        manifest = store.get_run_manifest(str(args["experimentId"]))
        text = (f"Run manifest {args['experimentId']}\n"
                f"Digest: {manifest.get('digest')}\n"
                f"Engine: {manifest.get('engineVersion')} | "
                f"data bars: {sum(s.get('bars', 0) for s in manifest.get('data', {}).get('series', {}).values())}\n"
                f"Strategies: {', '.join(s.get('id', '?') + '@' + str(s.get('version')) for s in manifest.get('strategies', []))}")
        return text, {"status": "OK", "manifest": manifest}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def reproduce_experiment(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .datasets import dataset_from_strategy  # noqa: PLC0415
        from .engine import BacktestConfig, run_backtest  # noqa: PLC0415

        store = _store(ctx)
        exp_id = str(args["experimentId"])
        experiment = store.get_experiment(exp_id)
        manifest = store.get_run_manifest(exp_id)
        strategy_id = experiment.get("strategyId")
        version = experiment.get("strategyVersion")
        if not strategy_id:
            raise QuantError("this experiment has no strategy id and cannot be reproduced",
                             detail={"experimentId": exp_id})
        record = store.get_strategy(strategy_id, version)
        from .strategy import parse_strategy  # noqa: PLC0415
        strategy = parse_strategy(record["spec"])
        cfg = experiment.get("configuration") or {}
        dataset = await dataset_from_strategy(
            _gateway(ctx), strategy, start=cfg.get("start"), end=cfg.get("end"),
            symbols=experiment.get("symbols"),
        )
        config = BacktestConfig(
            initial_capital=float(cfg.get("initialCapital") or 100_000),
            start=cfg.get("start"), end=cfg.get("end"),
            risk_free_rate=float(cfg.get("riskFreeRate") or 0.0),
            random_seed=int(cfg.get("randomSeed") or 42),
        )
        result = run_backtest(strategy, dataset, config)
        comparison = compare_metrics(experiment.get("metrics") or {}, result.metrics)
        fingerprint_match = (
            manifest.get("data", {}).get("series", {})
            == result.manifest.get("data", {}).get("series", {})
        )
        status = "REPRODUCED" if comparison["reproduced"] and fingerprint_match else "DIVERGED"
        text = (f"Reproduction {status} for {exp_id}\n"
                f"metrics compared: {comparison['compared']} | differences: "
                f"{len(comparison['differences'])} | data fingerprint match: {fingerprint_match}")
        return text, {
            "status": "OK", "verdict": status, "comparison": comparison,
            "dataFingerprintMatch": fingerprint_match,
            "manifest": result.manifest,
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Research sessions ────────────────────────────────────────────────────────

async def start_research_session(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        session = _store(ctx).create_research_session(
            title=str(args.get("title") or "Untitled research session"),
            question=args.get("question"), strategy_id=args.get("strategyId"),
        )
        return (f"Research session {session['id']} created: {session['title']}",
                {"status": "OK", "session": session})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def pre_register_hypothesis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        hyp = _store(ctx).pre_register_hypothesis(
            str(args["sessionId"]), statement=str(args["statement"]),
            universe=args.get("universe"), period=args.get("period"),
            metric=args.get("metric"), acceptance=args.get("acceptance"),
        )
        return (f"Hypothesis {hyp['id']} registered BEFORE testing: {hyp['statement']}",
                {"status": "OK", "hypothesis": hyp})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def record_trial(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        trial = _store(ctx).record_trial(
            str(args["sessionId"]), kind=str(args.get("kind") or "backtest"),
            hypothesis_id=args.get("hypothesisId"),
            experiment_id=args.get("experimentId"),
            parameters=args.get("parameters"), metrics=args.get("metrics"),
        )
        return (f"Trial {trial['id']} recorded ({trial['kind']}); the trial ledger now "
                f"feeds multiple-testing diagnostics",
                {"status": "OK", "trial": trial})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_journal(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        journal = _store(ctx).session_journal(str(args["sessionId"]))
        text = (f"Research journal {journal['session']['id']}: "
                f"{journal['hypothesisCount']} hypotheses, {journal['trialCount']} trials\n"
                f"Tested: {journal['testedHypotheses']} | rejected: {len(journal['rejectedHypotheses'])}")
        return text, {"status": "OK", "journal": journal}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_research_sessions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        sessions = _store(ctx).list_research_sessions(
            limit=int(args.get("limit") or 50), status=args.get("status")
        )
        return (f"{len(sessions)} research sessions", {"status": "OK", "sessions": sessions})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Portfolio & risk ─────────────────────────────────────────────────────────

async def optimize_portfolio_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .portfolio_optimizer import (  # noqa: PLC0415
            OptimizerConstraints, optimize_portfolio,
        )
        c = OptimizerConstraints(
            min_weight=args.get("minWeight"), max_weight=args.get("maxWeight"),
            net=float(args.get("net", 1.0)), gross=args.get("gross"),
            max_turnover=args.get("maxTurnover"),
            current_weights=args.get("currentWeights"),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
        )
        result = optimize_portfolio(
            args.get("expectedReturns"), args["covariance"],
            method=str(args.get("method") or "min_variance"),
            constraints=c, risk_aversion=float(args.get("riskAversion") or 1.0),
            views=args.get("views"),
        )
        text = (f"Portfolio ({result.method}): weights "
                f"{[round(w, 4) for w in result.weights]}\n"
                f"Expected return {result.expected_return} | volatility {result.volatility} | "
                f"Sharpe {result.sharpe} | feasible {result.diagnostics.get('feasible')}")
        return text, {"status": "OK", **result.to_dict()}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def analyze_portfolio_risk(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .risk_model import (  # noqa: PLC0415
            covariance_matrix, factor_exposures, risk_contributions,
        )
        if args.get("returns") is not None:
            cov = covariance_matrix(
                args["returns"], method=str(args.get("method") or "ledoit_wolf"),
                annualize=bool(args.get("annualize", True)),
                interval=str(args.get("interval") or "1d"),
            )
        else:
            cov = {"covariance": args["covariance"], "method": "supplied"}
        weights = args["weights"]
        contributions = risk_contributions(weights, cov["covariance"])
        payload: dict[str, Any] = {
            "status": "OK", "covariance": cov, "riskContributions": contributions,
        }
        if args.get("assetReturns") is not None and args.get("factorReturns") is not None:
            payload["factorExposures"] = factor_exposures(
                args["assetReturns"], args["factorReturns"]
            )
        text = (f"Portfolio volatility {contributions['volatility']:.6f}; "
                f"largest risk contributor share {max(contributions['share']):.3f}")
        return text, payload
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def stress_portfolio(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .scenario import historical_risk, parametric_risk, scenario_pnl  # noqa: PLC0415
        payload: dict[str, Any] = {"status": "OK"}
        if args.get("covariance") is not None:
            payload["parametric"] = parametric_risk(
                args["weights"], args["covariance"],
                confidence=float(args.get("confidence") or 0.95),
                horizon_days=float(args.get("horizonDays") or 1),
                portfolio_value=float(args.get("portfolioValue") or 1),
            )
        if args.get("returns") is not None:
            payload["historical"] = historical_risk(
                args["returns"], args["weights"],
                confidence=float(args.get("confidence") or 0.95),
                portfolio_value=float(args.get("portfolioValue") or 1),
            )
        if args.get("scenarios"):
            payload["scenario"] = scenario_pnl(
                args["weights"], args["scenarios"], symbols=args.get("symbols"),
                portfolio_value=float(args.get("portfolioValue") or 1),
            )
        if not any(k in payload for k in ("parametric", "historical", "scenario")):
            raise QuantError("supply covariance, returns or scenarios")
        text = "Stress envelope computed"
        if "parametric" in payload:
            text += f" | VaR {payload['parametric']['varPct']:.4f}"
        if "scenario" in payload and payload["scenario"].get("worst"):
            text += f" | worst scenario {payload['scenario']['worst']['name']}"
        return text, payload
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Asset-class extensions ───────────────────────────────────────────────────

async def backtest_option_chain_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .options_backtest import backtest_option_chain  # noqa: PLC0415
        result = backtest_option_chain(
            args["snapshots"], initial_capital=float(args.get("initialCapital") or 100_000),
            commission_per_contract=args.get("commissionPerContract"),
        )
        text = (f"Option-chain backtest: return {result['metrics']['totalReturn']:.4f}% | "
                f"max drawdown {result['metrics']['maxDrawdown']:.4f}% | "
                f"settled at expiry: {result['settledAtExpiry']}")
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def futures_term_structure_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .futures import term_structure  # noqa: PLC0415
        result = term_structure(
            args["points"], spot=args.get("spot"),
            risk_free=float(args.get("riskFree") or 0.0),
            storage=float(args.get("storage") or 0.0),
        )
        return (f"Futures curve is {result['shape']} across {len(result['points'])} points",
                {"status": "OK", **result})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def futures_roll_cost_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .futures import roll_cost  # noqa: PLC0415
        result = roll_cost(
            args["contracts"], args["rollDates"],
            adjustment=str(args.get("adjustment") or "difference"),
            cost_bps=float(args.get("costBps") or 0.0),
            initial_capital=float(args.get("initialCapital") or 100_000),
        )
        return (f"{result['rollCount']} rolls; explicit cost {result['totalCost']:.4f}",
                {"status": "OK", **result})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def export_research_report_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .report_export import export_experiment  # noqa: PLC0415
        result = export_experiment(
            _store(ctx), str(args["experimentId"]),
            fmt=str(args.get("format") or "html"),
        )
        return (f"Exported {result['format']} report for {args['experimentId']} to {result['path']}",
                {"status": "OK", **result})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Benchmark ────────────────────────────────────────────────────────────────

async def run_quant_bench_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from ..quant_bench.runner import run_benchmark  # noqa: PLC0415
        report = run_benchmark(answers=args.get("answers") or {})
        text = (f"QuantBench {report['suite']}: {report['status']} "
                f"({report['passed']}/{report['total']}, {report['passRate']:.1%})")
        return text, {"status": "OK", "report": report}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def register_desk_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 30_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout,
        ))

    _def("get_run_manifest",
         "Return the content-hashed reproducibility manifest for an experiment "
         "(data fingerprint, code/engine version, dependency versions, seed, assumptions).",
         get_run_manifest, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]})
    _def("reproduce_experiment",
         "Re-run a stored experiment from its manifest and compare metrics and the data "
         "fingerprint. Returns REPRODUCED or DIVERGED with every differing metric.",
         reproduce_experiment, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]}, 120_000)
    _def("start_research_session",
         "Open a persistent research session (question, hypotheses, trials, journal) so a "
         "multi-turn research program is auditable.",
         start_research_session, {"type": "object", "properties": {
             "title": {"type": "string"}, "question": {"type": "string"},
             "strategyId": {"type": "string"}}, "required": ["title"]})
    _def("pre_register_hypothesis",
         "Record a hypothesis and its acceptance criterion BEFORE testing it. This is the "
         "anti-p-hacking contract; the trial ledger keeps the count honest.",
         pre_register_hypothesis, {"type": "object", "properties": {
             "sessionId": {"type": "string"}, "statement": {"type": "string"},
             "universe": {"type": "array", "items": {"type": "string"}},
             "period": {"type": "object"}, "metric": {"type": "string"},
             "acceptance": {"type": "string"}},
             "required": ["sessionId", "statement"]})
    _def("record_trial",
         "Record one tested configuration in a research session. The ledger feeds the "
         "multiple-testing diagnostics with the REAL number of trials.",
         record_trial, {"type": "object", "properties": {
             "sessionId": {"type": "string"}, "kind": {"type": "string"},
             "hypothesisId": {"type": "string"}, "experimentId": {"type": "string"},
             "parameters": {"type": "object"}, "metrics": {"type": "object"}},
             "required": ["sessionId"]})
    _def("research_journal",
         "Return a session's hypotheses, trials, rejected ideas and open questions.",
         research_journal, {"type": "object", "properties": {
             "sessionId": {"type": "string"}}, "required": ["sessionId"]})
    _def("list_research_sessions",
         "List persistent research sessions.",
         list_research_sessions, {"type": "object", "properties": {
             "limit": {"type": "integer"}, "status": {"type": "string"}}})
    _def("optimize_portfolio",
         "Construct portfolio weights (min-variance/mean-variance/max-Sharpe/risk-parity/"
         "HRP/Black-Litterman) under explicit net, gross, bound and turnover constraints.",
         optimize_portfolio_tool, {"type": "object", "properties": {
             "expectedReturns": {"type": "array", "items": {"type": "number"}},
             "covariance": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "method": {"type": "string", "enum": [
                 "equal_weight", "min_variance", "mean_variance", "max_sharpe",
                 "risk_parity", "hrp", "black_litterman"]},
             "riskAversion": {"type": "number"}, "net": {"type": "number"},
             "gross": {"type": "number"}, "minWeight": {"type": "number"},
             "maxWeight": {"type": "number"}, "maxTurnover": {"type": "number"},
             "currentWeights": {"type": "array", "items": {"type": "number"}},
             "views": {"type": "object"}, "riskFreeRate": {"type": "number"}},
             "required": ["covariance"]})
    _def("analyze_portfolio_risk",
         "Estimate covariance (sample/EWMA/Ledoit-Wolf), risk contributions and factor "
         "exposures for a weighted portfolio.",
         analyze_portfolio_risk, {"type": "object", "properties": {
             "weights": {"type": "array", "items": {"type": "number"}},
             "returns": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "covariance": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "method": {"type": "string"}, "annualize": {"type": "boolean"},
             "interval": {"type": "string"},
             "assetReturns": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "factorReturns": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}},
             "required": ["weights"]})
    _def("stress_portfolio",
         "Parametric/historical VaR-ES, component VaR, and explicit asset/factor scenario "
         "P&L. Names uncovered assets instead of assuming zero.",
         stress_portfolio, {"type": "object", "properties": {
             "weights": {"type": "array", "items": {"type": "number"}},
             "covariance": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "returns": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "scenarios": {"type": "object"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "confidence": {"type": "number"}, "horizonDays": {"type": "number"},
             "portfolioValue": {"type": "number"}}, "required": ["weights"]})
    _def("backtest_option_chain",
         "Backtest a multi-leg option position over dated chain snapshots, marked with "
         "Black-Scholes and settled at expiry. European exercise; not a surface fill model.",
         backtest_option_chain_tool, {"type": "object", "properties": {
             "snapshots": {"type": "array", "items": {"type": "object"}},
             "initialCapital": {"type": "number"},
             "commissionPerContract": {"type": "number"}},
             "required": ["snapshots"]}, 60_000)
    _def("futures_term_structure",
         "Describe a futures curve (contango/backwardation) and its implied carry.",
         futures_term_structure_tool, {"type": "object", "properties": {
             "points": {"type": "array", "items": {"type": "object"}},
             "spot": {"type": "number"}, "riskFree": {"type": "number"},
             "storage": {"type": "number"}}, "required": ["points"]})
    _def("futures_roll_cost",
         "Splice a continuous futures series and quantify the explicit roll transaction "
         "cost separately from the market roll gap.",
         futures_roll_cost_tool, {"type": "object", "properties": {
             "contracts": {"type": "array", "items": {"type": "object"}},
             "rollDates": {"type": "array", "items": {"type": "string"}},
             "adjustment": {"type": "string"}, "costBps": {"type": "number"},
             "initialCapital": {"type": "number"}},
             "required": ["contracts", "rollDates"]})
    _def("export_research_report",
         "Export a stored experiment as a self-contained HTML report or a replayable "
         "notebook, with metrics, assumptions, warnings and the run digest.",
         export_research_report_tool, {"type": "object", "properties": {
             "experimentId": {"type": "string"},
             "format": {"type": "string", "enum": ["html", "notebook"]}},
             "required": ["experimentId"]})
    _def("run_quant_bench",
         "Run the deterministic QuantBench suite (routing, math invariants, reproducibility) "
         "and return the scorecard. Live honesty cases require supplied answers.",
         run_quant_bench_tool, {"type": "object", "properties": {
             "answers": {"type": "object"}}, }, 120_000)
    return list(DESK_TOOLS)


__all__ = ["DESK_TOOLS", "register_desk_tools"]
