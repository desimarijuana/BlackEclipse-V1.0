"""GTJA191 batches 5-10: the later tranches, kept out of `gtja191.py`.

`gtja191.py` owns the helper, the base tranches and the assembled list; this module
owns the entries added from tranche 5 onwards. The split exists because the size
budget ceilings a HARNESS module at 1,200 lines, and the honest fix for that is a
second file — not a ratchet bump on a file that has doubled.

`extra_alphas()` imports `_alpha` lazily: `gtja191` imports this module while it is
still initialising, and `_alpha` is already defined by then.
"""

from __future__ import annotations

from typing import Any


def extra_alphas() -> list[dict[str, Any]]:
    """Tranches 5-10, in the same `_alpha(...)` form as the base list."""
    from .gtja191 import _alpha  # noqa: PLC0415 - lazy, avoids an import cycle

    return [
    # -- tranche 5: GTJA #51-#100, transcribed from the same published
    # implementation (`alpha_051_100.py`). Only formulas whose operator set is
    # already verified are taken; `COUNT(x, n)` is `rolling_mean(cond, n) * n`, and
    # GTJA's `MIN/MAX` here are the elementwise pair added in tranche 3.
    _alpha(
        52, "gtja_alpha52", "reversal", "positive", 26,
        "GTJA #52: up-thrust over down-thrust of the typical price, in percent — "
        "SUM(MAX(0, HIGH - prev_typical), 26) / SUM(MAX(0, prev_typical - LOW), 26).",
        "ts_sum(maximum(0, high - lag((high + low + close) / 3, 1)), 26) / "
        "ts_sum(maximum(0, lag((high + low + close) / 3, 1) - low), 26) * 100",
        ["high", "low", "close"],
    ),
    _alpha(
        53, "gtja_alpha53", "momentum", "positive", 12,
        "GTJA #53: COUNT(CLOSE>DELAY(CLOSE,1), 12)/12*100 — the percentage of up "
        "days over twelve sessions.",
        "rolling_mean(greater_than(close, lag(close, 1)), 12) * 100", ["close"],
    ),
    _alpha(
        54, "gtja_alpha54", "reversal", "negative", 20,
        "GTJA #54: -RANK(STD(|CLOSE-OPEN|,20) + (CLOSE-OPEN) + CORR(CLOSE,OPEN,10)).",
        "0 - rank(rolling_std(abs(close - open), 20) + (close - open) + "
        "correlation(close, open, 10))",
        ["open", "close"], requires_panel=True,
    ),
    _alpha(
        57, "gtja_alpha57", "reversal", "negative", 9,
        "GTJA #57: Wilder-SMA(3,1) of the close's position inside the nine-day "
        "high-low range, in percent.",
        "wilder(where(greater_than(rolling_max(high, 9) - rolling_min(low, 9), 0), (close - rolling_min(low, 9)) / (rolling_max(high, 9) - rolling_min(low, 9)) * 100, 0), 3, 1)",
        ["high", "low", "close"],
    ),
    _alpha(
        58, "gtja_alpha58", "momentum", "positive", 20,
        "GTJA #58: COUNT(CLOSE>DELAY(CLOSE,1), 20)/20*100.",
        "rolling_mean(greater_than(close, lag(close, 1)), 20) * 100", ["close"],
    ),
    _alpha(
        59, "gtja_alpha59", "reversal", "positive", 20,
        "GTJA #59: GTJA #3's beyond-the-prior-bar distance, summed over 20 days.",
        "ts_sum(where(1 - abs(sign(close - lag(close, 1))), 0, "
        "where(greater_than(close, lag(close, 1)), "
        "close - minimum(low, lag(close, 1)), "
        "close - maximum(high, lag(close, 1)))), 20)",
        ["high", "low", "close"],
    ),
    _alpha(
        60, "gtja_alpha60", "volume", "positive", 20,
        "GTJA #60: the volume-weighted close-location expression, summed over 20 "
        "days.",
        "ts_sum(((close - low) - (high - close)) / (high - low) * volume, 20)",
        ["high", "low", "close", "volume"],
    ),
    _alpha(
        63, "gtja_alpha63", "momentum", "positive", 6,
        "GTJA #63: Wilder-SMA(6,1) of up moves over the Wilder-SMA of absolute "
        "moves — a 6-day RSI, in percent.",
        "wilder(maximum(close - lag(close, 1), 0), 6, 1) / "
        "wilder(abs(close - lag(close, 1)), 6, 1) * 100",
        ["close"],
    ),
    _alpha(
        65, "gtja_alpha65", "reversal", "negative", 6,
        "GTJA #65: MEAN(CLOSE,6)/CLOSE.",
        "sma(close, 6) / close", ["close"],
    ),
    _alpha(
        66, "gtja_alpha66", "reversal", "positive", 6,
        "GTJA #66: (CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)*100.",
        "(close - sma(close, 6)) / sma(close, 6) * 100", ["close"],
    ),
    _alpha(
        67, "gtja_alpha67", "momentum", "positive", 24,
        "GTJA #67: the 24-day RSI (Wilder-SMA of up moves over absolute moves).",
        "wilder(maximum(close - lag(close, 1), 0), 24, 1) / "
        "wilder(abs(close - lag(close, 1)), 24, 1) * 100",
        ["close"],
    ),
    _alpha(
        68, "gtja_alpha68", "reversal", "positive", 15,
        "GTJA #68: Wilder-SMA(15,2) of the mid-price change times the bar range "
        "per unit volume.",
        "wilder(((high + low) / 2 - (lag(high, 1) + lag(low, 1)) / 2) * "
        "(high - low) / volume, 15, 2)",
        ["high", "low", "volume"],
    ),
    _alpha(
        70, "gtja_alpha70", "volatility", "negative", 6,
        "GTJA #70: STD(AMOUNT, 6) — turnover volatility. Declares the `amount` "
        "input: it is not derivable from OHLCV here.",
        "rolling_std(amount, 6)", ["amount"], requires_inputs=("amount",),
    ),
    _alpha(
        71, "gtja_alpha71", "reversal", "positive", 24,
        "GTJA #71: (CLOSE-MEAN(CLOSE,24))/MEAN(CLOSE,24)*100.",
        "(close - sma(close, 24)) / sma(close, 24) * 100", ["close"],
    ),
    _alpha(
        72, "gtja_alpha72", "reversal", "negative", 15,
        "GTJA #72: Wilder-SMA(15,1) of the close's distance below the six-day high, "
        "in percent.",
        "wilder(where(greater_than(rolling_max(high, 6) - rolling_min(low, 6), 0), "
        "(rolling_max(high, 6) - close) / "
        "(rolling_max(high, 6) - rolling_min(low, 6)) * 100, 0), 15, 1)",
        ["high", "low", "close"],
    ),
    _alpha(
        79, "gtja_alpha79", "momentum", "positive", 12,
        "GTJA #79: the 12-day RSI (Wilder-SMA of up moves over absolute moves).",
        "wilder(maximum(close - lag(close, 1), 0), 12, 1) / "
        "wilder(abs(close - lag(close, 1)), 12, 1) * 100",
        ["close"],
    ),
    _alpha(
        80, "gtja_alpha80", "volume", "positive", 6,
        "GTJA #80: (VOLUME-DELAY(VOLUME,5))/DELAY(VOLUME,5)*100.",
        "(volume - lag(volume, 5)) / lag(volume, 5) * 100", ["volume"],
    ),
    _alpha(
        84, "gtja_alpha84", "volume", "positive", 20,
        "GTJA #84: signed volume (up days positive, down days negative) summed "
        "over 20 days.",
        "ts_sum(where(greater_than(close, lag(close, 1)), volume, "
        "where(less_than(close, lag(close, 1)), 0 - volume, 0)), 20)",
        ["close", "volume"],
    ),
    _alpha(
        85, "gtja_alpha85", "volume", "positive", 20,
        "GTJA #85: TSRANK(VOL/MEAN(VOL,20),20) * TSRANK(-DELTA(CLOSE,7),8).",
        "ts_rank(volume / sma(volume, 20), 20) * ts_rank(0 - delta(close, 7), 8)",
        ["close", "volume"],
    ),
    _alpha(
        88, "gtja_alpha88", "momentum", "positive", 21,
        "GTJA #88: (CLOSE-DELAY(CLOSE,20))/DELAY(CLOSE,20)*100.",
        "(close - lag(close, 20)) / lag(close, 20) * 100", ["close"],
    ),
    _alpha(
        95, "gtja_alpha95", "volatility", "negative", 20,
        "GTJA #95: STD(AMOUNT, 20) — declares the `amount` input.",
        "rolling_std(amount, 20)", ["amount"], requires_inputs=("amount",),
    ),
    # -- tranche 6: GTJA #101-#150. `HIGHDAY`/`LOWDAY` in the published operator
    # library are `n-1-argmax` / `n-1-argmin` (0 = today), which is why the
    # position terms are written as `n - (n-1 - ts_argmax(...))`.
    _alpha(
        102, "gtja_alpha102", "volume", "positive", 6,
        "GTJA #102: the 6-day RSI of VOLUME — Wilder-SMA of volume up moves over "
        "absolute volume moves.",
        "wilder(maximum(volume - lag(volume, 1), 0), 6, 1) / "
        "wilder(abs(volume - lag(volume, 1)), 6, 1) * 100",
        ["volume"],
    ),
    _alpha(
        103, "gtja_alpha103", "reversal", "negative", 20,
        "GTJA #103: (20 - LOWDAY(LOW,20))/20*100 — how recently the 20-day low "
        "occurred, as a percentage.",
        "((20 - (19 - ts_argmin(low, 20))) / 20) * 100",
        ["low"],
    ),
    _alpha(
        106, "gtja_alpha106", "momentum", "positive", 21,
        "GTJA #106: CLOSE - DELAY(CLOSE,20).",
        "close - lag(close, 20)", ["close"],
    ),
    _alpha(
        109, "gtja_alpha109", "reversal", "negative", 10,
        "GTJA #109: SMA(HIGH-LOW,10,2) / SMA(SMA(HIGH-LOW,10,2),10,2) — a smoothed "
        "range ratio.",
        "wilder(high - low, 10, 2) / wilder(wilder(high - low, 10, 2), 10, 2)",
        ["high", "low"],
    ),
    _alpha(
        110, "gtja_alpha110", "reversal", "positive", 20,
        "GTJA #110: up-thrust over down-thrust from the previous close, 20 days, in "
        "percent.",
        "ts_sum(maximum(0, high - lag(close, 1)), 20) / "
        "ts_sum(maximum(0, lag(close, 1) - low), 20) * 100",
        ["high", "low", "close"],
    ),
    _alpha(
        111, "gtja_alpha111", "volume", "positive", 11,
        "GTJA #111: the 11-day minus the 4-day Wilder-SMA(2) of volume-weighted "
        "close location.",
        "wilder(volume * ((close - low) - (high - close)) / (high - low), 11, 2) - "
        "wilder(volume * ((close - low) - (high - close)) / (high - low), 4, 2)",
        ["high", "low", "close", "volume"],
    ),
    _alpha(
        116, "gtja_alpha116", "trend", "positive", 20,
        "GTJA #116: REGBETA(CLOSE, SEQUENCE(20), 20) — the OLS slope of close "
        "against time.",
        "slope(close, 20)", ["close"],
    ),
    _alpha(
        117, "gtja_alpha117", "volume", "positive", 32,
        "GTJA #117: TSRANK(VOL,32) * (1-TSRANK(CLOSE+HIGH-LOW,16)) * "
        "(1-TSRANK(RET,32)).",
        "ts_rank(volume, 32) * (1 - ts_rank(close + high - low, 16)) * "
        "(1 - ts_rank(pct_change(close, 1), 32))",
        ["high", "low", "close", "volume"],
    ),
    _alpha(
        118, "gtja_alpha118", "volume", "positive", 20,
        "GTJA #118: SUM(HIGH-OPEN,20)/SUM(OPEN-LOW,20)*100 — where the bar bodies "
        "sit, summed.",
        "ts_sum(high - open, 20) / ts_sum(open - low, 20) * 100",
        ["open", "high", "low"],
    ),
    _alpha(
        120, "gtja_alpha120", "reversal", "positive", 1,
        "GTJA #120: RANK(VWAP-CLOSE)/RANK(VWAP+CLOSE).",
        "rank(vwap - close) / rank(vwap + close)",
        ["vwap", "close"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        122, "gtja_alpha122", "trend", "positive", 13,
        "GTJA #122: the one-day change in the thrice-Wilder-smoothed log close, "
        "relative to yesterday.",
        "((wilder(wilder(wilder(log(close), 13, 2), 13, 2), 13, 2)) - "
        "lag(wilder(wilder(wilder(log(close), 13, 2), 13, 2), 13, 2), 1)) / "
        "lag(wilder(wilder(wilder(log(close), 13, 2), 13, 2), 13, 2), 1)",
        ["close"],
    ),
    _alpha(
        124, "gtja_alpha124", "reversal", "positive", 30,
        "GTJA #124: (CLOSE-VWAP) / DECAYLINEAR(RANK(TSMAX(CLOSE,30)),2).",
        "(close - vwap) / decay_linear(rank(rolling_max(close, 30)), 2)",
        ["close", "vwap"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        126, "gtja_alpha126", "reversal", "positive", 1,
        "GTJA #126: (CLOSE+HIGH+LOW)/3 — the typical price.",
        "(close + high + low) / 3", ["high", "low", "close"],
    ),
    _alpha(
        127, "gtja_alpha127", "reversal", "negative", 12,
        "GTJA #127: sqrt(MEAN((100*(CLOSE-TSMAX(CLOSE,12))/TSMAX(CLOSE,12))^2, 12)) "
        "— the RMS distance below the twelve-day high.",
        "sqrt(sma((100 * (close - rolling_max(close, 12)) / "
        "rolling_max(close, 12)) ^ 2, 12))",
        ["close"],
    ),
    _alpha(
        128, "gtja_alpha128", "volume", "positive", 14,
        "GTJA #128: 100 - 100/(1 + SUM(up volume,14)/SUM(down volume,14)) on the "
        "typical price — a money-flow style index.",
        "100 - 100 / (1 + ts_sum(where(greater_than((high + low + close) / 3, "
        "lag((high + low + close) / 3, 1)), (high + low + close) / 3 * volume, 0), "
        "14) / ts_sum(where(less_than((high + low + close) / 3, "
        "lag((high + low + close) / 3, 1)), (high + low + close) / 3 * volume, 0), "
        "14))",
        ["high", "low", "close", "volume"],
    ),
    _alpha(
        129, "gtja_alpha129", "reversal", "positive", 12,
        "GTJA #129: SUM(|CLOSE-DELAY(CLOSE,1)| on down days, 12).",
        "ts_sum(where(less_than(close - lag(close, 1), 0), "
        "abs(close - lag(close, 1)), 0), 12)",
        ["close"],
    ),
    _alpha(
        131, "gtja_alpha131", "volume", "positive", 50,
        "GTJA #131: RANK(DELTA(VWAP,1)) ^ TSRANK(CORR(CLOSE,MEAN(VOL,50),18),18).",
        "rank(delta(vwap, 1)) ^ ts_rank(correlation(close, sma(volume, 50), 18), 18)",
        ["vwap", "close", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        132, "gtja_alpha132", "volume", "positive", 20,
        "GTJA #132: MEAN(AMOUNT, 20) — average turnover. Declares the `amount` "
        "input.",
        "sma(amount, 20)", ["amount"], requires_inputs=("amount",),
    ),
    _alpha(
        133, "gtja_alpha133", "reversal", "negative", 20,
        "GTJA #133: the high-day percentage minus the low-day percentage over 20 "
        "sessions.",
        "((20 - (19 - ts_argmax(high, 20))) / 20) * 100 - "
        "((20 - (19 - ts_argmin(low, 20))) / 20) * 100",
        ["high", "low"],
    ),
    _alpha(
        134, "gtja_alpha134", "volume", "positive", 13,
        "GTJA #134: (CLOSE-DELAY(CLOSE,12))/DELAY(CLOSE,12)*VOLUME.",
        "(close - lag(close, 12)) / lag(close, 12) * volume", ["close", "volume"],
    ),
    _alpha(
        135, "gtja_alpha135", "reversal", "positive", 20,
        "GTJA #135: Wilder-SMA(20,1) of yesterday's CLOSE/DELAY(CLOSE,20) ratio.",
        "wilder(lag(close / lag(close, 20), 1), 20, 1)", ["close"],
    ),
    _alpha(
        139, "gtja_alpha139", "volume", "negative", 10,
        "GTJA #139: -CORR(OPEN, VOLUME, 10).",
        "0 - correlation(open, volume, 10)", ["open", "volume"],
    ),
    _alpha(
        145, "gtja_alpha145", "volume", "positive", 26,
        "GTJA #145: (MEAN(VOL,9)-MEAN(VOL,26))/MEAN(VOL,12)*100.",
        "(sma(volume, 9) - sma(volume, 26)) / sma(volume, 12) * 100", ["volume"],
    ),
    _alpha(
        147, "gtja_alpha147", "trend", "positive", 12,
        "GTJA #147: REGBETA(MEAN(CLOSE,12), SEQUENCE(12), 12) — the OLS slope of the "
        "twelve-day mean against time.",
        "slope(sma(close, 12), 12)", ["close"],
    ),
    _alpha(
        150, "gtja_alpha150", "volume", "positive", 1,
        "GTJA #150: (CLOSE+HIGH+LOW)/3 * VOLUME.",
        "(close + high + low) / 3 * volume", ["high", "low", "close", "volume"],
    ),
    # -- tranche 7: GTJA #151-#191. #157 needs a rolling PRODUCT (window 1 here,
    # which is the identity), and #182 is the first alpha to declare BENCHMARK
    # inputs — both are contract-level, so they get their own tests.
    _alpha(
        151, "gtja_alpha151", "reversal", "positive", 20,
        "GTJA #151: Wilder-SMA(20,1) of the twenty-day close change.",
        "wilder(close - lag(close, 20), 20, 1)", ["close"],
    ),
    _alpha(
        153, "gtja_alpha153", "reversal", "negative", 24,
        "GTJA #153: (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/4 — "
        "the four-horizon mean price.",
        "(sma(close, 3) + sma(close, 6) + sma(close, 12) + sma(close, 24)) / 4",
        ["close"],
    ),
    _alpha(
        154, "gtja_alpha154", "volume", "positive", 180,
        "GTJA #154: (VWAP - TSMIN(VWAP,16)) < CORR(VWAP,MEAN(VOL,180),18) — a boolean "
        "factor by construction.",
        "less_than(vwap - rolling_min(vwap, 16), "
        "correlation(vwap, sma(volume, 180), 18))",
        ["vwap", "volume"], requires_inputs=("vwap",),
    ),
    _alpha(
        155, "gtja_alpha155", "volume", "positive", 27,
        "GTJA #155: the 13-vs-27 Wilder-SMA(2) volume spread, smoothed again at "
        "10 days.",
        "(wilder(volume, 13, 2) - wilder(volume, 27, 2)) - "
        "wilder(wilder(volume, 13, 2) - wilder(volume, 27, 2), 10, 2)",
        ["volume"],
    ),
    _alpha(
        156, "gtja_alpha156", "volume", "negative", 5,
        "GTJA #156: -1 * MAX(RANK(DECAYLINEAR(DELTA(VWAP,5),3)), "
        "RANK(DECAYLINEAR(-DELTA(OPEN*0.15+LOW*0.85,2)/(OPEN*0.15+LOW*0.85),3))).",
        "0 - maximum(rank(decay_linear(delta(vwap, 5), 3)), "
        "rank(decay_linear(0 - delta(open * 0.15 + low * 0.85, 2) / "
        "(open * 0.15 + low * 0.85), 3)))",
        ["vwap", "open", "low"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        157, "gtja_alpha157", "reversal", "positive", 5,
        "GTJA #157: the paper's nested RANK chain — -1*RANK(DELTA(CLOSE-1,5)), "
        "double-ranked, ts_min(2), summed(1), logged, double-ranked, product(1), "
        "ts_min(5) — plus TSRANK(DELAY(-RET,6),5).",
        "rolling_min(prod(rank(rank(log(ts_sum(rolling_min(rank(rank("
        "0 - rank(delta(close - 1, 5)))), 2), 1)))), 1), 5) + "
        "ts_rank(lag(0 - pct_change(close, 1), 6), 5)",
        ["close"], requires_panel=True,
    ),
    _alpha(
        158, "gtja_alpha158", "reversal", "positive", 15,
        "GTJA #158: ((HIGH - SMA(CLOSE,15,2)) - (LOW - SMA(CLOSE,15,2))) / CLOSE — "
        "the published form in which the two Wilder terms cancel.",
        "((high - wilder(close, 15, 2)) - (low - wilder(close, 15, 2))) / close",
        ["high", "low", "close"],
    ),
    _alpha(
        160, "gtja_alpha160", "volatility", "negative", 20,
        "GTJA #160: Wilder-SMA(20,1) of the 20-day close volatility on down days "
        "only.",
        "wilder(where(1 - greater_than(close, lag(close, 1)), "
        "rolling_std(close, 20), 0), 20, 1)",
        ["close"],
    ),
    _alpha(
        161, "gtja_alpha161", "volatility", "negative", 12,
        "GTJA #161: MEAN of the true range (max of high-low and the two gaps to the "
        "prior close), 12 days.",
        "sma(maximum(maximum(high - low, abs(lag(close, 1) - high)), "
        "abs(lag(close, 1) - low)), 12)",
        ["high", "low", "close"],
    ),
    _alpha(
        162, "gtja_alpha162", "reversal", "positive", 12,
        "GTJA #162: the 12-day RSI rescaled into its own 12-day min-max range.",
        "("
        "wilder(maximum(close - lag(close, 1), 0), 12, 1) / "
        "wilder(abs(close - lag(close, 1)), 12, 1) * 100 - "
        "rolling_min(wilder(maximum(close - lag(close, 1), 0), 12, 1) / "
        "wilder(abs(close - lag(close, 1)), 12, 1) * 100, 12)"
        ") / ("
        "rolling_max(wilder(maximum(close - lag(close, 1), 0), 12, 1) / "
        "wilder(abs(close - lag(close, 1)), 12, 1) * 100, 12) - "
        "rolling_min(wilder(maximum(close - lag(close, 1), 0), 12, 1) / "
        "wilder(abs(close - lag(close, 1)), 12, 1) * 100, 12)"
        ")",
        ["close"],
    ),
    _alpha(
        163, "gtja_alpha163", "reversal", "positive", 20,
        "GTJA #163: RANK(-RET * MEAN(VOL,20) * VWAP * (HIGH-CLOSE)).",
        "rank((0 - pct_change(close, 1)) * sma(volume, 20) * vwap * (high - close))",
        ["high", "close", "volume", "vwap"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        164, "gtja_alpha164", "reversal", "negative", 13,
        "GTJA #164: Wilder-SMA(13,2) of the up-day inverse-move less its 12-day "
        "minimum, per unit range.",
        "wilder((where(greater_than(close, lag(close, 1)), "
        "1 / (close - lag(close, 1)), 1) - "
        "rolling_min(where(greater_than(close, lag(close, 1)), "
        "1 / (close - lag(close, 1)), 1), 12)) / (high - low) * 100, 13, 2)",
        ["high", "low", "close"],
    ),
    _alpha(
        167, "gtja_alpha167", "reversal", "positive", 12,
        "GTJA #167: SUM of up moves over 12 days.",
        "ts_sum(where(greater_than(close - lag(close, 1), 0), "
        "close - lag(close, 1), 0), 12)",
        ["close"],
    ),
    _alpha(
        168, "gtja_alpha168", "volume", "negative", 20,
        "GTJA #168: -VOLUME/MEAN(VOLUME,20).",
        "0 - volume / sma(volume, 20)", ["volume"],
    ),
    _alpha(
        170, "gtja_alpha170", "volume", "positive", 20,
        "GTJA #170: (RANK(1/CLOSE)*VOL/MEAN(VOL,20)) * "
        "(HIGH*RANK(HIGH-CLOSE)/(SUM(HIGH,5)/5)) - RANK(VWAP-DELAY(VWAP,5)).",
        "((rank(1 / close) * volume) / sma(volume, 20)) * "
        "((high * rank(high - close)) / sma(high, 5)) - "
        "rank(vwap - lag(vwap, 5))",
        ["high", "close", "volume", "vwap"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        171, "gtja_alpha171", "reversal", "negative", 1,
        "GTJA #171: -1 * (LOW-CLOSE)*OPEN^5 / ((CLOSE-HIGH)*CLOSE^5).",
        "0 - (low - close) * (open ^ 5) / ((close - high) * (close ^ 5))",
        ["open", "high", "low", "close"],
    ),
    _alpha(
        173, "gtja_alpha173", "trend", "positive", 13,
        "GTJA #173: 3*SMA(CLOSE,13,2) - 2*SMA(SMA(CLOSE,13,2),13,2) + "
        "SMA^3(LOG(CLOSE),13,2) — a trend-plus-log baseline.",
        "3 * wilder(close, 13, 2) - 2 * wilder(wilder(close, 13, 2), 13, 2) + "
        "wilder(wilder(wilder(log(close), 13, 2), 13, 2), 13, 2)",
        ["close"],
    ),
    _alpha(
        174, "gtja_alpha174", "volatility", "negative", 20,
        "GTJA #174: Wilder-SMA(20,1) of the 20-day close volatility on UP days only.",
        "wilder(where(greater_than(close, lag(close, 1)), rolling_std(close, 20), 0), "
        "20, 1)",
        ["close"],
    ),
    _alpha(
        175, "gtja_alpha175", "volatility", "negative", 6,
        "GTJA #175: MEAN of the true range over six days.",
        "sma(maximum(maximum(high - low, abs(lag(close, 1) - high)), "
        "abs(lag(close, 1) - low)), 6)",
        ["high", "low", "close"],
    ),
    _alpha(
        177, "gtja_alpha177", "reversal", "negative", 20,
        "GTJA #177: ((20-HIGHDAY(HIGH,20))/20)*100 — how recently the 20-day high "
        "occurred.",
        "((20 - (19 - ts_argmax(high, 20))) / 20) * 100", ["high"],
    ),
    _alpha(
        178, "gtja_alpha178", "volume", "positive", 2,
        "GTJA #178: (CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)*VOLUME.",
        "(close - lag(close, 1)) / lag(close, 1) * volume", ["close", "volume"],
    ),
    _alpha(
        180, "gtja_alpha180", "volume", "negative", 60,
        "GTJA #180: if MEAN(VOL,20) < VOL then -TSRANK(|DELTA(CLOSE,7)|,60)*"
        "SIGN(DELTA(CLOSE,7)) else -VOL.",
        "where(less_than(sma(volume, 20), volume), "
        "0 - ts_rank(abs(delta(close, 7)), 60) * sign(delta(close, 7)), "
        "0 - volume)",
        ["close", "volume"],
    ),
    _alpha(
        182, "gtja_alpha182", "reversal", "positive", 20,
        "GTJA #182: COUNT of days where the stock and the benchmark moved the same "
        "way, over 20. The first alpha to declare BENCHMARK inputs.",
        "rolling_mean(greater_than("
        "greater_than(close, open) * greater_than(benchmark_close, benchmark_open) + "
        "greater_than(open, close) * greater_than(benchmark_open, benchmark_close), "
        "0), 20)",
        ["open", "close", "benchmark_open", "benchmark_close"],
        requires_inputs=("benchmark_open", "benchmark_close"),
    ),
    _alpha(
        184, "gtja_alpha184", "reversal", "positive", 200,
        "GTJA #184: RANK(CORR(DELAY(OPEN-CLOSE,1), CLOSE, 200)) + RANK(OPEN-CLOSE).",
        "rank(correlation(lag(open - close, 1), close, 200)) + rank(open - close)",
        ["open", "close"], requires_panel=True,
    ),
    _alpha(
        185, "gtja_alpha185", "reversal", "positive", 1,
        "GTJA #185: RANK(-(1 - OPEN/CLOSE)^2).",
        "rank(0 - (1 - open / close) ^ 2)", ["open", "close"],
        requires_panel=True,
    ),
    _alpha(
        188, "gtja_alpha188", "volatility", "negative", 11,
        "GTJA #188: (HIGH-LOW - SMA(HIGH-LOW,11,2)) / SMA(HIGH-LOW,11,2) * 100.",
        "((high - low) - wilder(high - low, 11, 2)) / "
        "wilder(high - low, 11, 2) * 100",
        ["high", "low"],
    ),
    _alpha(
        189, "gtja_alpha189", "reversal", "negative", 6,
        "GTJA #189: MEAN(|CLOSE - MEAN(CLOSE,6)|, 6).",
        "sma(abs(close - sma(close, 6)), 6)", ["close"],
    ),
    _alpha(
        191, "gtja_alpha191", "volume", "positive", 20,
        "GTJA #191: CORR(MEAN(VOL,20), LOW, 5) + (HIGH+LOW)/2 - CLOSE.",
        "correlation(sma(volume, 20), low, 5) + (high + low) / 2 - close",
        ["high", "low", "volume", "close"],
    ),
    # -- tranche 8: the three remaining formulas that needed only a name or an
    # input contract. GTJA's `SUMAC(x, n)` is a plain rolling SUM (not a running
    # total), so it is an alias here rather than a second implementation; #181 is
    # the benchmark-deviation ratio and uses the declared benchmark input.
    _alpha(
        165, "gtja_alpha165", "trend", "positive", 48,
        "GTJA #165: the 48-day range of the cumulative deviation from the 48-day "
        "mean, over close volatility.",
        "(rolling_max(ts_sum(close - sma(close, 48), 48), 48) - "
        "rolling_min(ts_sum(close - sma(close, 48), 48), 48)) / "
        "rolling_std(close, 48)",
        ["close"],
    ),
    _alpha(
        181, "gtja_alpha181", "trend", "positive", 20,
        "GTJA #181: the squared deviation of the stock's return from the benchmark's, "
        "over the benchmark's cubed deviation — a co-movement ratio. Declares the "
        "benchmark input.",
        "ts_sum(((pct_change(close, 1) - sma(pct_change(close, 1), 20)) - "
        "(benchmark_close - sma(benchmark_close, 20))) ^ 2, 20) / "
        "ts_sum((benchmark_close - sma(benchmark_close, 20)) ^ 3, 20)",
        ["close", "benchmark_close"], requires_inputs=("benchmark_close",),
    ),
    _alpha(
        183, "gtja_alpha183", "trend", "positive", 24,
        "GTJA #183: the 24-day version of #165 — range of the cumulative deviation "
        "over close volatility.",
        "(rolling_max(ts_sum(close - sma(close, 24), 24), 24) - "
        "rolling_min(ts_sum(close - sma(close, 24), 24), 24)) / "
        "rolling_std(close, 24)",
        ["close"],
    ),
    # -- tranche 9: the regression and stateful block. `regbeta`/`regresi` regress
    # ONE SERIES ON ANOTHER (unlike `slope`, which regresses on time), and
    # `regbeta_where` carries a selection mask into the regression so a
    # down-market beta is computed from the selected days rather than by silently
    # dropping rows. `cumprod` supplies GTJA #143's `SELF` state.
    _alpha(
        51, "gtja_alpha51", "reversal", "negative", 12,
        "GTJA #51: the down-side share of 12-day range expansion "
        "(dn/(dn+up), the complement of #49).",
        "ts_sum(where(1 - greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) / (ts_sum(where(1 - greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) + ts_sum(where(greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12))",
        ["high", "low"],
    ),
    _alpha(
        56, "gtja_alpha56", "volume", "negative", 19,
        "GTJA #56: RANK(OPEN-TSMIN(OPEN,12)) < RANK(RANK(CORR(SUM(mid,19), "
        "SUM(MEAN(VOL,40),19), 13))^5) — a boolean factor.",
        "less_than(rank(open - rolling_min(open, 12)), "
        "rank(rank(correlation(ts_sum((high + low) / 2, 19), "
        "ts_sum(sma(volume, 40), 19), 13)) ^ 5))",
        ["open", "high", "low", "volume"], requires_panel=True,
    ),
    _alpha(
        108, "gtja_alpha108", "volume", "negative", 120,
        "GTJA #108: -RANK(HIGH-TSMIN(HIGH,2)) ^ RANK(CORR(VWAP,MEAN(VOL,120),6)).",
        "0 - rank(high - rolling_min(high, 2)) ^ "
        "rank(correlation(vwap, sma(volume, 120), 6))",
        ["high", "vwap", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        115, "gtja_alpha115", "volume", "positive", 30,
        "GTJA #115: RANK(CORR(HIGH*0.9+CLOSE*0.1, MEAN(VOL,30),10)) ^ "
        "RANK(CORR(TSRANK(mid,4), TSRANK(VOL,10),7)).",
        "rank(correlation(high * 0.9 + close * 0.1, sma(volume, 30), 10)) ^ "
        "rank(correlation(ts_rank((high + low) / 2, 4), ts_rank(volume, 10), 7))",
        ["high", "low", "close", "volume"], requires_panel=True,
    ),
    _alpha(
        121, "gtja_alpha121", "volume", "negative", 60,
        "GTJA #121: -RANK(VWAP-TSMIN(VWAP,12)) ^ "
        "TSRANK(CORR(TSRANK(VWAP,20), TSRANK(MEAN(VOL,60),2),18), 3).",
        "0 - rank(vwap - rolling_min(vwap, 12)) ^ "
        "ts_rank(correlation(ts_rank(vwap, 20), ts_rank(sma(volume, 60), 2), 18), 3)",
        ["vwap", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        123, "gtja_alpha123", "volume", "negative", 60,
        "GTJA #123: RANK(CORR(SUM(mid,20), SUM(MEAN(VOL,60),20), 9)) < "
        "RANK(CORR(LOW, VOL, 6)) — a boolean factor.",
        "less_than(rank(correlation(ts_sum((high + low) / 2, 20), "
        "ts_sum(sma(volume, 60), 20), 9)), "
        "rank(correlation(low, volume, 6)))",
        ["high", "low", "volume"], requires_panel=True,
    ),
    _alpha(
        138, "gtja_alpha138", "volume", "negative", 60,
        "GTJA #138: -(RANK(DECAYLINEAR(DELTA(LOW*0.7+VWAP*0.3,3),20)) - "
        "TSRANK(DECAYLINEAR(TSRANK(CORR(TSRANK(LOW,8), TSRANK(MEAN(VOL,60),17),5),19),"
        "16),7)).",
        "0 - (rank(decay_linear(delta(low * 0.7 + vwap * 0.3, 3), 20)) - "
        "ts_rank(decay_linear(ts_rank(correlation(ts_rank(low, 8), "
        "ts_rank(sma(volume, 60), 17), 5), 19), 16), 7))",
        ["low", "vwap", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        143, "gtja_alpha143", "momentum", "positive", 1,
        "GTJA #143: the cumulative product of up-day gross returns — the paper's "
        "`SELF` state, seeded at 1.0 and carried forward on flat or down days.",
        "cumprod(where(greater_than(close, lag(close, 1)), "
        "1 + pct_change(close, 1), 1))",
        ["close"],
    ),
    _alpha(
        146, "gtja_alpha146", "trend", "negative", 61,
        "GTJA #146: the deviation of returns from their 61-day Wilder mean, "
        "weighted by its own 20-day mean, over the 60-day Wilder variance.",
        "((pct_change(close, 1) - wilder(pct_change(close, 1), 61, 2)) * "
        "sma(pct_change(close, 1) - wilder(pct_change(close, 1), 61, 2), 20)) / "
        "wilder((pct_change(close, 1) - wilder(pct_change(close, 1), 61, 2)) ^ 2, "
        "60, 2)",
        ["close"],
    ),
    _alpha(
        148, "gtja_alpha148", "volume", "negative", 60,
        "GTJA #148: RANK(CORR(OPEN, SUM(MEAN(VOL,60),9), 6)) < "
        "RANK(OPEN-TSMIN(OPEN,14)) — a boolean factor.",
        "less_than(rank(correlation(open, ts_sum(sma(volume, 60), 9), 6)), "
        "rank(open - rolling_min(open, 14)))",
        ["open", "volume"], requires_panel=True,
    ),
    _alpha(
        149, "gtja_alpha149", "reversal", "positive", 252,
        "GTJA #149: the DOWNSIDE beta of the stock on the benchmark — REGBETA over "
        "252 days restricted to the days the benchmark fell. Declares the benchmark "
        "input; the selection mask is carried into the regression.",
        "regbeta_where(pct_change(close, 1), pct_change(benchmark_close, 1), "
        "less_than(benchmark_close, lag(benchmark_close, 1)), 252)",
        ["close", "benchmark_close"], requires_inputs=("benchmark_close",),
    ),
    # -- tranche 10: the multivariate-regression alpha, the formulas that were
    # dropped from tranche 9 for transcription reasons, and the remaining alphas
    # whose operators all exist. `regresi_multi` takes declared factor inputs: GTJA
    # #30 needs MKT/SMB/HML, which the harness does not invent.
    _alpha(
        7, "gtja_alpha7", "volume", "positive", 3,
        "GTJA #7: (RANK(MAX(VWAP-CLOSE,3)) + RANK(MIN(VWAP-CLOSE,3))) * "
        "RANK(DELTA(VOLUME,3)).",
        "(rank(rolling_max(vwap - close, 3)) + rank(rolling_min(vwap - close, 3))) * "
        "rank(delta(volume, 3))",
        ["vwap", "close", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        30, "gtja_alpha30", "reversal", "positive", 60,
        "GTJA #30: WMA((REGRESI(RET, MKT, SMB, HML, 60))^2, 20) — the squared "
        "three-factor residual, smoothed with WMA's oldest-heaviest weights. "
        "Declares the three factor inputs.",
        "wma(regresi_multi(pct_change(close, 1), mkt, smb, hml, 60) ^ 2, 20)",
        ["close", "mkt", "smb", "hml"],
        requires_inputs=("mkt", "smb", "hml"),
    ),
    _alpha(
        50, "gtja_alpha50", "reversal", "negative", 12,
        "GTJA #50: the down-side share minus the up-side share of 12-day range "
        "expansion (dn/total - up/total).",
        "(ts_sum(where(1 - greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) / (ts_sum(where(1 - greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) + ts_sum(where(greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12))) - (ts_sum(where(greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) / (ts_sum(where(1 - greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12) + ts_sum(where(greater_than(high + low, lag(high, 1) + lag(low, 1)), 0, maximum(abs(high - lag(high, 1)), abs(low - lag(low, 1)))), 12)))",
        ["high", "low"],
    ),
    _alpha(
        73, "gtja_alpha73", "volume", "negative", 30,
        "GTJA #73: -(TSRANK(DECAYLINEAR(DECAYLINEAR(CORR(CLOSE,VOL,10),16),4),5) - "
        "RANK(DECAYLINEAR(CORR(VWAP,MEAN(VOL,30),4),3))).",
        "0 - (ts_rank(decay_linear(decay_linear(correlation(close, volume, 10), 16), "
        "4), 5) - rank(decay_linear(correlation(vwap, sma(volume, 30), 4), 3)))",
        ["close", "volume", "vwap"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        77, "gtja_alpha77", "reversal", "negative", 40,
        "GTJA #77: MIN(RANK(DECAYLINEAR((HIGH+LOW)/2 - VWAP, 20)), "
        "RANK(DECAYLINEAR(CORR(mid, MEAN(VOL,40),3),6))).",
        "minimum(rank(decay_linear((high + low) / 2 - vwap, 20)), "
        "rank(decay_linear(correlation((high + low) / 2, sma(volume, 40), 3), 6)))",
        ["high", "low", "volume", "vwap"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        78, "gtja_alpha78", "reversal", "positive", 12,
        "GTJA #78: (typical - its 12-day mean) / (0.015 * mean absolute deviation of "
        "close from that mean).",
        "((high + low + close) / 3 - sma((high + low + close) / 3, 12)) / "
        "(0.015 * sma(abs(close - sma((high + low + close) / 3, 12)), 12))",
        ["high", "low", "close"],
    ),
    _alpha(
        86, "gtja_alpha86", "momentum", "positive", 20,
        "GTJA #86: the ten-day-leg comparison — -1 above the 0.25 threshold, +1 when "
        "the recent leg faded, else -delta(close,1).",
        "where(greater_than(((lag(close, 20) - lag(close, 10)) / 10) - "
        "((lag(close, 10) - close) / 10), 0.25), 0 - 1, "
        "where(less_than(((lag(close, 20) - lag(close, 10)) / 10) - "
        "((lag(close, 10) - close) / 10), 0), 1, "
        "(0 - 1) * (close - lag(close, 1))))",
        ["close"],
    ),
    _alpha(
        87, "gtja_alpha87", "reversal", "positive", 11,
        "GTJA #87: -(RANK(DECAYLINEAR(DELTA(VWAP,4),7)) + "
        "TSRANK(DECAYLINEAR((LOW-VWAP)/(OPEN-(HIGH+LOW)/2), 11), 7)).",
        "0 - (rank(decay_linear(delta(vwap, 4), 7)) + "
        "ts_rank(decay_linear((low - vwap) / (open - (high + low) / 2), 11), 7))",
        ["high", "low", "open", "vwap"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        89, "gtja_alpha89", "trend", "positive", 27,
        "GTJA #89: 2*(SMA(CLOSE,13,2) - SMA(CLOSE,27,2) - "
        "SMA(that,10,2)) — a Wilder-smoothed MACD.",
        "2 * ((wilder(close, 13, 2) - wilder(close, 27, 2)) - "
        "wilder(wilder(close, 13, 2) - wilder(close, 27, 2), 10, 2))",
        ["close"],
    ),
    _alpha(
        93, "gtja_alpha93", "reversal", "positive", 20,
        "GTJA #93: SUM over 20 days of MAX(OPEN-LOW, OPEN-DELAY(OPEN,1)) on days the "
        "open did not rise.",
        "ts_sum(where(1 - less_than(open, lag(open, 1)), 0, "
        "maximum(open - low, open - lag(open, 1))), 20)",
        ["open", "low"],
    ),
    _alpha(
        104, "gtja_alpha104", "volume", "negative", 20,
        "GTJA #104: -1 * DELTA(CORR(HIGH,VOL,5),5) * RANK(STD(CLOSE,20)).",
        "0 - (delta(correlation(high, volume, 5), 5) * "
        "rank(rolling_std(close, 20)))",
        ["high", "volume", "close"], requires_panel=True,
    ),
    _alpha(
        107, "gtja_alpha107", "reversal", "negative", 1,
        "GTJA #107: -RANK(OPEN-DELAY(HIGH,1)) * RANK(OPEN-DELAY(CLOSE,1)) * "
        "RANK(OPEN-DELAY(LOW,1)).",
        "(0 - rank(open - lag(high, 1))) * rank(open - lag(close, 1)) * "
        "rank(open - lag(low, 1))",
        ["open", "high", "low", "close"], requires_panel=True,
    ),
    _alpha(
        113, "gtja_alpha113", "volume", "negative", 20,
        "GTJA #113: -RANK(SUM(DELAY(CLOSE,5),20)/20) * CORR(CLOSE,VOL,2) * "
        "RANK(CORR(SUM(CLOSE,5), SUM(CLOSE,20), 2)).",
        "0 - rank(sma(lag(close, 5), 20)) * correlation(close, volume, 2) * "
        "rank(correlation(ts_sum(close, 5), ts_sum(close, 20), 2))",
        ["close", "volume"], requires_panel=True,
    ),
    _alpha(
        125, "gtja_alpha125", "volume", "positive", 80,
        "GTJA #125: RANK(DECAYLINEAR(CORR(VWAP,MEAN(VOL,80),17),20)) / "
        "RANK(DECAYLINEAR(DELTA(CLOSE*0.5+VWAP*0.5,3),16)).",
        "rank(decay_linear(correlation(vwap, sma(volume, 80), 17), 20)) / "
        "rank(decay_linear(delta(close * 0.5 + vwap * 0.5, 3), 16))",
        ["vwap", "close", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        136, "gtja_alpha136", "volume", "negative", 10,
        "GTJA #136: -RANK(DELTA(RET,3)) * CORR(OPEN,VOL,10).",
        "(0 - rank(delta(pct_change(close, 1), 3))) * "
        "correlation(open, volume, 10)",
        ["close", "open", "volume"], requires_panel=True,
    ),
    _alpha(
        142, "gtja_alpha142", "volume", "negative", 10,
        "GTJA #142: -RANK(TSRANK(CLOSE,10)) * RANK(DELTA(DELTA(CLOSE,1),1)) * "
        "RANK(TSRANK(VOL/MEAN(VOL,20),5)).",
        "0 - rank(ts_rank(close, 10)) * rank(delta(delta(close, 1), 1)) * "
        "rank(ts_rank(volume / sma(volume, 20), 5))",
        ["close", "volume"], requires_panel=True,
    ),
    _alpha(
        144, "gtja_alpha144", "reversal", "negative", 20,
        "GTJA #144: SUMIF(|CLOSE/DELAY(CLOSE,1)-1|/AMOUNT, 20, CLOSE<DELAY(CLOSE,1)) "
        "divided by the count of down days. Declares the `amount` input.",
        "ts_sum(where(less_than(close, lag(close, 1)), "
        "abs(close / lag(close, 1) - 1) / amount, 0), 20) / "
        "(rolling_mean(less_than(close, lag(close, 1)), 20) * 20)",
        ["close", "amount"], requires_inputs=("amount",),
    ),
    _alpha(
        152, "gtja_alpha152", "trend", "positive", 26,
        "GTJA #152: Wilder-SMA(9,1) of the 12-vs-26 mean spread of the delayed "
        "nine-day price ratio.",
        "wilder(sma(lag(wilder(lag(close / lag(close, 9), 1), 9, 1), 1), 12) - "
        "sma(lag(wilder(lag(close / lag(close, 9), 1), 9, 1), 1), 26), 9, 1)",
        ["close"],
    ),
    _alpha(
        166, "gtja_alpha166", "reversal", "negative", 20,
        "GTJA #166: the 20-day return skewness with the paper's coefficients "
        "(-n(n-1)^1.5 ... ), guarded so a non-positive denominator yields 0.",
        "where(greater_than((20 - 1) * (20 - 2) * "
        "ts_sum(pct_change(close, 1) ^ 2, 20) ^ 1.5, 0), "
        "(0 - 20) * (20 - 1) ^ 1.5 * "
        "ts_sum(pct_change(close, 1) - sma(pct_change(close, 1), 20), 20) / "
        "((20 - 1) * (20 - 2) * ts_sum(pct_change(close, 1) ^ 2, 20) ^ 1.5), 0)",
        ["close"],
    ),
    _alpha(
        169, "gtja_alpha169", "reversal", "positive", 26,
        "GTJA #169: Wilder-SMA(10,1) of the 12-vs-26 mean spread of the delayed "
        "nine-day Wilder-smoothed close change.",
        "wilder(sma(lag(wilder(close - lag(close, 1), 9, 1), 1), 12) - "
        "sma(lag(wilder(close - lag(close, 1), 9, 1), 1), 26), 10, 1)",
        ["close"],
    ),
    _alpha(
        187, "gtja_alpha187", "reversal", "positive", 20,
        "GTJA #187: SUM over 20 days of MAX(HIGH-OPEN, OPEN-DELAY(OPEN,1)) on days "
        "the open did not fall.",
        "ts_sum(where(1 - greater_than(open, lag(open, 1)), 0, "
        "maximum(high - open, open - lag(open, 1))), 20)",
        ["open", "high"],
    ),
    # -- tranche 11: the cross-sectional-rank-inside-a-rolling-correlation family.
    #
    # A self-correction: earlier docs claimed this evaluator "refuses" that nesting.
    # It does not, and it never did. `rank(...)` in the panel evaluator returns a
    # T x N array of per-date cross-sectional ranks, and `correlation(...)` then
    # runs column-wise over time, so `correlation(rank(a), rank(b), n)` is exactly
    # the published operation. (The per-series engine's `rank` is a time-series
    # percentile, which is why every alpha here is flagged `requiresPanel`.)
    _alpha(
        16, "gtja_alpha16", "volume", "negative", 5,
        "GTJA #16: -RANK(COV(RANK(HIGH), RANK(VOLUME), 5)).",
        "0 - rank(covariance(rank(high), rank(volume), 5))",
        ["high", "volume"], requires_panel=True,
    ),
    _alpha(
        32, "gtja_alpha32", "volume", "negative", 6,
        "GTJA #32: -SUM(RANK(CORR(RANK(HIGH), RANK(VOL), 3)), 3).",
        "0 - ts_sum(rank(correlation(rank(high), rank(volume), 3)), 3)",
        ["high", "volume"], requires_panel=True,
    ),
    _alpha(
        36, "gtja_alpha36", "volume", "positive", 7,
        "GTJA #36: RANK(SUM(CORR(RANK(VOL),RANK(VWAP),6), 2)).",
        "rank(ts_sum(correlation(rank(volume), rank(vwap), 6), 2))",
        ["volume", "vwap"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        55, "gtja_alpha55", "volume", "negative", 12,
        "GTJA #55: -CORR(RANK(close position inside the 12-day range), RANK(VOL), 6).",
        "0 - correlation(rank((close - rolling_min(low, 12)) / "
        "(rolling_max(high, 12) - rolling_min(low, 12))), rank(volume), 6)",
        ["high", "low", "close", "volume"], requires_panel=True,
    ),
    _alpha(
        62, "gtja_alpha62", "volume", "negative", 5,
        "GTJA #62: -CORR(HIGH, RANK(VOLUME), 5).",
        "0 - correlation(high, rank(volume), 5)",
        ["high", "volume"], requires_panel=True,
    ),
    _alpha(
        74, "gtja_alpha74", "volume", "positive", 40,
        "GTJA #74: RANK(CORR(SUM(LOW*0.35+VWAP*0.65,20), SUM(MEAN(VOL,40),20),7)) + "
        "RANK(CORR(RANK(VWAP), RANK(VOL),6)).",
        "rank(correlation(ts_sum(low * 0.35 + vwap * 0.65, 20), "
        "ts_sum(sma(volume, 40), 20), 7)) + "
        "rank(correlation(rank(vwap), rank(volume), 6))",
        ["low", "vwap", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        83, "gtja_alpha83", "volume", "negative", 5,
        "GTJA #83: -RANK(COV(RANK(HIGH), RANK(VOLUME), 5)) — the published form is "
        "identical to #16; both are kept as published.",
        "0 - rank(covariance(rank(high), rank(volume), 5))",
        ["high", "volume"], requires_panel=True,
    ),
    _alpha(
        90, "gtja_alpha90", "volume", "negative", 5,
        "GTJA #90: -RANK(CORR(RANK(VWAP), RANK(VOLUME), 5)).",
        "0 - rank(correlation(rank(vwap), rank(volume), 5))",
        ["vwap", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        99, "gtja_alpha99", "volume", "negative", 5,
        "GTJA #99: -RANK(COV(RANK(CLOSE), RANK(VOLUME), 5)).",
        "0 - rank(covariance(rank(close), rank(volume), 5))",
        ["close", "volume"], requires_panel=True,
    ),
    _alpha(
        101, "gtja_alpha101", "volume", "negative", 37,
        "GTJA #101: -1 * (RANK(CORR(CLOSE, SUM(MEAN(VOL,30),37),15)) < "
        "RANK(CORR(RANK(HIGH*0.1+VWAP*0.9), RANK(VOL),11))) — a boolean factor.",
        "0 - less_than(rank(correlation(close, ts_sum(sma(volume, 30), 37), 15)), "
        "rank(correlation(rank(high * 0.1 + vwap * 0.9), rank(volume), 11)))",
        ["close", "high", "vwap", "volume"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        105, "gtja_alpha105", "volume", "negative", 10,
        "GTJA #105: -CORR(RANK(OPEN), RANK(VOLUME), 10).",
        "0 - correlation(rank(open), rank(volume), 10)",
        ["open", "volume"], requires_panel=True,
    ),
    _alpha(
        119, "gtja_alpha119", "volume", "positive", 80,
        "GTJA #119: RANK(DECAY(CORR(VWAP, SUM(MEAN(VOL,5),26),5),7)) - "
        "RANK(DECAY(TSRANK(TSMIN(CORR(RANK(OPEN),RANK(MEAN(VOL,15)),21),9),7),8)).",
        "rank(decay_linear(correlation(vwap, ts_sum(sma(volume, 5), 26), 5), 7)) - "
        "rank(decay_linear(ts_rank(rolling_min(correlation(rank(open), "
        "rank(sma(volume, 15)), 21), 9), 7), 8))",
        ["vwap", "volume", "open"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        130, "gtja_alpha130", "volume", "positive", 40,
        "GTJA #130: RANK(DECAY(CORR(mid, MEAN(VOL,40),9),10)) / "
        "RANK(DECAY(CORR(RANK(VWAP), RANK(VOL),7),3)).",
        "rank(decay_linear(correlation((high + low) / 2, sma(volume, 40), 9), 10)) / "
        "rank(decay_linear(correlation(rank(vwap), rank(volume), 7), 3))",
        ["high", "low", "vwap", "volume"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        141, "gtja_alpha141", "volume", "negative", 15,
        "GTJA #141: -RANK(CORR(RANK(HIGH), RANK(MEAN(VOL,15)), 9)).",
        "0 - rank(correlation(rank(high), rank(sma(volume, 15)), 9))",
        ["high", "volume"], requires_panel=True,
    ),
    _alpha(
        176, "gtja_alpha176", "volume", "positive", 12,
        "GTJA #176: CORR(RANK(close position inside the 12-day range), RANK(VOL), 6).",
        "correlation(rank(where(greater_than(rolling_max(high, 12) - "
        "rolling_min(low, 12), 0), (close - rolling_min(low, 12)) / "
        "(rolling_max(high, 12) - rolling_min(low, 12)), 0)), rank(volume), 6)",
        ["high", "low", "close", "volume"], requires_panel=True,
    ),
    _alpha(
        179, "gtja_alpha179", "volume", "positive", 50,
        "GTJA #179: RANK(CORR(VWAP,VOL,4)) * RANK(CORR(RANK(LOW), "
        "RANK(MEAN(VOL,50)),12)).",
        "rank(correlation(vwap, volume, 4)) * "
        "rank(correlation(rank(low), rank(sma(volume, 50)), 12))",
        ["vwap", "volume", "low"], requires_panel=True, requires_inputs=("vwap",),
    ),
    # -- tranche 12: the verifiable remainder, transcribed one-to-one from the
    # published implementation. The formulas deliberately NOT taken (69, 91, 137,
    # 159, 172, 186, 190) are listed with their specific blockers in
    # `docs/quant-engine.md`; each would need a guess about an ambiguous published
    # form, which is the one thing this zoo does not do.
    _alpha(
        17, "gtja_alpha17", "volume", "negative", 15,
        "GTJA #17: RANK(VWAP - TSMAX(VWAP,15)) ^ DELTA(CLOSE,5). A zero rank with a "
        "negative exponent is inf by the formula's own construction.",
        "rank(vwap - rolling_max(vwap, 15)) ^ delta(close, 5)",
        ["vwap", "close"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        28, "gtja_alpha28", "reversal", "positive", 9,
        "GTJA #28: 3*SMA(RSI9,3,1) - 2*SMA(SMA(RSI9,3,1),3,1) — a doubly smoothed "
        "nine-day RSI, in percent.",
        "3 * wilder(where(greater_than(rolling_max(high, 9) - rolling_min(low, 9), 0), (close - rolling_min(low, 9)) / (rolling_max(high, 9) - rolling_min(low, 9)) * 100, 0), 3, 1) - 2 * wilder(wilder(where(greater_than(rolling_max(high, 9) - rolling_min(low, 9), 0), (close - rolling_min(low, 9)) / (rolling_max(high, 9) - rolling_min(low, 9)) * 100, 0), 3, 1), 3, 1)",
        ["high", "low", "close"],
    ),
    _alpha(
        61, "gtja_alpha61", "volume", "negative", 80,
        "GTJA #61: -1 * MAX(RANK(DECAY(DELTA(VWAP,1),12)), "
        "RANK(DECAY(RANK(CORR(LOW,MEAN(VOL,80),8)),17))).",
        "0 - maximum(rank(decay_linear(delta(vwap, 1), 12)), "
        "rank(decay_linear(rank(correlation(low, sma(volume, 80), 8)), 17)))",
        ["vwap", "low", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        64, "gtja_alpha64", "volume", "negative", 60,
        "GTJA #64: -1 * MAX(RANK(DECAY(CORR(RANK(VWAP),RANK(VOL),4),4)), "
        "RANK(DECAY(TSMAX(CORR(RANK(CLOSE),RANK(MEAN(VOL,60)),4),13),14))) — the "
        "inner MAX is read as a rolling 13-day max, GTJA's own convention.",
        "0 - maximum(rank(decay_linear(correlation(rank(vwap), rank(volume), 4), 4)), "
        "rank(decay_linear(rolling_max(correlation(rank(close), "
        "rank(sma(volume, 60)), 4), 13), 14)))",
        ["vwap", "volume", "close"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        75, "gtja_alpha75", "reversal", "positive", 50,
        "GTJA #75: COUNT(CLOSE>OPEN and the benchmark fell, 50) / "
        "COUNT(the benchmark fell, 50). Declares both benchmark inputs.",
        "rolling_mean(greater_than(close, open) * "
        "less_than(benchmark_close, benchmark_open), 50) / "
        "rolling_mean(less_than(benchmark_close, benchmark_open), 50)",
        ["open", "close", "benchmark_open", "benchmark_close"],
        requires_inputs=("benchmark_open", "benchmark_close"),
    ),
    _alpha(
        76, "gtja_alpha76", "volatility", "negative", 20,
        "GTJA #76: STD(|CLOSE/DELAY(CLOSE,1)-1|/VOLUME, 20) / its own 20-day mean.",
        "rolling_std(abs(close / lag(close, 1) - 1) / volume, 20) / "
        "sma(abs(close / lag(close, 1) - 1) / volume, 20)",
        ["close", "volume"],
    ),
    _alpha(
        81, "gtja_alpha81", "volume", "positive", 21,
        "GTJA #81: SMA(VOLUME,21,2) — a doubly weighted volume average.",
        "wilder(volume, 21, 2)", ["volume"],
    ),
    _alpha(
        82, "gtja_alpha82", "reversal", "negative", 20,
        "GTJA #82: SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100, 20, 1).",
        "wilder(where(greater_than(rolling_max(high, 6) - rolling_min(low, 6), 0), "
        "(rolling_max(high, 6) - close) / "
        "(rolling_max(high, 6) - rolling_min(low, 6)) * 100, 0), 20, 1)",
        ["high", "low", "close"],
    ),
    _alpha(
        92, "gtja_alpha92", "volume", "negative", 180,
        "GTJA #92: -1 * MAX(RANK(DECAY(DELTA(CLOSE*0.35+VWAP*0.65,2),3)), "
        "TSRANK(DECAY(|CORR(MEAN(VOL,180),CLOSE,13)|,5),15)).",
        "0 - maximum(rank(decay_linear(delta(close * 0.35 + vwap * 0.65, 2), 3)), "
        "ts_rank(decay_linear(abs(correlation(sma(volume, 180), close, 13)), 5), 15))",
        ["close", "vwap", "volume"], requires_panel=True, requires_inputs=("vwap",),
    ),
    _alpha(
        94, "gtja_alpha94", "volume", "positive", 30,
        "GTJA #94: signed volume (up days positive, down days negative), 30 days.",
        "ts_sum(where(greater_than(close, lag(close, 1)), volume, "
        "where(less_than(close, lag(close, 1)), 0 - volume, 0)), 30)",
        ["close", "volume"],
    ),
    _alpha(
        96, "gtja_alpha96", "reversal", "positive", 9,
        "GTJA #96: SMA(SMA(RSV9,3,1),3,1) — the nine-day RSV smoothed twice.",
        "wilder(wilder(where(greater_than(rolling_max(high, 9) - rolling_min(low, 9), 0), (close - rolling_min(low, 9)) / (rolling_max(high, 9) - rolling_min(low, 9)) * 100, 0), 3, 1), 3, 1)", ["high", "low", "close"],
    ),
    _alpha(
        97, "gtja_alpha97", "volatility", "negative", 10,
        "GTJA #97: STD(VOLUME, 10).",
        "rolling_std(volume, 10)", ["volume"],
    ),
    _alpha(
        98, "gtja_alpha98", "reversal", "positive", 100,
        "GTJA #98: when the 100-day mean's change is at most 5% of the lagged close, "
        "-1*(CLOSE - TSMIN(CLOSE,100)); else -DELTA(CLOSE,3).",
        "where(less_than(delta(sma(close, 100), 100) / lag(close, 100), 0.05), "
        "0 - (close - rolling_min(close, 100)), 0 - delta(close, 3))",
        ["close"],
    ),
    _alpha(
        100, "gtja_alpha100", "volatility", "negative", 20,
        "GTJA #100: STD(VOLUME, 20).",
        "rolling_std(volume, 20)", ["volume"],
    ),
    _alpha(
        112, "gtja_alpha112", "reversal", "positive", 12,
        "GTJA #112: (SUM(up)-SUM(down))/(SUM(up)+SUM(down))*100 — a 12-day "
        "directional balance.",
        "ts_sum(where(greater_than(close - lag(close, 1), 0), close - lag(close, 1), 0), 12) / (ts_sum(where(greater_than(close - lag(close, 1), 0), close - lag(close, 1), 0), 12) + ts_sum(where(less_than(close - lag(close, 1), 0), abs(close - lag(close, 1)), 0), 12)) - ts_sum(where(less_than(close - lag(close, 1), 0), abs(close - lag(close, 1)), 0), 12) / (ts_sum(where(greater_than(close - lag(close, 1), 0), close - lag(close, 1), 0), 12) + ts_sum(where(less_than(close - lag(close, 1), 0), abs(close - lag(close, 1)), 0), 12))",
        ["close"],
    ),
    _alpha(
        114, "gtja_alpha114", "volume", "positive", 5,
        "GTJA #114: RANK(DELAY((HIGH-LOW)/(SUM(CLOSE,5)/5),2)) * RANK(RANK(VOL)) / "
        "(((HIGH-LOW)/(SUM(CLOSE,5)/5)) / (VWAP - CLOSE)).",
        "(rank(lag((high - low) / sma(close, 5), 2)) * rank(rank(volume))) / "
        "(((high - low) / sma(close, 5)) / (vwap - close))",
        ["high", "low", "close", "volume", "vwap"], requires_panel=True,
        requires_inputs=("vwap",),
    ),
    _alpha(
        140, "gtja_alpha140", "volume", "positive", 60,
        "GTJA #140: MIN(RANK(DECAY(RANK(OPEN)+RANK(LOW)-RANK(HIGH)-RANK(CLOSE),8)), "
        "TSRANK(DECAY(CORR(TSRANK(CLOSE,8),TSRANK(MEAN(VOL,60),20),8),7),3)).",
        "minimum(rank(decay_linear(rank(open) + rank(low) - rank(high) - "
        "rank(close), 8)), ts_rank(decay_linear(correlation(ts_rank(close, 8), "
        "ts_rank(sma(volume, 60), 20), 8), 7), 3))",
        ["open", "high", "low", "close", "volume"], requires_panel=True,
    ),
    # -- tranche 13: the last formulas whose published source settles the form.
    # `#69` needed GTJA's `DTM`/`DBM`, now read from `src/lib/special.py`:
    # DTM = MAX(HIGH-OPEN, OPEN-DELAY(OPEN)) when the open gapped up, else 0;
    # DBM = MAX(OPEN-LOW, OPEN-DELAY(OPEN)) when it gapped down, else 0 (the second
    # term keeps its sign, exactly as published).
    _alpha(
        69, "gtja_alpha69", "reversal", "positive", 20,
        "GTJA #69: when the 20-day up-gap sum exceeds the down-gap sum, "
        "(up-down)/up; when equal, 0; else (up-down)/down.",
        'where(greater_than(ts_sum(where(greater_than(open, lag(open, 1)), maximum(high - open, open - lag(open, 1)), 0), 20), ts_sum(where(less_than(open, lag(open, 1)), maximum(open - low, open - lag(open, 1)), 0), 20)), (ts_sum(where(greater_than(open, lag(open, 1)), maximum(high - open, open - lag(open, 1)), 0), 20) - ts_sum(where(less_than(open, lag(open, 1)), maximum(open - low, open - lag(open, 1)), 0), 20)) / ts_sum(where(greater_than(open, lag(open, 1)), maximum(high - open, open - lag(open, 1)), 0), 20), where(less_than(abs(sign(ts_sum(where(greater_than(open, lag(open, 1)), maximum(high - open, open - lag(open, 1)), 0), 20) - ts_sum(where(less_than(open, lag(open, 1)), maximum(open - low, open - lag(open, 1)), 0), 20))), 0.5), 0, (ts_sum(where(greater_than(open, lag(open, 1)), maximum(high - open, open - lag(open, 1)), 0), 20) - ts_sum(where(less_than(open, lag(open, 1)), maximum(open - low, open - lag(open, 1)), 0), 20)) / ts_sum(where(less_than(open, lag(open, 1)), maximum(open - low, open - lag(open, 1)), 0), 20)))',
        ["open", "high", "low"],
    ),
    _alpha(
        91, "gtja_alpha91", "volume", "negative", 5,
        "GTJA #91: -1 * RANK(CLOSE - MAX(CLOSE,5)) * RANK(CORR(MEAN(VOL,40),LOW,5)). "
        "`MAX(CLOSE,5)` is read as a rolling five-day max — GTJA's own `MAX(X,N)` "
        "convention; the elementwise reading would be a different factor.",
        '0 - rank(close - rolling_max(close, 5)) * rank(correlation(sma(volume, 40), low, 5))',
        ["close", "low", "volume"], requires_panel=True,
    ),
    _alpha(
        137, "gtja_alpha137", "volatility", "positive", 1,
        "GTJA #137: the ATR-variant numerator over its true-range product (Alpha#55's "
        "inner term, without the 20-day sum).",
        '16 * (close - lag(close, 1) + (close - open) / 2 + lag(close, 1) - lag(open, 1)) / (where(greater_than(abs(high - lag(close, 1)), abs(low - lag(close, 1))) * greater_than(abs(high - lag(close, 1)), abs(high - lag(low, 1))), abs(high - lag(close, 1)) + abs(low - lag(close, 1)) / 2 + abs(lag(close, 1) - lag(open, 1)) / 4, where(greater_than(abs(low - lag(close, 1)), abs(high - lag(low, 1))) * greater_than(abs(low - lag(close, 1)), abs(high - lag(close, 1))), abs(low - lag(close, 1)) + abs(high - lag(close, 1)) / 2 + abs(lag(close, 1) - lag(open, 1)) / 4, abs(high - lag(low, 1)) + abs(lag(close, 1) - lag(open, 1)) / 4)) * maximum(abs(high - lag(close, 1)), abs(low - lag(close, 1))))',
        ["open", "high", "low", "close"],
    ),
    _alpha(
        172, "gtja_alpha172", "reversal", "negative", 20,
        "GTJA #172: MEAN over 6 days of |up-DI - down-DI| / (up-DI + down-DI) * 100 "
        "on a 14-day true range.",
        'sma(abs(ts_sum(where(greater_than(lag(low, 1) - low, 0) * greater_than(lag(low, 1) - low, high - lag(high, 1)), lag(low, 1) - low, 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14) - ts_sum(where(greater_than(high - lag(high, 1), 0) * greater_than(high - lag(high, 1), lag(low, 1) - low), high - lag(high, 1), 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14)) / (ts_sum(where(greater_than(lag(low, 1) - low, 0) * greater_than(lag(low, 1) - low, high - lag(high, 1)), lag(low, 1) - low, 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14) + ts_sum(where(greater_than(high - lag(high, 1), 0) * greater_than(high - lag(high, 1), lag(low, 1) - low), high - lag(high, 1), 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14)) * 100, 6)',
        ["high", "low", "close"],
    ),
    _alpha(
        190, "gtja_alpha190", "reversal", "positive", 20,
        "GTJA #190: LOG((COUNT(r>g,20)-1) * SUMIF((r-g)^2 on r<g) / "
        "(COUNT(r<g,20) * SUMIF((r-g)^2 on r>g))), g the 20-day geometric daily "
        "return. The published asymmetric guards are kept.",
        'where(greater_than((((rolling_mean(greater_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), 20) * 20) - 1) * ts_sum(where(less_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), (pct_change(close, 1) - ((close / lag(close, 19)) ^ (1 / 20) - 1)) ^ 2, 0), 20)) / ((rolling_mean(less_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), 20) * 20) * ts_sum(where(greater_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), (pct_change(close, 1) - ((close / lag(close, 19)) ^ (1 / 20) - 1)) ^ 2, 0), 20)), 0), log((((rolling_mean(greater_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), 20) * 20) - 1) * ts_sum(where(less_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), (pct_change(close, 1) - ((close / lag(close, 19)) ^ (1 / 20) - 1)) ^ 2, 0), 20)) / ((rolling_mean(less_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), 20) * 20) * ts_sum(where(greater_than(pct_change(close, 1), ((close / lag(close, 19)) ^ (1 / 20) - 1)), (pct_change(close, 1) - ((close / lag(close, 19)) ^ (1 / 20) - 1)) ^ 2, 0), 20))), 0)',
        ["close"],
    ),
    # -- tranche 14: the last two, resolved by a second published implementation
    # (NeoSPQR404/gtja191-research, `src/Alpha_Set.py`).
    #
    # #159's weights agree between that reference and lrb777's port (12*24, 6*24,
    # 6*24 over the denominator 6*12+6*24+12*24), so the "erratum" I inferred was
    # wrong: two independent transcriptions match, which IS the verification.
    #
    # #172/#186 use the reference's STANDARD Wilder true range
    # max(max(high-low, |high-prev_close|), |low-prev_close|). lrb777's port uses a
    # different TR (max(|HD|,|LD|,|high-prev_low|)); the standard definition is used
    # for both here so the pair stays internally consistent.
    _alpha(
        159, "gtja_alpha159", "reversal", "positive", 24,
        "GTJA #159: the three-horizon (6/12/24) share of the close above "
        "MIN(LOW, prev_close), weighted 12*24 / 6*24 / 6*24 and normalised by "
        "6*12+6*24+12*24.",
        '((close - ts_sum(minimum(low, lag(close, 1)), 6)) / ts_sum((maximum(high, lag(close, 1)) - minimum(low, lag(close, 1))), 6) * 12 * 24 + (close - ts_sum(minimum(low, lag(close, 1)), 12)) / ts_sum((maximum(high, lag(close, 1)) - minimum(low, lag(close, 1))), 12) * 6 * 24 + (close - ts_sum(minimum(low, lag(close, 1)), 24)) / ts_sum((maximum(high, lag(close, 1)) - minimum(low, lag(close, 1))), 24) * 6 * 24) * 100 / (6 * 12 + 6 * 24 + 12 * 24)',
        ["high", "low", "close"],
    ),
    _alpha(
        186, "gtja_alpha186", "reversal", "negative", 20,
        "GTJA #186: the #172 DMI expression averaged with its own six-day lag.",
        '(sma(abs(ts_sum(where(greater_than(lag(low, 1) - low, 0) * greater_than(lag(low, 1) - low, high - lag(high, 1)), lag(low, 1) - low, 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14) - ts_sum(where(greater_than(high - lag(high, 1), 0) * greater_than(high - lag(high, 1), lag(low, 1) - low), high - lag(high, 1), 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14)) / (ts_sum(where(greater_than(lag(low, 1) - low, 0) * greater_than(lag(low, 1) - low, high - lag(high, 1)), lag(low, 1) - low, 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14) + ts_sum(where(greater_than(high - lag(high, 1), 0) * greater_than(high - lag(high, 1), lag(low, 1) - low), high - lag(high, 1), 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14)) * 100, 6) + lag(sma(abs(ts_sum(where(greater_than(lag(low, 1) - low, 0) * greater_than(lag(low, 1) - low, high - lag(high, 1)), lag(low, 1) - low, 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14) - ts_sum(where(greater_than(high - lag(high, 1), 0) * greater_than(high - lag(high, 1), lag(low, 1) - low), high - lag(high, 1), 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14)) / (ts_sum(where(greater_than(lag(low, 1) - low, 0) * greater_than(lag(low, 1) - low, high - lag(high, 1)), lag(low, 1) - low, 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14) + ts_sum(where(greater_than(high - lag(high, 1), 0) * greater_than(high - lag(high, 1), lag(low, 1) - low), high - lag(high, 1), 0), 14) * 100 / ts_sum(maximum(maximum(high - low, abs(high - lag(close, 1))), abs(low - lag(close, 1))), 14)) * 100, 6), 6)) / 2',
        ["high", "low", "close"],
    ),
    ]


__all__ = ["extra_alphas"]
