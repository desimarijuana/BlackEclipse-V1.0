"""GTJA191 — the subset whose published formula is reproduced here exactly.

Guotai Junan's *191 Alphas* (国泰君安 191 阿尔法) is a large technical-alpha
library. Only formulas that can be transcribed without interpretation are ported:
a wrong alpha number under a familiar name is worse than a missing entry, because
its IC would look like evidence for a factor nobody actually published.

Ported (5 of 191):

  * **#1** — cross-sectional rank of the volume/log-change signal correlated with
    the intraday move. Needs the universe panel (`requiresPanel`).
  * **#2** — the one-day change in the close-location expression (series).
  * **#5** — the maximum over 3 days of the 5-day rank correlation between
    volume rank and high rank (panel).
  * **#6** — minus the cross-sectional rank of the sign of a 4-day change in a
    weighted open/high price (panel).
  * **#11** — volume-weighted close-location summed over 6 days (series).

Not ported: the remaining 186. Many depend on `VWAP`, `AMOUNT`, `BENCHMARKINDEX`
or on GTJA's own operator definitions (`TSRANK`, `SIGN`, `SUM`, `MAX`) whose
precise edge behaviour differs between published revisions. Those need a primary
source and operator-by-operator reconciliation, not a guess.
"""

from __future__ import annotations

from typing import Any

ZOO = "gtja191"
SOURCE = "GTJA 191 (Guotai Junan) — re-implemented on harness.stats.formula"
REFERENCE = "国泰君安 191 阿尔法 (GTJA 191)"
TOTAL = 191


def _alpha(
    number: int,
    name: str,
    family: str,
    direction: str,
    lookback: int,
    description: str,
    expression: str,
    inputs: list[str],
    *,
    requires_panel: bool = False,
    requires_inputs: tuple[str, ...] = (),
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "family": family,
        "direction": direction,
        "lookback": lookback,
        "description": description,
        "expression": expression,
        "inputs": inputs,
        "available": True,
        "zoo": ZOO,
        "source": SOURCE,
        "reference": f"{REFERENCE} #{number}",
        "alphaNumber": number,
    }
    if requires_panel:
        record["requiresPanel"] = True
    if requires_inputs:
        record["requiresInputs"] = list(requires_inputs)
    return record


