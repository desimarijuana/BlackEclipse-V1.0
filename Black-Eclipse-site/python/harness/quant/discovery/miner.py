"""Systematic method search — discover, but count every trial.

The miner runs a bounded grid of method parameterizations on an in-sample slice,
then evaluates each on an untouched out-of-sample tail. It reports:

* every candidate, its parameters, IS and OOS metrics and why it passed/failed;
* the REAL trial count, and a Deflated Sharpe Ratio for the selected candidate
  that accounts for it;
* the IS→OOS divergence, so a fragile winner is visible.

It does not "find alpha" by magic. It finds candidates that survive a fair test,
and it says how many were tried. That is the difference between discovery and
data mining.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np

from ..data import build_dataset, series_from_rows
from ..engine import BacktestConfig, run_backtest
from ..errors import QuantError
from ..multiple_testing import deflated_sharpe
from ..validation import returns_from_equity
from .synthesize import build_strategy, build_combination
from .taxonomy import FAMILIES, family_by_id

_BUILDABLE = [f.id for f in FAMILIES if f.builder in
              ("ema_cross", "donchian", "bollinger", "rsi", "vol_breakout")]

_GRIDS: dict[str, list[dict[str, Any]]] = {
    "trend_ema_cross": [
        {"fast": f, "slow": s}
        for f, s in ((10, 50), (20, 50), (20, 100), (50, 200))
    ],
    "trend_donchian_breakout": [{"lookback": 20}, {"lookback": 55}],
    "mean_reversion_bollinger": [{"entry_z": 1.5}, {"entry_z": 2.0}, {"entry_z": 2.5}],
    "mean_reversion_rsi": [{"oversold": 30, "overbought": 70},
                           {"oversold": 25, "overbought": 75}],
    "volatility_breakout": [{"breakout_lookback": 20}, {"breakout_lookback": 55}],
}


def _split_rows(rows: list[dict[str, Any]], oos_fraction: float) -> tuple[list, list]:
    if not 0 < oos_fraction < 1:
        raise QuantError("oos_fraction must be in (0, 1)")
    n = len(rows)
    cut = int(n * (1.0 - oos_fraction))
    if cut < 40 or n - cut < 20:
        raise QuantError("not enough bars for an in-sample / out-of-sample split",
                         detail={"bars": n, "isBars": cut, "oosBars": n - cut})
    return rows[:cut], rows[cut:]


def _run(spec: dict[str, Any], symbol: str, rows: list[dict[str, Any]],
         interval: str) -> dict[str, Any]:
    dataset = build_dataset({symbol: series_from_rows(symbol, interval, rows, source="discovery")})
    from ..strategy import parse_strategy  # noqa: PLC0415
    result = run_backtest(parse_strategy(spec), dataset, BacktestConfig())
    return {
        "sharpe": result.metrics.get("sharpe"),
        "totalReturn": result.metrics.get("total_return"),
        "maxDrawdown": result.metrics.get("max_drawdown"),
        "tradeCount": result.metrics.get("trade_count"),
        "returns": returns_from_equity([p["equity"] for p in result.equity_curve]),
        "experimentLike": result.metrics,
    }


def _score(is_m: dict[str, Any], oos_m: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    sharpe = oos_m.get("sharpe")
    trades = oos_m.get("tradeCount") or 0
    ret = oos_m.get("totalReturn")
    if sharpe is None or trades < 3:
        return -99.0, ["too few out-of-sample trades to judge"]
    score = float(sharpe)
    if (is_m.get("sharpe") or 0) > 0:
        score += 0.25
    else:
        reasons.append("in-sample Sharpe was not positive")
    if ret is not None and ret > 0:
        score += 0.25
    else:
        reasons.append("out-of-sample return was not positive")
    divergence = float(is_m.get("sharpe") or 0) - float(sharpe)
    if divergence > 0.75:
        score -= 0.5
        reasons.append(f"large IS→OOS Sharpe divergence ({divergence:.2f})")
    return score, reasons


def _status(score: float, oos_m: dict[str, Any]) -> str:
    if (oos_m.get("tradeCount") or 0) < 3:
        return "rejected"
    if score >= 1.0:
        return "candidate"
    if score > 0:
        return "weak"
    return "rejected"


def mine_methods(rows: list[dict[str, Any]], *, symbol: str, interval: str = "1d",
                 method_ids: Optional[Iterable[str]] = None,
                 max_trials: int = 24, oos_fraction: float = 0.3,
                 combinations: int = 0) -> dict[str, Any]:
    """Run a bounded discovery search over method parameterizations."""
    if not rows:
        raise QuantError("no bars supplied")
    is_rows, oos_rows = _split_rows(rows, oos_fraction)
    ids = [m for m in (method_ids or _BUILDABLE) if m in _GRIDS]
    if not ids:
        raise QuantError("no buildable method ids supplied",
                         detail={"buildable": _BUILDABLE})

    trials: list[dict[str, Any]] = []
    limit = max(1, int(max_trials))
    for method_id in ids:
        for params in _GRIDS[method_id]:
            if len(trials) >= limit:
                break
            try:
                spec = build_strategy(method_id, symbol=symbol, interval=interval,
                                      params=params)
                is_m = _run(spec, symbol, is_rows, interval)
                oos_m = _run(spec, symbol, oos_rows, interval)
                score, reasons = _score(is_m, oos_m)
                trials.append({
                    "methodId": method_id,
                    "name": family_by_id(method_id).name if family_by_id(method_id) else method_id,
                    "params": params,
                    "spec": spec,
                    "status": _status(score, oos_m),
                    "score": round(score, 4),
                    "reasons": reasons,
                    "inSample": {k: is_m.get(k) for k in
                                 ("sharpe", "totalReturn", "maxDrawdown", "tradeCount")},
                    "outOfSample": {k: oos_m.get(k) for k in
                                    ("sharpe", "totalReturn", "maxDrawdown", "tradeCount")},
                    "_returns": oos_m.get("returns") or [],
                })
            except Exception as exc:  # noqa: BLE001 - a bad candidate is evidence
                trials.append({
                    "methodId": method_id, "params": params, "status": "error",
                    "score": -99.0, "reasons": [str(exc)],
                })
        if len(trials) >= limit:
            break

    # Optional compositions: pair the best trend method with a filter method.
    if combinations > 0 and len(trials) >= 2:
        ordered = sorted([t for t in trials if t.get("spec")], key=lambda t: -t["score"])
        if len(ordered) >= 2:
            try:
                spec = build_combination(
                    ordered[0]["methodId"], ordered[1]["methodId"],
                    symbol=symbol, interval=interval,
                    primary_params=ordered[0]["params"],
                    filter_params=ordered[1]["params"],
                )
                is_m = _run(spec, symbol, is_rows, interval)
                oos_m = _run(spec, symbol, oos_rows, interval)
                score, reasons = _score(is_m, oos_m)
                trials.append({
                    "methodId": f"{ordered[0]['methodId']}+{ordered[1]['methodId']}",
                    "name": "Combined method",
                    "params": {"primary": ordered[0]["params"], "filter": ordered[1]["params"]},
                    "spec": spec, "status": _status(score, oos_m),
                    "score": round(score, 4), "reasons": reasons + ["a NEW composition"],
                    "inSample": {k: is_m.get(k) for k in
                                 ("sharpe", "totalReturn", "maxDrawdown", "tradeCount")},
                    "outOfSample": {k: oos_m.get(k) for k in
                                    ("sharpe", "totalReturn", "maxDrawdown", "tradeCount")},
                    "_returns": oos_m.get("returns") or [],
                })
            except Exception:  # noqa: BLE001
                pass

    valid = [t for t in trials if t.get("status") in ("candidate", "weak")]
    valid.sort(key=lambda t: -t["score"])
    selected = valid[0] if valid else None
    trial_sharpes = []
    for t in trials:
        is_sharpe = (t.get("inSample") or {}).get("sharpe")
        if is_sharpe is not None:
            trial_sharpes.append(float(is_sharpe) / np.sqrt(252.0))  # per-period
    dsr = None
    if selected and selected.get("_returns"):
        dsr = deflated_sharpe(
            [float(x) for x in selected["_returns"]],
            trial_sharpes=trial_sharpes if len(trial_sharpes) >= 2 else None,
        )
    for t in trials:
        t.pop("_returns", None)
    return {
        "symbol": symbol,
        "interval": interval,
        "isBars": len(is_rows),
        "oosBars": len(oos_rows),
        "trialCount": len(trials),
        "maxTrials": limit,
        "candidates": valid,
        "selected": selected,
        "rejectedCount": len([t for t in trials if t["status"] in ("rejected", "error")]),
        "allTrials": trials,
        "deflatedSharpe": dsr,
        "warnings": [
            "the search is bounded but the trial count is real; the Deflated "
            "Sharpe Ratio accounts for it",
            "a candidate is not a validated strategy: run walk-forward, robustness, "
            "cost stress and out-of-sample checks before promoting it",
        ],
        "note": "discovery output; the evidence still has to clear the normal gates",
    }


__all__ = ["mine_methods"]