_BASE_FACTORS: list[dict[str, Any]] = [
    _alpha(
        1, "gtja_alpha1", "volume", "positive", 7,
        "GTJA #1: -CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6).",
        "0 - correlation(rank(delta(log(volume), 1)), rank((close - open) / open), 6)",
        ["volume", "open", "close"], requires_panel=True,
    ),
    _alpha(
        2, "gtja_alpha2", "reversal", "positive", 2,
        "GTJA #2: -DELTA(((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW), 1).",
        "0 - delta(((close - low) - (high - close)) / (high - low), 1)",
        ["high", "low", "close"],
    ),
    _alpha(
        5, "gtja_alpha5", "volume", "positive", 10,
        "GTJA #5: -TSMAX(CORR(TSRANK(VOLUME,5), TSRANK(HIGH,5), 5), 3).",
        "0 - rolling_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3)",
        ["volume", "high"], requires_panel=True,
    ),
    _alpha(
        6, "gtja_alpha6", "reversal", "positive", 5,
        "GTJA #6: -RANK(SIGN(DELTA(OPEN*0.85 + HIGH*0.15, 4))).",
        "0 - rank(sign(delta(open * 0.85 + high * 0.15, 4)))",
        ["open", "high"], requires_panel=True,
    ),
    _alpha(
        11, "gtja_alpha11", "volume", "positive", 6,
        "GTJA #11: SUM(((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW) * VOLUME, 6) — a "
        "rolling SUM, not a mean; the two differ by a factor of six.",
        "ts_sum(((close - low) - (high - close)) / (high - low) * volume, 6)",
        ["high", "low", "close", "volume"],
    ),
    # -- tranche 2: verified against a published GTJA191 implementation
    # (lrb777/gtja191, `src/factors/alpha_001_050.py`), whose comments carry the
    # Chinese-alpha formula for each number. Only formulas whose operators map
    # one-to-one onto this DSL are taken; GTJA's own `SMA(X,N,M)` (a Wilder
    # recursive mean, NOT this DSL's `sma`) and `WMA` are deliberately excluded,
    # because silently substituting a simple mean would change the alpha.
    _alpha(
        8, "gtja_alpha8", "reversal", "positive", 5,
        "GTJA #8: -RANK(DELTA((HIGH+LOW)/2*0.2 + VWAP*0.8, 4)).",
        "0 - rank(delta((high + low) / 2 * 0.2 + vwap * 0.8, 4))",
        ["high", "low", "vwap"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        12, "gtja_alpha12", "reversal", "positive", 10,
        "GTJA #12: RANK(OPEN - SUM(VWAP,10)/10) * (-1*RANK(ABS(CLOSE-VWAP))).",
        "rank(open - sma(vwap, 10)) * (0 - rank(abs(close - vwap)))",
        ["open", "vwap", "close"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        13, "gtja_alpha13", "reversal", "positive", 1,
        "GTJA #13: (HIGH*LOW)^0.5 - VWAP — the bar's geometric mid against where "
        "volume traded.",
        "sqrt(high * low) - vwap",
        ["high", "low", "vwap"], requires_inputs=("vwap",),
    ),
    _alpha(
        14, "gtja_alpha14", "momentum", "positive", 6,
        "GTJA #14: CLOSE - DELAY(CLOSE,5) — the raw five-day change.",
        "close - lag(close, 5)", ["close"],
    ),
    _alpha(
        15, "gtja_alpha15", "reversal", "positive", 2,
        "GTJA #15: OPEN/DELAY(CLOSE,1) - 1 — the overnight gap.",
        "open / lag(close, 1) - 1", ["open", "close"],
    ),
    _alpha(
        18, "gtja_alpha18", "momentum", "positive", 6,
        "GTJA #18: CLOSE/DELAY(CLOSE,5) — the five-day price ratio.",
        "close / lag(close, 5)", ["close"],
    ),
    _alpha(
        20, "gtja_alpha20", "momentum", "positive", 7,
        "GTJA #20: (CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*100 — six-day change in "
        "percent.",
        "(close - lag(close, 6)) / lag(close, 6) * 100", ["close"],
    ),
    _alpha(
        29, "gtja_alpha29", "volume", "positive", 7,
        "GTJA #29: (CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*VOLUME — the six-day change "
        "weighted by participation.",
        "(close - lag(close, 6)) / lag(close, 6) * volume", ["close", "volume"],
    ),
    _alpha(
        31, "gtja_alpha31", "reversal", "negative", 12,
        "GTJA #31: (CLOSE-MEAN(CLOSE,12))/MEAN(CLOSE,12)*100 — deviation from the "
        "twelve-day mean, in percent.",
        "(close - sma(close, 12)) / sma(close, 12) * 100", ["close"],
    ),
    _alpha(
        33, "gtja_alpha33", "reversal", "positive", 240,
        "GTJA #33: (-TSMIN(LOW,5)+DELAY(TSMIN(LOW,5),5)) * "
        "RANK((SUM(RET,240)-SUM(RET,20))/220) * TSRANK(VOLUME,5).",
        "((0 - rolling_min(low, 5)) + lag(rolling_min(low, 5), 5)) * "
        "rank((ts_sum(pct_change(close, 1), 240) - "
        "ts_sum(pct_change(close, 1), 20)) / 220) * ts_rank(volume, 5)",
        ["low", "close", "volume"], requires_panel=True,
    ),
    _alpha(
        34, "gtja_alpha34", "reversal", "negative", 12,
        "GTJA #34: MEAN(CLOSE,12)/CLOSE.",
        "sma(close, 12) / close", ["close"],
    ),
    _alpha(
        38, "gtja_alpha38", "reversal", "positive", 20,
        "GTJA #38: (SUM(HIGH,20)/20 < HIGH) ? -1*DELTA(HIGH,2) : 0.",
        "where(less_than(sma(high, 20), high), 0 - delta(high, 2), 0)",
        ["high"],
    ),
    _alpha(
        42, "gtja_alpha42", "volume", "negative", 10,
        "GTJA #42: -1*RANK(STD(HIGH,10)) * CORR(HIGH, VOLUME, 10).",
        "(0 - rank(rolling_std(high, 10))) * correlation(high, volume, 10)",
        ["high", "volume"], requires_panel=True,
    ),
    _alpha(
        43, "gtja_alpha43", "volume", "positive", 6,
        "GTJA #43: SUM(CLOSE>DELAY(CLOSE,1) ? VOLUME : (CLOSE<DELAY(CLOSE,1) ? "
        "-VOLUME : 0), 6) — signed volume over six days.",
        "ts_sum(where(greater_than(close, lag(close, 1)), volume, "
        "where(less_than(close, lag(close, 1)), 0 - volume, 0)), 6)",
        ["close", "volume"],
    ),
    _alpha(
        46, "gtja_alpha46", "reversal", "positive", 24,
        "GTJA #46: (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24)) / "
        "(4*CLOSE) — a multi-horizon mean-to-price ratio.",
        "(sma(close, 3) + sma(close, 6) + sma(close, 12) + sma(close, 24)) / "
        "(4 * close)",
        ["close"],
    ),
    _alpha(
        48, "gtja_alpha48", "volume", "negative", 20,
        "GTJA #48: -1 * RANK(sign-chain of the last three closes) * "
        "SUM(VOLUME,5)/SUM(VOLUME,20).",
        "0 - rank(sign(close - lag(close, 1)) + "
        "sign(lag(close, 1) - lag(close, 2)) + "
        "sign(lag(close, 2) - lag(close, 3))) * "
        "ts_sum(volume, 5) / ts_sum(volume, 20)",
        ["close", "volume"], requires_panel=True,
    ),
    # -- tranche 3: the formulas that needed two operators this DSL did not have.
    # `wilder(x, n, m)` is GTJA's `SMA(X,N,M)` — the Wilder recursion
    # `Y = (m*X + (n-m)*Y')/n`, NOT a rolling mean — and `maximum`/`minimum` are
    # GTJA's elementwise `MAX(x, y)`/`MIN(x, y)`. Both are now first-class in
    # `stats.formula` and the panel evaluator, so these are transcriptions rather
    # than approximations. Source: lrb777/gtja191, alpha_001_050.py.
    _alpha(
        3, "gtja_alpha3", "reversal", "positive", 7,
        "GTJA #3: SUM over 6 days of the distance the close travelled beyond the "
        "prior bar (0 on an unchanged close), using elementwise MIN(low, prev) / "
        "MAX(high, prev).",
        "ts_sum(where(1 - abs(sign(close - lag(close, 1))), 0, "
        "where(greater_than(close, lag(close, 1)), "
        "close - minimum(low, lag(close, 1)), "
        "close - maximum(high, lag(close, 1)))), 6)",
        ["open", "high", "low", "close"],
    ),
    _alpha(
        4, "gtja_alpha4", "reversal", "positive", 20,
        "GTJA #4: three-state regime — -1 when the 8-day band is below the 2-day "
        "mean, +1 when it is above, else a volume-versus-20-day-mean tiebreak.",
        "where(less_than(sma(close, 8) + rolling_std(close, 8), sma(close, 2)), "
        "0 - 1, where(less_than(sma(close, 2), sma(close, 8) - "
        "rolling_std(close, 8)), 1, where(less_than(volume / sma(volume, 20), 1), "
        "0 - 1, 1)))",
        ["close", "volume"],
    ),
    _alpha(
        9, "gtja_alpha9", "reversal", "positive", 7,
        "GTJA #9: Wilder-SMA(7,2) of the mid-price change times the bar range per "
        "unit volume — a smoothed pressure term.",
        "wilder(((high + low) / 2 - (lag(high, 1) + lag(low, 1)) / 2) * "
        "(high - low) / volume, 7, 2)",
        ["high", "low", "volume"],
    ),
    _alpha(
        10, "gtja_alpha10", "reversal", "positive", 20,
        "GTJA #10: RANK(TSMAX((RET<0 ? STD(RET,20) : CLOSE)^2, 5)) — where the "
        "extreme squared conviction bar sits over the last five sessions.",
        "rank(rolling_max((where(less_than(pct_change(close, 1), 0), "
        "rolling_std(pct_change(close, 1), 20), close)) ^ 2, 5))",
        ["close"], requires_panel=True,
    ),
    _alpha(
        19, "gtja_alpha19", "reversal", "positive", 6,
        "GTJA #19: the five-day change, expressed against the earlier price when "
        "falling and against today's when rising, 0 on an unchanged close.",
        "where(less_than(close, lag(close, 5)), "
        "(close - lag(close, 5)) / lag(close, 5), "
        "where(less_than(abs(sign(close - lag(close, 5))), 0.5), 0, "
        "(close - lag(close, 5)) / close))",
        ["close"],
    ),
    _alpha(
        22, "gtja_alpha22", "reversal", "positive", 12,
        "GTJA #22: Wilder-SMA(12,1) of the three-day change in price deviation from "
        "its six-day mean.",
        "wilder(((close - sma(close, 6)) / sma(close, 6)) - "
        "lag(((close - sma(close, 6)) / sma(close, 6)), 3), 12, 1)",
        ["close"],
    ),
    _alpha(
        23, "gtja_alpha23", "reversal", "positive", 20,
        "GTJA #23: the share of 20-day close volatility that occurred on up days, "
        "as a percentage (Wilder-SMA of each side).",
        "wilder(where(greater_than(close, lag(close, 1)), rolling_std(close, 20), 0), "
        "20, 1) / (wilder(where(greater_than(close, lag(close, 1)), "
        "rolling_std(close, 20), 0), 20, 1) + wilder(where(greater_than(close, "
        "lag(close, 1)), 0, rolling_std(close, 20)), 20, 1)) * 100",
        ["close"],
    ),
    _alpha(
        24, "gtja_alpha24", "momentum", "positive", 6,
        "GTJA #24: Wilder-SMA(5,1) of the five-day close change.",
        "wilder(close - lag(close, 5), 5, 1)", ["close"],
    ),
    _alpha(
        26, "gtja_alpha26", "reversal", "positive", 230,
        "GTJA #26: (SUM(CLOSE,7)/7 - CLOSE) + CORR(VWAP, DELAY(CLOSE,5), 230).",
        "(sma(close, 7) - close) + correlation(vwap, lag(close, 5), 230)",
        ["close", "vwap"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        40, "gtja_alpha40", "volume", "positive", 26,
        "GTJA #40: up-day volume over down-day volume on a 26-day window, in "
        "percent.",
        "ts_sum(where(greater_than(close, lag(close, 1)), volume, 0), 26) / "
        "ts_sum(where(greater_than(close, lag(close, 1)), 0, volume), 26) * 100",
        ["close", "volume"],
    ),
    _alpha(
        47, "gtja_alpha47", "reversal", "negative", 9,
        "GTJA #47: Wilder-SMA(9,1) of the RSV-style position of the close inside "
        "the six-day high-low range, in percent.",
        "wilder(where(greater_than(rolling_max(high, 6) - rolling_min(low, 6), 0), "
        "(rolling_max(high, 6) - close) / "
        "(rolling_max(high, 6) - rolling_min(low, 6)) * 100, 0), 9, 1)",
        ["high", "low", "close"],
    ),
    # -- tranche 4: unlocked by `wma` (oldest-heaviest weights) and by the
    # elementwise `maximum`/`minimum` pair added in tranche 3. `#21` needs no new
    # operator at all: GTJA's REGBETA(MEAN(CLOSE,6), SEQUENCE(6), 6) is exactly a
    # rolling OLS slope of the 6-day mean against time, which is `slope(x, 6)`.
    # Source: lrb777/gtja191, alpha_001_050.py.
    _alpha(
        21, "gtja_alpha21", "reversal", "negative", 6,
        "GTJA #21: REGBETA(MEAN(CLOSE,6), SEQUENCE(6), 6) — the OLS slope of the "
        "six-day mean against time, i.e. a smoothed trend gradient.",
        "slope(sma(close, 6), 6)", ["close"],
    ),
    _alpha(
        25, "gtja_alpha25", "reversal", "negative", 250,
        "GTJA #25: -RANK(DELTA(CLOSE,7)*(1-RANK(DECAYLINEAR(VOL/MEAN(VOL,20),9))))"
        " * (1+RANK(SUM(RET,250))) — a seven-day move weighted by how ordinary its "
        "volume was, scaled by the annual flow.",
        "(0 - rank(delta(close, 7) * (1 - rank(decay_linear("
        "volume / sma(volume, 20), 9))))) * "
        "(1 + rank(ts_sum(pct_change(close, 1), 250)))",
        ["close", "volume"], requires_panel=True,
    ),
    _alpha(
        27, "gtja_alpha27", "momentum", "positive", 12,
        "GTJA #27: WMA of the summed three-day and six-day percentage changes, "
        "with WMA's OLDEST-heaviest weights.",
        "wma((close - lag(close, 3)) / lag(close, 3) * 100 + "
        "(close - lag(close, 6)) / lag(close, 6) * 100, 12)",
        ["close"],
    ),
    _alpha(
        35, "gtja_alpha35", "reversal", "negative", 17,
        "GTJA #35: -1 * MIN(RANK(DECAYLINEAR(DELTA(OPEN,1),15)), "
        "RANK(DECAYLINEAR(CORR(VOLUME, OPEN, 17), 7))) — the weaker of two ranked "
        "volume/price signals, inverted.",
        "0 - minimum(rank(decay_linear(delta(open, 1), 15)), "
        "rank(decay_linear(correlation(volume, open, 17), 7)))",
        ["open", "volume"], requires_panel=True,
    ),
    _alpha(
        37, "gtja_alpha37", "reversal", "negative", 10,
        "GTJA #37: -RANK(SUM(OPEN,5)*SUM(RET,5) - DELAY(SUM(OPEN,5)*SUM(RET,5),10)).",
        "0 - rank(ts_sum(open, 5) * ts_sum(pct_change(close, 1), 5) - "
        "lag(ts_sum(open, 5) * ts_sum(pct_change(close, 1), 5), 10))",
        ["open", "close"], requires_panel=True,
    ),
    _alpha(
        39, "gtja_alpha39", "volume", "negative", 180,
        "GTJA #39: -1 * (RANK(DECAYLINEAR(DELTA(CLOSE,2),8)) - "
        "RANK(DECAYLINEAR(CORR(VWAP*0.3+OPEN*0.7, SUM(MEAN(VOL,180),37), 14), 12))).",
        "0 - (rank(decay_linear(delta(close, 2), 8)) - "
        "rank(decay_linear(correlation(vwap * 0.3 + open * 0.7, "
        "ts_sum(sma(volume, 180), 37), 14), 12)))",
        ["close", "open", "vwap", "volume"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        41, "gtja_alpha41", "volume", "negative", 5,
        "GTJA #41: -RANK(TSMAX(DELTA(VWAP,3),5)).",
        "0 - rank(rolling_max(delta(vwap, 3), 5))",
        ["vwap"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        44, "gtja_alpha44", "reversal", "positive", 15,
        "GTJA #44: TSRANK(DECAYLINEAR(CORR(LOW, MEAN(VOL,10), 7), 6), 4) + "
        "TSRANK(DECAYLINEAR(DELTA(VWAP,3), 10), 15).",
        "ts_rank(decay_linear(correlation(low, sma(volume, 10), 7), 6), 4) + "
        "ts_rank(decay_linear(delta(vwap, 3), 10), 15)",
        ["low", "volume", "vwap"], requires_inputs=("vwap",),
    ),
    _alpha(
        45, "gtja_alpha45", "volume", "positive", 150,
        "GTJA #45: RANK(DELTA(CLOSE*0.6+OPEN*0.4,1)) * "
        "RANK(CORR(VWAP, MEAN(VOL,150), 15)).",
        "rank(delta(close * 0.6 + open * 0.4, 1)) * "
        "rank(correlation(vwap, sma(volume, 150), 15))",
        ["open", "close", "vwap", "volume"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        49, "gtja_alpha49", "reversal", "positive", 12,
        "GTJA #49: the up-side share of 12-day range expansion, where each day "
        "contributes MAX(|high-prev_high|, |low-prev_low|) unless the day already "
        "closed beyond the prior range on that side.",
        "ts_sum(where(greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, "
        "maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) / "
        "(ts_sum(where(greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, "
        "maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) + "
        "ts_sum(where(less_than(high + low, lag(high, 1) + lag(low, 1)), 0, "
        "maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12))",
        ["high", "low"],
    ),
]


def _assemble() -> list[dict[str, Any]]:
    """Base tranches plus the later batches, ordered by alpha number."""
    from .gtja191_batches import extra_alphas  # noqa: PLC0415 - avoids a cycle

    factors = list(_BASE_FACTORS)
    factors.extend(extra_alphas())
    factors.sort(key=lambda factor: factor["alphaNumber"])
    return factors


GTJA191_FACTORS: list[dict[str, Any]] = _assemble()


#: Stated as data so a tool or doc can report coverage without trusting prose.
PORTED = len(GTJA191_FACTORS)


def gtja_positions_port() -> dict[str, Any]:
    return {"zoo": ZOO, "ported": PORTED, "total": TOTAL, "reference": REFERENCE}


__all__ = ["GTJA191_FACTORS", "PORTED", "TOTAL", "gtja_positions_port"]
