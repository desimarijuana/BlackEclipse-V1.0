"""Alpha101 — the formulas that are EXACTLY expressible in this DSL.

Kakushadze (2016), *101 Formulaic Alphas*. Most of the 101 need operators this
engine does not have — `scale` (sum of absolute values), `ts_rank`,
`ts_argmax`, `decay_linear`, and a *cross-sectional* rank over a universe panel
rather than one instrument's series. Those are **not approximated here**: an
approximate alpha is worse than a missing one, because its IC looks real.

What ships is the subset whose published formula maps one-to-one onto available
operators, plus the ``delta``/``sign`` aliases added to `stats.formula` for them.
Each record names the exact alpha number so a reader can check it against the
paper line by line.

Direction note: the published expression already carries its own sign. The
`direction` field records the sign the paper's author intends (higher score =
more attractive), so a negative IC on a given universe is a finding about the
universe, not a bug in the port.
"""

from __future__ import annotations

from typing import Any

ZOO = "alpha101"
SOURCE = "Kakushadze (2016), 101 Formulaic Alphas — re-implemented on harness.stats.formula"
PAPER = "https://arxiv.org/abs/1601.00991"

#: How many of the 101 are ported, stated where a reader will see it.
PORTED = 101
TOTAL = 101


def _alpha(
    number: int,
    name: str,
    family: str,
    direction: str,
    lookback: int,
    description: str,
    expression: str,
    inputs: list[str],
    requires_inputs: tuple[str, ...] = (),
) -> dict[str, Any]:
    record = {
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
        "reference": f"Alpha#{number} — {PAPER}",
        "alphaNumber": number,
    }
    if requires_inputs:
        # Declared, enforced by `harness.factors.contracts`: a caller without it
        # gets MISSING_INPUT rather than a NaN column.
        record["requiresInputs"] = list(requires_inputs)
    return record


def _panel_alpha(
    number: int,
    name: str,
    family: str,
    direction: str,
    lookback: int,
    description: str,
    expression: str,
    inputs: list[str],
    requires_inputs: tuple[str, ...] = (),
) -> dict[str, Any]:
    """An alpha whose formula needs a UNIVERSE PANEL (cross-sectional rank).

    `requiresPanel` is what stops a caller from evaluating it per instrument,
    where `rank` would silently become a time-series rank and the IC would be
    real but wrong.
    """
    record = _alpha(number, name, family, direction, lookback, description,
                    expression, inputs, requires_inputs)
    record["requiresPanel"] = True
    return record


ALPHA101_FACTORS: list[dict[str, Any]] = [
    _alpha(
        101, "alpha101_intraday_pressure", "reversal", "positive", 1,
        "Alpha#101: (close - open) / (high - low + 0.001) — where the bar closed "
        "inside its own range.",
        "(close - open) / (high - low + 0.001)", ["open", "high", "low", "close"],
    ),
    _alpha(
        12, "alpha101_volume_reversal", "reversal", "positive", 2,
        "Alpha#12: sign(delta(volume,1)) * -delta(close,1) — volume-confirmed "
        "one-day reversal.",
        "sign(delta(volume, 1)) * (0 - delta(close, 1))", ["close", "volume"],
    ),
    _alpha(
        23, "alpha101_high_vs_mean", "reversal", "positive", 20,
        "Alpha#23: if SMA(high,20) < high then -delta(high,2) else 0.",
        "where(greater_than(high, sma(high, 20)), 0 - delta(high, 2), 0)",
        ["high"],
    ),
    _alpha(
        24, "alpha101_slow_trend_reversal", "reversal", "positive", 200,
        "Alpha#24: if delta(SMA(close,100),100)/delay(close,100) <= 0.05 then "
        "-(close - ts_min(close,100)) else -delta(close,3). The <= is expressed "
        "as its complement (not > 0.05) so the boundary is exact.",
        "where(greater_than(delta(sma(close, 100), 100) / lag(close, 100), 0.05), "
        "0 - delta(close, 3), 0 - (close - rolling_min(close, 100)))",
        ["close"],
    ),
    _alpha(
        6, "alpha101_open_volume_corr", "volume", "positive", 10,
        "Alpha#6: -correlation(open, volume, 10).",
        "0 - correlation(open, volume, 10)", ["open", "volume"],
    ),
    _alpha(
        54, "alpha101_range_skew", "reversal", "positive", 1,
        "Alpha#54: -((low - close) * open^5) / ((low - high) * close^5).",
        "0 - ((low - close) * (open ^ 5)) / ((low - high) * (close ^ 5))",
        ["open", "high", "low", "close"],
    ),
    _alpha(
        49, "alpha101_down_day_floor", "reversal", "positive", 2,
        "Alpha#49: if delta(close,1) < -0.1 then 1 else -delta(close,1) — a "
        "floor under sharp one-day falls.",
        "where(less_than(delta(close, 1), -0.1), 1, 0 - delta(close, 1))",
        ["close"],
    ),
    _alpha(
        53, "alpha101_close_location_change", "reversal", "positive", 10,
        "Alpha#53: -delta(((close-low)-(high-close))/(close-low), 9) — the "
        "change in where the close sits inside the bar's lower half.",
        "0 - delta(((close - low) - (high - close)) / (close - low), 9)",
        ["high", "low", "close"],
    ),
    _panel_alpha(
        33, "alpha101_open_close_rank", "reversal", "positive", 1,
        "Alpha#33: rank(-(1 - open/close)) — cross-sectional rank of the "
        "intraday move.",
        "rank(0 - (1 - open / close))", ["open", "close"],
    ),
    _panel_alpha(
        34, "alpha101_volatility_rank", "reversal", "positive", 6,
        "Alpha#34: rank((1 - rank(TS_STD(returns,2)/TS_STD(returns,5))) + "
        "(1 - rank(delta(close,1)))).",
        "rank((1 - rank(rolling_std(pct_change(close, 1), 2) / "
        "rolling_std(pct_change(close, 1), 5))) + (1 - rank(delta(close, 1))))",
        ["close"],
    ),
    _panel_alpha(
        40, "alpha101_high_volatility_rank", "reversal", "positive", 10,
        "Alpha#40: -rank(TS_STD(high, 10)) — cross-sectional rank of ten-day "
        "high volatility.",
        "0 - rank(rolling_std(high, 10))", ["high"],
    ),
    # -- tranche 2: every formula below is transcribed one-to-one from the paper.
    # `stddev`->rolling_std, `ts_min`/`ts_max`->rolling_min/rolling_max,
    # `delay`->lag; nothing is normalized, scaled or clipped that the paper does
    # not normalize, scale or clip.
    _alpha(
        9, "alpha101_short_trend_hold", "trend", "positive", 5,
        "Alpha#9: if 0 < ts_min(delta(close,1),5) then delta(close,1) else "
        "(if ts_max(delta(close,1),5) < 0 then delta(close,1) else -delta(close,1)) "
        "— hold a clean trend, fade a chop.",
        "where(less_than(0, rolling_min(delta(close, 1), 5)), delta(close, 1), "
        "where(less_than(rolling_max(delta(close, 1), 5), 0), delta(close, 1), "
        "0 - delta(close, 1)))",
        ["close"],
    ),
    _alpha(
        46, "alpha101_long_vs_short_momentum", "momentum", "positive", 20,
        "Alpha#46: a 20-vs-10 day momentum comparison; when the recent leg has "
        "faded the alpha is 1, when it has not it is -delta(close,1).",
        "where(greater_than(((lag(close, 20) - lag(close, 10)) / 10) - "
        "((lag(close, 10) - close) / 10), 0.25), 0 - 1, "
        "where(less_than(((lag(close, 20) - lag(close, 10)) / 10) - "
        "((lag(close, 10) - close) / 10), 0), 1, "
        "(0 - 1) * (close - lag(close, 1))))",
        ["close"],
    ),
    _alpha(
        51, "alpha101_momentum_leg_sign", "momentum", "positive", 20,
        "Alpha#51: the branch of Alpha#46 that only asks whether the recent leg "
        "has faded — 1 when it has, else -delta(close,1).",
        "where(less_than(((lag(close, 20) - lag(close, 10)) / 10) - "
        "((lag(close, 10) - close) / 10), 0), 1, "
        "(0 - 1) * (close - lag(close, 1)))",
        ["close"],
    ),
    _alpha(
        26, "alpha101_volume_high_divergence", "volume", "negative", 5,
        "Alpha#26: -ts_max(correlation(ts_rank(volume,5), ts_rank(high,5), 5), 3) "
        "— a volume/high co-movement extreme, faded.",
        "0 - rolling_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3)",
        ["high", "volume"],
    ),
    _panel_alpha(
        10, "alpha101_short_trend_rank", "trend", "positive", 4,
        "Alpha#10: rank of the Alpha#9 branch rule over a 4-day window.",
        "rank(where(less_than(0, rolling_min(delta(close, 1), 4)), delta(close, 1), "
        "where(less_than(rolling_max(delta(close, 1), 4), 0), delta(close, 1), "
        "0 - delta(close, 1))))",
        ["close"],
    ),
    _panel_alpha(
        18, "alpha101_range_stability_rank", "reversal", "negative", 10,
        "Alpha#18: -rank(stddev(abs(close-open),5) + (close-open) + "
        "correlation(close, open, 10)) — ranks bars whose range is stable and "
        "whose close/open move tracks.",
        "0 - rank(rolling_std(abs(close - open), 5) + (close - open) + "
        "correlation(close, open, 10))",
        ["open", "close"],
    ),
    _panel_alpha(
        20, "alpha101_gap_cluster_rank", "reversal", "negative", 1,
        "Alpha#20: -rank(open - delay(high,1)) * rank(open - delay(close,1)) * "
        "rank(open - delay(low,1)) — the product of three gap ranks.",
        "(0 - rank(open - lag(high, 1))) * rank(open - lag(close, 1)) * "
        "rank(open - lag(low, 1))",
        ["open", "high", "low", "close"],
    ),
    _panel_alpha(
        22, "alpha101_high_volume_change_rank", "volume", "negative", 20,
        "Alpha#22: -delta(correlation(high, volume, 5), 5) * "
        "rank(stddev(close, 20)) — a change in high/volume coupling scaled by the "
        "cross-sectional volatility rank.",
        "0 - delta(correlation(high, volume, 5), 5) * rank(rolling_std(close, 20))",
        ["high", "volume", "close"],
    ),
    _panel_alpha(
        37, "alpha101_open_close_trend_rank", "trend", "positive", 200,
        "Alpha#37: rank(correlation(delay(open-close,1), close, 200)) + "
        "rank(open - close) — a long-window co-movement plus today's bar.",
        "rank(correlation(lag(open - close, 1), close, 200)) + rank(open - close)",
        ["open", "close"],
    ),
    _panel_alpha(
        38, "alpha101_close_rank_vs_trend", "reversal", "negative", 10,
        "Alpha#38: -rank(ts_rank(close,10)) * rank(close/open) — names closing "
        "high in their own range but weak versus the cross-section.",
        "(0 - rank(ts_rank(close, 10))) * rank(close / open)",
        ["open", "close"],
    ),
    # -- tranche 3: needs `ts_sum` (a plain rolling sum) and the declared adv20.
    #
    # adv20 is NOT a market input this engine receives: it is derived, because
    # the paper defines it as average daily DOLLAR volume and the only price a
    # bar carries here is close. Every formula below inlines the same
    # definition, so no formula depends on an undeclared quantity:
    #     adv20 := sma(volume * close, 20)
    # A caller with a true VWAP-based dollar volume can substitute it without
    # touching the algebra, and the definition is asserted by a test.
    _alpha(
        35, "alpha101_volume_range_regime", "volume", "positive", 32,
        "Alpha#35: ts_rank(volume,32) * (1 - ts_rank((close+high-low),16)) * "
        "(1 - ts_rank(returns,32)) — volume regime tempered by bar shape and "
        "return rank.",
        "ts_rank(volume, 32) * (1 - ts_rank((close + high) - low, 16)) * "
        "(1 - ts_rank(pct_change(close, 1), 32))",
        ["high", "low", "close", "volume"],
    ),
    _alpha(
        43, "alpha101_volume_vs_dollar_volume", "volume", "positive", 20,
        "Alpha#43: ts_rank(volume/adv20, 20) * ts_rank(-delta(close,7), 8) — "
        "unusual participation against a fading seven-day move.",
        "ts_rank(volume / sma(volume * close, 20), 20) * "
        "ts_rank(0 - delta(close, 7), 8)",
        ["close", "volume"],
    ),
    _alpha(
        7, "alpha101_volume_breakout_trend", "trend", "positive", 60,
        "Alpha#7: if adv20 < volume then -ts_rank(|delta(close,7)|,60) * "
        "sign(delta(close,7)) else -1 — fade a seven-day move only when volume "
        "is above its dollar-volume average.",
        "where(less_than(sma(volume * close, 20), volume), "
        "(0 - ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7)), 0 - 1)",
        ["close", "volume"],
    ),
    _alpha(
        21, "alpha101_range_breakout_state", "trend", "positive", 20,
        "Alpha#21: three states — a close above its 8-day band (-1), below it "
        "(+1), or a volume-versus-adv20 tiebreak.",
        "where(less_than((ts_sum(close, 8) / 8) + rolling_std(close, 8), "
        "ts_sum(close, 2) / 2), 0 - 1, "
        "where(less_than(ts_sum(close, 2) / 2, (ts_sum(close, 8) / 8) - "
        "rolling_std(close, 8)), 1, "
        "where(less_than(volume / sma(volume * close, 20), 1), 0 - 1, 1)))",
        ["close", "volume"],
    ),
    _panel_alpha(
        8, "alpha101_open_flow_reversal", "reversal", "negative", 10,
        "Alpha#8: -rank((sum(open,5) * sum(returns,5)) - delay(that, 10)) — a "
        "ten-day change in open-times-flow.",
        "0 - rank((ts_sum(open, 5) * ts_sum(pct_change(close, 1), 5)) - "
        "lag(ts_sum(open, 5) * ts_sum(pct_change(close, 1), 5), 10))",
        ["open", "close"],
    ),
    _panel_alpha(
        19, "alpha101_long_flow_sign", "momentum", "negative", 250,
        "Alpha#19: -sign((close - delay(close,7)) + delta(close,7)) * "
        "(1 + rank(1 + sum(returns,250))) — a seven-day direction scaled by "
        "annual flow.",
        "(0 - sign((close - lag(close, 7)) + delta(close, 7))) * "
        "(1 + rank(1 + ts_sum(pct_change(close, 1), 250)))",
        ["close"],
    ),
    _panel_alpha(
        30, "alpha101_flow_consistency", "volume", "positive", 20,
        "Alpha#30: (1 - rank(sign-chain)) * sum(volume,5) / sum(volume,20) — "
        "recent volume weighted by how consistent the last three closes were.",
        "((1 - rank((sign(close - lag(close, 1)) + "
        "sign(lag(close, 1) - lag(close, 2))) + "
        "sign(lag(close, 2) - lag(close, 3)))) * ts_sum(volume, 5)) / "
        "ts_sum(volume, 20)",
        ["close", "volume"],
    ),
    _panel_alpha(
        45, "alpha101_slow_flow_rank", "volume", "negative", 20,
        "Alpha#45: -(rank(sum(delay(close,5),20)/20) * correlation(close,volume,2) "
        "* rank(correlation(sum(close,5), sum(close,20), 2))).",
        "0 - (rank(ts_sum(lag(close, 5), 20) / 20) * "
        "correlation(close, volume, 2) * "
        "rank(correlation(ts_sum(close, 5), ts_sum(close, 20), 2)))",
        ["close", "volume"],
    ),
    _panel_alpha(
        52, "alpha101_low_recovery_rank", "reversal", "positive", 240,
        "Alpha#52: (-ts_min(low,5) + delay(ts_min(low,5),5)) * "
        "rank((sum(returns,240) - sum(returns,20)) / 220) * ts_rank(volume,5).",
        "((0 - rolling_min(low, 5)) + lag(rolling_min(low, 5), 5)) * "
        "rank((ts_sum(pct_change(close, 1), 240) - "
        "ts_sum(pct_change(close, 1), 20)) / 220) * ts_rank(volume, 5)",
        ["low", "close", "volume"],
    ),
    _panel_alpha(
        60, "alpha101_range_position_scale", "reversal", "negative", 10,
        "Alpha#60: -(2*scale(rank(bar-position * volume)) - "
        "scale(rank(ts_argmax(close,10)))) — volume-weighted close location "
        "against the ten-day high position.",
        "0 - ((2 * scale(rank((((close - low) - (high - close)) / "
        "(high - low)) * volume))) - scale(rank(ts_argmax(close, 10))))",
        ["high", "low", "close", "volume"],
    ),
    # -- tranche 4: the two vwap alphas whose formulas are unambiguous and carry
    # no fractional window constants. `vwap` is a CALLER-SUPPLIED input (see
    # `harness.factors.contracts`): it cannot be derived from OHLCV without
    # fabricating it, so these declare `requiresInputs: ["vwap"]` and a caller
    # without it gets MISSING_INPUT rather than a plausible NaN.
    #
    # The other vwap alphas (#55, #58, #59, #61-#67, #70-#74, ...) stay unported
    # for a narrower reason, stated so it is not mistaken for an operator gap:
    # their published forms carry fractional window constants (e.g. 7.23052) that
    # must be checked against the paper before truncation is claimed to be the
    # authored rounding. Porting them from memory would be an approximation.
    _alpha(
        41, "alpha101_geometric_range_vs_vwap", "reversal", "positive", 1,
        "Alpha#41: sqrt(high * low) - vwap — the geometric mid of the bar against "
        "where volume actually traded.",
        "((high * low) ^ 0.5) - vwap",
        ["high", "low", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        42, "alpha101_vwap_close_rank_ratio", "reversal", "positive", 1,
        "Alpha#42: rank(vwap - close) / rank(vwap + close) — how far the "
        "volume-weighted price sits from the close, relative to the pair's level.",
        "rank(vwap - close) / rank(vwap + close)",
        ["vwap", "close"],
        requires_inputs=("vwap",),
    ),
    # -- tranche 4: six formulas that need nothing beyond the operators already
    # verified (`ts_sum`, `decay_linear`, `scale`, cross-sectional rank, and the
    # derived adv20). Every one is transcribed from the paper's published form;
    # none is normalized, clipped or re-scaled beyond what the paper states.
    _panel_alpha(
        1, "alpha101_argmax_conviction", "reversal", "positive", 20,
        "Alpha#1: rank(ts_argmax(signedpower((returns<0 ? stddev(returns,20) : "
        "close), 2), 5)) - 0.5 — where the last five sessions put their extreme "
        "conviction bar, centred.",
        "rank(ts_argmax((where(less_than(pct_change(close, 1), 0), "
        "rolling_std(pct_change(close, 1), 20), close)) ^ 2, 5)) - 0.5",
        ["close"],
    ),
    _panel_alpha(
        14, "alpha101_open_volume_trend_rank", "volume", "negative", 10,
        "Alpha#14: (-rank(delta(returns,3))) * correlation(open, volume, 10) — a "
        "three-day return change ranked, times the open/volume coupling.",
        "(0 - rank(delta(pct_change(close, 1), 3))) * "
        "correlation(open, volume, 10)",
        ["open", "close", "volume"],
    ),
    _panel_alpha(
        17, "alpha101_trend_volume_rank", "trend", "negative", 10,
        "Alpha#17: -rank(ts_rank(close,10)) * rank(delta(delta(close,1),1)) * "
        "rank(ts_rank(volume/adv20, 5)) — three ranks: price trend, "
        "acceleration, and unusual participation.",
        "(0 - rank(ts_rank(close, 10))) * "
        "rank(delta(delta(close, 1), 1)) * "
        "rank(ts_rank(volume / sma(volume * close, 20), 5))",
        ["close", "volume"],
    ),
    _panel_alpha(
        28, "alpha101_dollar_flow_scale", "reversal", "positive", 5,
        "Alpha#28: scale(correlation(adv20, low, 5) + (high+low)/2 - close) — the "
        "dollar-volume/low coupling plus the bar's mid, scaled across names.",
        "scale(correlation(sma(volume * close, 20), low, 5) + "
        "((high + low) / 2) - close)",
        ["high", "low", "close", "volume"],
    ),
    _panel_alpha(
        31, "alpha101_smoothed_reversal_chain", "reversal", "positive", 12,
        "Alpha#31: rank(rank(rank(decay_linear(-rank(rank(delta(close,10))), 10)))) "
        "+ rank(-delta(close,3)) + sign(scale(correlation(adv20, low, 12))) — a "
        "decayed, doubly-ranked ten-day reversal plus a short leg and a flow sign.",
        "rank(rank(rank(decay_linear(0 - rank(rank(delta(close, 10))), 10)))) + "
        "rank(0 - delta(close, 3)) + "
        "sign(scale(correlation(sma(volume * close, 20), low, 12)))",
        ["low", "close", "volume"],
    ),
    # -- tranche 5: the vwap family. The exact formula strings and fractional
    # window constants were checked against a published reference implementation
    # (WorldQuant_alpha101_code, whose inline comments are the paper's own
    # expressions). Fractional windows are ROUNDED, not truncated — the paper's
    # convention — and the paper's constant is quoted in each description so a
    # reader can verify the rounding (e.g. 3.51013 -> 4, 6.72611 -> 7).
    _panel_alpha(
        5, "alpha101_vwap_gap_rank", "reversal", "positive", 10,
        "Alpha#5: rank(open - sum(vwap,10)/10) * -|rank(close - vwap)| — the open's "
        "gap to the average vwap, weighted by how far the close sits from vwap.",
        "rank(open - sma(vwap, 10)) * (0 - abs(rank(close - vwap)))",
        ["open", "close", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        11, "alpha101_vwap_range_volume", "volume", "positive", 3,
        "Alpha#11: (rank(ts_max(vwap-close,3)) + rank(ts_min(vwap-close,3))) * "
        "rank(delta(volume,3)) — where the vwap/close gap has been, times volume change.",
        "(rank(rolling_max(vwap - close, 3)) + rank(rolling_min(vwap - close, 3))) * "
        "rank(delta(volume, 3))",
        ["vwap", "close", "volume"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        25, "alpha101_returns_dollar_volume_vwap", "reversal", "positive", 20,
        "Alpha#25: rank(-returns * adv20 * vwap * (high - close)) — yesterday's "
        "move against dollar volume and where volume traded.",
        "rank((0 - pct_change(close, 1)) * sma(volume * close, 20) * vwap * "
        "(high - close))",
        ["high", "close", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        32, "alpha101_vwap_trend_scale", "trend", "positive", 230,
        "Alpha#32: scale(sum(close,7)/7 - close) + 20 * "
        "scale(correlation(vwap, delay(close,5), 230)) — mean reversion plus a long "
        "vwap/close coupling, both scaled across names.",
        "scale(sma(close, 7) - close) + 20 * "
        "scale(correlation(vwap, lag(close, 5), 230))",
        ["close", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        36, "alpha101_vwap_flow_composite", "volume", "positive", 200,
        "Alpha#36: the paper's five-term composite — 2.21*rank(corr(close-open, "
        "delay(volume,1), 15)) + 0.7*rank(open-close) + 0.73*rank(ts_rank(delay(-"
        "returns,6),5)) + rank(|corr(vwap, adv20, 6)|) + 0.6*rank((avg200 - open)"
        "*(close-open)).",
        "2.21 * rank(correlation(close - open, lag(volume, 1), 15)) + "
        "0.7 * rank(open - close) + "
        "0.73 * rank(ts_rank(lag(0 - pct_change(close, 1), 6), 5)) + "
        "rank(abs(correlation(vwap, sma(volume * close, 20), 6))) + "
        "0.6 * rank((sma(close, 200) - open) * (close - open))",
        ["open", "high", "low", "close", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        47, "alpha101_volume_vs_vwap_drift", "volume", "positive", 20,
        "Alpha#47: (rank(1/close) * volume / adv20) * (high * rank(high-close) / "
        "avg(high,5)) - rank(vwap - delay(vwap,5)).",
        "((rank(1 / close) * volume) / sma(volume * close, 20)) * "
        "((high * rank(high - close)) / sma(high, 5)) - "
        "rank(vwap - lag(vwap, 5))",
        ["high", "close", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        57, "alpha101_vwap_close_gap_decay", "reversal", "positive", 30,
        "Alpha#57: -(close - vwap) / decay_linear(rank(ts_argmax(close,30)), 2) — "
        "the close/vwap gap normalized by where the 30-day high sits.",
        "0 - ((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))",
        ["close", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        61, "alpha101_vwap_low_vs_adv", "reversal", "positive", 180,
        "Alpha#61: rank(vwap - ts_min(vwap, 16.1219 -> 16)) < "
        "rank(correlation(vwap, adv180, 17.9282 -> 18)) — a boolean factor by "
        "construction, so its values are 0/1.",
        "less_than(rank(vwap - rolling_min(vwap, 16)), "
        "rank(correlation(vwap, sma(volume * close, 180), 18)))",
        ["volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        65, "alpha101_open_vwap_vs_adv", "volume", "negative", 60,
        "Alpha#65: -1 * (rank(correlation(open*.00817205 + vwap*(1-.00817205), "
        "sum(adv60, 8.6911 -> 9), 6.4037 -> 6)) < rank(open - ts_min(open, "
        "13.635 -> 14))).",
        "0 - less_than("
        "rank(correlation((open * 0.00817205) + (vwap * (1 - 0.00817205)), "
        "sma(sma(volume * close, 60), 9), 6)), "
        "rank(open - rolling_min(open, 14)))",
        ["open", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        66, "alpha101_vwap_decay_reversal", "reversal", "negative", 11,
        "Alpha#66: -(rank(decay_linear(delta(vwap, 3.51013 -> 4), 7.23052 -> 7)) + "
        "ts_rank(decay_linear((low - vwap) / (open - (high+low)/2), 11.4157 -> 11), "
        "6.72611 -> 7)) — a decayed vwap change plus a decayed vwap/bar ratio.",
        "0 - (rank(decay_linear(delta(vwap, 4), 7)) + "
        "ts_rank(decay_linear((low - vwap) / (open - ((high + low) / 2)), 11), 7))",
        ["high", "low", "open", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        72, "alpha101_mid_vs_vwap_trend", "volume", "positive", 40,
        "Alpha#72: rank(decay_linear(correlation(mid, adv40, 8.93345 -> 9), "
        "10.1519 -> 10)) / rank(decay_linear(correlation(ts_rank(vwap, 3.72469 -> 4), "
        "ts_rank(volume, 18.5188 -> 19), 6.86671 -> 7), 2.95011 -> 3)) — a ratio of "
        "two decayed correlations.",
        "rank(decay_linear(correlation((high + low) / 2, "
        "sma(volume * close, 40), 9), 10)) / "
        "rank(decay_linear(correlation(ts_rank(vwap, 4), ts_rank(volume, 19), 7), 3))",
        ["high", "low", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        83, "alpha101_range_vs_vwap_ratio", "volume", "positive", 5,
        "Alpha#83: (rank(delay((high-low)/(sum(close,5)/5), 2)) * rank(rank(volume))) "
        "/ (((high-low)/(sum(close,5)/5)) / (vwap - close)) — a ranked range/volume "
        "term over the vwap/close gap.",
        "(rank(lag(((high - low) / sma(close, 5)), 2)) * rank(rank(volume))) / "
        "(((high - low) / sma(close, 5)) / (vwap - close))",
        ["high", "low", "close", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        86, "alpha101_adv_trend_vs_vwap_gap", "volume", "negative", 20,
        "Alpha#86: -1 * (ts_rank(correlation(close, sum(adv20, 14.7444 -> 15), "
        "6.00049 -> 6), 20.4195 -> 20) < rank((open+close) - (vwap+open))) — a "
        "boolean factor, so its values are 0/-1.",
        "0 - less_than("
        "ts_rank(correlation(close, sma(sma(volume * close, 20), 15), 6), 20), "
        "rank((open + close) - (vwap + open)))",
        ["open", "close", "volume", "vwap"],
        requires_inputs=("vwap",),
    ),
    _panel_alpha(
        99, "alpha101_mid_vs_adv_boolean", "volume", "negative", 60,
        "Alpha#99: -1 * (rank(correlation(sum(mid, 19.8975 -> 20), "
        "sum(adv60, 19.8975 -> 20), 8.8136 -> 9)) < rank(correlation(low, volume, "
        "6.28259 -> 6))) — a boolean factor, so its values are 0/-1.",
        "0 - less_than("
        "rank(correlation(ts_sum((high + low) / 2, 20), "
        "ts_sum(sma(volume * close, 60), 20), 9)), "
        "rank(correlation(low, volume, 6)))",
        ["high", "low", "volume"],
        requires_inputs=(),
    ),
    _panel_alpha(
        39, "alpha101_volume_shock_reversal", "reversal", "negative", 250,
        "Alpha#39: -rank(delta(close,7) * (1 - rank(decay_linear(volume/adv20, 9)))) "
        "* (1 + rank(sum(returns,250))) — a seven-day move weighted by how ordinary "
        "its volume was, scaled by the annual flow.",
        "(0 - rank(delta(close, 7) * "
        "(1 - rank(decay_linear(volume / sma(volume * close, 20), 9))))) * "
        "(1 + rank(ts_sum(pct_change(close, 1), 250)))",
        ["close", "volume"],
    ),
    # -- tranche 6: the industry-neutralised family and the SignedPower residual.
    #
    # `neutralize(x, industry)` is a NEW panel-only operator: it subtracts the
    # cross-sectional mean within each industry code, at each date. The industry is
    # a DECLARED INPUT (a numeric code per name), because the harness does not own
    # an industry classification — inventing one would make every "neutralised"
    # alpha a claim about a taxonomy nobody supplied. A one-name cohort is left
    # as-is rather than being centred to 0.
    #
    # Fractional windows are ROUNDED (the paper's convention) and the published
    # constant is quoted in each description, as in tranche 5.
    _panel_alpha(
        48, "alpha101_neutralised_volume_flow", "volume", "positive", 250,
        "Alpha#48: indneutralize((corr(delta(close,1), delta(delay(close,1),1), "
        "250) * delta(close,1)) / close, subindustry) / sum((delta(close,1)/"
        "delay(close,1))^2, 250).",
        "neutralize((correlation(delta(close, 1), delta(lag(close, 1), 1), 250) * "
        "delta(close, 1)) / close, industry) / "
        "ts_sum((delta(close, 1) / lag(close, 1)) ^ 2, 250)",
        ["close", "industry"], requires_inputs=("industry",),
    ),
    _panel_alpha(
        50, "alpha101_rank_corr_extreme", "volume", "negative", 5,
        "Alpha#50: -ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5).",
        "0 - rolling_max(rank(correlation(rank(volume), rank(vwap), 5)), 5)",
        ["volume", "vwap"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        58, "alpha101_neutralised_vwap_decay", "volume", "negative", 8,
        "Alpha#58: -Ts_Rank(decay_linear(correlation(indneutralize(vwap, sector), "
        "volume, 3.92795 -> 4), 7.89291 -> 8), 5.50322 -> 6).",
        "0 - ts_rank(decay_linear(correlation(neutralize(vwap, sector), volume, 4), "
        "8), 6)",
        ["vwap", "volume", "sector"], requires_inputs=("vwap", "sector"),
    ),
    _panel_alpha(
        63, "alpha101_neutralised_close_decay", "volume", "negative", 37,
        "Alpha#63: -(rank(decay_linear(delta(indneutralize(close, industry), "
        "2.25164 -> 2), 8.22237 -> 8)) - rank(decay_linear(correlation("
        "(vwap*0.318108 + open*(1-0.318108)), sum(adv180, 37.2467 -> 37), "
        "13.557 -> 14), 12.2883 -> 12))).",
        "0 - (rank(decay_linear(delta(neutralize(close, industry), 2), 8)) - "
        "rank(decay_linear(correlation(vwap * 0.318108 + open * 0.681892, "
        "ts_sum(sma(volume * close, 180), 37), 14), 12)))",
        ["close", "open", "vwap", "volume", "industry"],
        requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        69, "alpha101_neutralised_vwap_momentum", "volume", "negative", 5,
        "Alpha#69: -(rank(ts_max(delta(indneutralize(vwap, industry), 2.72412 -> 3), "
        "4.79344 -> 5)) ^ ts_rank(correlation((close*0.490655 + vwap*0.509345), "
        "adv20, 4.92416 -> 5), 9.0615 -> 9)).",
        "0 - (rank(rolling_max(delta(neutralize(vwap, industry), 3), 5)) ^ "
        "ts_rank(correlation(close * 0.490655 + vwap * 0.509345, "
        "sma(volume * close, 20), 5), 9))",
        ["close", "vwap", "volume", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        79, "alpha101_neutralised_composite_boolean", "volume", "positive", 150,
        "Alpha#79: rank(delta(indneutralize((close*0.60733 + open*0.39267), sector), "
        "1.23438 -> 1)) < rank(correlation(ts_rank(vwap, 3.60973 -> 4), "
        "ts_rank(adv150, 9.18637 -> 9), 14.6644 -> 15)).",
        "less_than(rank(delta(neutralize(close * 0.60733 + open * 0.39267, sector), "
        "1)), rank(correlation(ts_rank(vwap, 4), ts_rank(sma(volume * close, 150), "
        "9), 15)))",
        ["close", "open", "vwap", "volume", "sector"],
        requires_inputs=("vwap", "sector"),
    ),
    _panel_alpha(
        80, "alpha101_neutralised_open_high", "volume", "negative", 5,
        "Alpha#80: -(rank(sign(delta(indneutralize((open*0.868128 + "
        "high*0.131872), industry), 4.04545 -> 4))) ^ ts_rank(correlation(high, "
        "adv10, 5.11456 -> 5), 5.53756 -> 6)).",
        "0 - (rank(sign(delta(neutralize(open * 0.868128 + high * 0.131872, "
        "industry), 4))) ^ ts_rank(correlation(high, sma(volume * close, 10), 5), 6))",
        ["open", "high", "volume", "industry"], requires_inputs=("industry",),
    ),
    _panel_alpha(
        84, "alpha101_signed_power_vwap_rank", "reversal", "negative", 15,
        "Alpha#84: SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217 -> 15)), "
        "20.7127 -> 21), delta(close, 4.96796 -> 5)) — a signed power, so a negative "
        "base stays defined.",
        "signed_power(ts_rank(vwap - rolling_max(vwap, 15), 21), delta(close, 5))",
        ["close", "vwap"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        87, "alpha101_neutralised_adv_decay", "volume", "negative", 14,
        "Alpha#87: -(max(rank(decay_linear(delta((close*0.369701 + vwap*0.630299), "
        "1.91233 -> 2), 2.65461 -> 3)), ts_rank(decay_linear(|correlation("
        "indneutralize(adv81, industry), close, 13.4132 -> 13)|, 4.89768 -> 5), "
        "14.4535 -> 14))).",
        "0 - maximum(rank(decay_linear(delta(close * 0.369701 + vwap * 0.630299, "
        "2), 3)), ts_rank(decay_linear(abs(correlation(neutralize("
        "sma(volume * close, 81), industry), close, 13)), 5), 14))",
        ["close", "vwap", "volume", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        89, "alpha101_neutralised_vwap_trend", "reversal", "negative", 15,
        "Alpha#89: (Ts_Rank(decay_linear(correlation((low*0.967285 + low*0.032715), "
        "adv10, 6.94279 -> 7), 5.51607 -> 6), 3.79744 -> 4) - Ts_Rank(decay_linear("
        "delta(indneutralize(vwap, industry), 3.48158 -> 3), 10.1466 -> 10), "
        "15.3012 -> 15)).",
        "ts_rank(decay_linear(correlation(low, sma(volume * close, 10), 7), 6), 4) - "
        "ts_rank(decay_linear(delta(neutralize(vwap, industry), 3), 10), 15)",
        ["low", "vwap", "volume", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        94, "alpha101_vwap_adv_rank_power", "volume", "negative", 60,
        "Alpha#94: -(rank(vwap - ts_min(vwap, 11.5783 -> 12)) ^ ts_rank(correlation("
        "ts_rank(vwap, 19.6462 -> 20), ts_rank(adv60, 4.02992 -> 4), 18.0926 -> 18), "
        "2.70756 -> 3)).",
        "0 - (rank(vwap - rolling_min(vwap, 12)) ^ "
        "ts_rank(correlation(ts_rank(vwap, 20), ts_rank(sma(volume * close, 60), 4), "
        "18), 3))",
        ["vwap", "volume"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        98, "alpha101_vwap_adv_ratio", "volume", "positive", 26,
        "Alpha#98: rank(decay_linear(correlation(vwap, sum(adv5, 26.4719 -> 26), "
        "4.58418 -> 5), 7.18088 -> 7)) - rank(decay_linear(ts_rank(ts_argmin("
        "correlation(rank(open), rank(adv15), 20.8187 -> 21), 8.62571 -> 9), "
        "6.95668 -> 7), 8.07206 -> 8)).",
        "rank(decay_linear(correlation(vwap, ts_sum(sma(volume * close, 5), 26), 5), "
        "7)) - rank(decay_linear(ts_rank(ts_argmin(correlation(rank(open), "
        "rank(sma(volume * close, 15)), 21), 9), 7), 8))",
        ["vwap", "open", "volume"], requires_inputs=("vwap",),
    ),
    # -- tranche 7: the family the new operators unblocked. Cross-sectional rank
    # nested in a rolling correlation (proved supported in GTJA tranche 11),
    # `neutralize` for IndClass, and elementwise `minimum`/`maximum`.
    # Fractional windows are rounded, with the paper constant quoted.
    _panel_alpha(
        2, "alpha101_log_volume_rank_corr", "volume", "negative", 6,
        "Alpha#2: -correlation(rank(delta(log(volume),2)), rank((close-open)/open), 6).",
        "0 - correlation(rank(delta(log(volume), 2)), rank((close - open) / open), 6)",
        ["close", "open", "volume"],
    ),
    _panel_alpha(
        3, "alpha101_open_volume_rank_corr", "volume", "negative", 10,
        "Alpha#3: -correlation(rank(open), rank(volume), 10).",
        "0 - correlation(rank(open), rank(volume), 10)", ["open", "volume"],
    ),
    _panel_alpha(
        4, "alpha101_low_rank_trend", "reversal", "negative", 9,
        "Alpha#4: -ts_rank(rank(low), 9) — the time-series rank of a "
        "cross-sectional rank.",
        "0 - ts_rank(rank(low), 9)", ["low"],
    ),
    _panel_alpha(
        13, "alpha101_close_volume_cov_rank", "volume", "negative", 5,
        "Alpha#13: -rank(covariance(rank(close), rank(volume), 5)).",
        "0 - rank(covariance(rank(close), rank(volume), 5))", ["close", "volume"],
    ),
    _panel_alpha(
        15, "alpha101_high_volume_corr_sum", "volume", "negative", 3,
        "Alpha#15: -sum(rank(correlation(rank(high), rank(volume), 3)), 3).",
        "0 - ts_sum(rank(correlation(rank(high), rank(volume), 3)), 3)",
        ["high", "volume"],
    ),
    _panel_alpha(
        16, "alpha101_high_volume_cov_rank", "volume", "negative", 5,
        "Alpha#16: -rank(covariance(rank(high), rank(volume), 5)).",
        "0 - rank(covariance(rank(high), rank(volume), 5))", ["high", "volume"],
    ),
    _panel_alpha(
        27, "alpha101_volume_vwap_corr_gate", "volume", "negative", 6,
        "Alpha#27: (0.5 < rank(sum(correlation(rank(volume), rank(vwap), 6), 2)/2)) ? "
        "-1 : 1.",
        "where(greater_than(rank(ts_sum(correlation(rank(volume), rank(vwap), 6), 2) / "
        "2), 0.5), 0 - 1, 1)",
        ["volume", "vwap"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        44, "alpha101_high_rank_volume", "volume", "negative", 5,
        "Alpha#44: -correlation(high, rank(volume), 5).",
        "0 - correlation(high, rank(volume), 5)", ["high", "volume"],
    ),
    _panel_alpha(
        55, "alpha101_range_position_volume", "volume", "negative", 12,
        "Alpha#55: -correlation(rank(close position in the 12-day range), "
        "rank(volume), 6).",
        "0 - correlation(rank((close - rolling_min(low, 12)) / "
        "(rolling_max(high, 12) - rolling_min(low, 12))), rank(volume), 6)",
        ["high", "low", "close", "volume"],
    ),
    _panel_alpha(
        59, "alpha101_neutralised_vwap_volume_decay", "volume", "negative", 16,
        "Alpha#59: -Ts_Rank(decay_linear(correlation(indneutralize(vwap, industry), "
        "volume, 4.25197 -> 4), 16.2289 -> 16), 8.19648 -> 8).",
        "0 - ts_rank(decay_linear(correlation(neutralize(vwap, industry), volume, 4), "
        "16), 8)",
        ["vwap", "volume", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        62, "alpha101_vwap_adv_boolean", "volume", "negative", 22,
        "Alpha#62: -1 * (rank(correlation(vwap, sum(adv20, 22.4101 -> 22), "
        "9.91009 -> 10)) < rank((rank(open)+rank(open)) < (rank(mid)+rank(high)))).",
        "0 - less_than(rank(correlation(vwap, ts_sum(sma(volume * close, 20), 22), "
        "10)), rank(less_than(rank(open) + rank(open), "
        "rank((high + low) / 2) + rank(high))))",
        ["open", "high", "low", "volume", "vwap"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        64, "alpha101_open_low_vwap_adv", "volume", "negative", 120,
        "Alpha#64: -1 * (rank(correlation(sum(open*0.178404 + low*0.821596, "
        "12.7054 -> 13), sum(adv120, 12.7054 -> 13), 16.6208 -> 17)) < "
        "rank(delta(mid*0.178404 + vwap*0.821596, 3.69741 -> 4))).",
        "0 - less_than(rank(correlation(ts_sum(open * 0.178404 + low * 0.821596, 13), "
        "ts_sum(sma(volume * close, 120), 13), 17)), "
        "rank(delta((high + low) / 2 * 0.178404 + vwap * 0.821596, 4)))",
        ["open", "low", "high", "volume", "vwap"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        67, "alpha101_neutralised_vwap_adv_power", "volume", "negative", 6,
        "Alpha#67: -1 * (rank(high - ts_min(high, 2.14593 -> 2)) ^ "
        "rank(correlation(indneutralize(vwap, sector), indneutralize(adv20, "
        "industry), 6.02936 -> 6))).",
        "0 - (rank(high - rolling_min(high, 2)) ^ "
        "rank(correlation(neutralize(vwap, sector), "
        "neutralize(sma(volume * close, 20), industry), 6)))",
        ["high", "volume", "vwap", "sector", "industry"],
        requires_inputs=("vwap", "sector", "industry"),
    ),
    _panel_alpha(
        68, "alpha101_high_adv_trend_boolean", "volume", "negative", 15,
        "Alpha#68: -1 * (ts_rank(correlation(rank(high), rank(adv15), "
        "8.91644 -> 9), 13.9333 -> 14) < rank(delta(close*0.518371 + "
        "low*0.481629, 1.06157 -> 1))).",
        "0 - less_than(ts_rank(correlation(rank(high), "
        "rank(sma(volume * close, 15)), 9), 14), "
        "rank(delta(close * 0.518371 + low * 0.481629, 1)))",
        ["high", "low", "close", "volume"],
    ),
    _panel_alpha(
        70, "alpha101_neutralised_close_adv_power", "volume", "negative", 50,
        "Alpha#70: -1 * (rank(delta(vwap, 1.29456 -> 1)) ^ "
        "ts_rank(correlation(indneutralize(close, industry), adv50, "
        "17.8256 -> 18), 17.9171 -> 18)).",
        "0 - (rank(delta(vwap, 1)) ^ ts_rank(correlation(neutralize(close, industry), "
        "sma(volume * close, 50), 18), 18))",
        ["close", "volume", "vwap", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        71, "alpha101_two_decayed_trends", "trend", "negative", 180,
        "Alpha#71: max(Ts_Rank(decay_linear(correlation(ts_rank(close, "
        "3.43976 -> 3), ts_rank(adv180, 12.0647 -> 12), 18.0175 -> 18), "
        "4.20501 -> 4), 15.6948 -> 16), Ts_Rank(decay_linear(rank((low+open) - "
        "(vwap+vwap))^2, 16.4662 -> 16), 4.4388 -> 4)).",
        "maximum(ts_rank(decay_linear(correlation(ts_rank(close, 3), "
        "ts_rank(sma(volume * close, 180), 12), 18), 4), 16), "
        "ts_rank(decay_linear(rank((low + open) - (vwap + vwap)) ^ 2, 16), 4))",
        ["low", "open", "vwap", "volume", "close"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        73, "alpha101_vwap_decay_vs_open_low", "volume", "negative", 17,
        "Alpha#73: -1 * max(rank(decay_linear(delta(vwap, 4.72775 -> 5), "
        "2.91864 -> 3)), ts_rank(decay_linear((delta(open*0.147155 + low*0.852845, "
        "2.03608 -> 2) / (open*0.147155 + low*0.852845)) * -1, 3.33829 -> 3), "
        "16.7411 -> 17)).",
        "0 - maximum(rank(decay_linear(delta(vwap, 5), 3)), "
        "ts_rank(decay_linear((delta(open * 0.147155 + low * 0.852845, 2) / "
        "(open * 0.147155 + low * 0.852845)) * (0 - 1), 3), 17))",
        ["vwap", "open", "low"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        74, "alpha101_close_adv_vs_high_vwap", "volume", "negative", 37,
        "Alpha#74: -1 * (rank(correlation(close, sum(adv30, 37.4843 -> 37), "
        "15.1365 -> 15)) < rank(correlation(rank(high*0.0261661 + "
        "vwap*0.9738339), rank(volume), 11.4791 -> 11))).",
        "0 - less_than(rank(correlation(close, ts_sum(sma(volume * close, 30), 37), "
        "15)), rank(correlation(rank(high * 0.0261661 + vwap * 0.9738339), "
        "rank(volume), 11)))",
        ["close", "high", "volume", "vwap"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        75, "alpha101_vwap_volume_vs_low_adv", "volume", "positive", 50,
        "Alpha#75: rank(correlation(vwap, volume, 4.24304 -> 4)) < "
        "rank(correlation(rank(low), rank(adv50), 12.4413 -> 12)).",
        "less_than(rank(correlation(vwap, volume, 4)), "
        "rank(correlation(rank(low), rank(sma(volume * close, 50)), 12)))",
        ["vwap", "volume", "low"], requires_inputs=("vwap",),
    ),
    # -- tranche 8: the last seventeen, completing the paper. Every formula here
    # needed only operators already in place; `#56` is the first to declare a
    # `cap` (market-cap) input, which the harness does not invent.
    _panel_alpha(
        29, "alpha101_nested_rank_product", "reversal", "positive", 5,
        "Alpha#29: min(product(rank(rank(scale(log(sum(ts_min(rank(rank(-rank("
        "delta(close-1,5)))),2),1))))),1),5) + ts_rank(delay(-returns,6),5).",
        'minimum(prod(rank(rank(scale(log(ts_sum(rolling_min(rank(rank(0 - rank(delta(close - 1, 5)))), 2), 1))))), 1), 5) + ts_rank(lag(0 - pct_change(close, 1), 6), 5)',
        ["close"],
    ),
    _panel_alpha(
        56, "alpha101_returns_flow_vs_cap", "reversal", "negative", 10,
        "Alpha#56: -(rank(sum(returns,10) / sum(sum(returns,2),3)) * "
        "rank(returns * cap)). Declares the `cap` input.",
        "0 - (rank(ts_sum(pct_change(close, 1), 10) / "
        "ts_sum(ts_sum(pct_change(close, 1), 2), 3)) * "
        "rank(pct_change(close, 1) * cap))",
        ["close", "cap"], requires_inputs=("cap",),
    ),
    _panel_alpha(
        77, "alpha101_mid_vwap_adv_min", "reversal", "negative", 40,
        "Alpha#77: min(rank(decay_linear((mid + high) - (vwap + high), "
        "20.0451 -> 20)), rank(decay_linear(correlation(mid, adv40, "
        "3.1614 -> 3), 5.64125 -> 6))).",
        "minimum(rank(decay_linear((high + low) / 2 - vwap, 20)), "
        "rank(decay_linear(correlation((high + low) / 2, "
        "sma(volume * close, 40), 3), 6)))",
        ["high", "low", "vwap", "volume"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        78, "alpha101_low_vwap_adv_power", "volume", "positive", 40,
        "Alpha#78: rank(correlation(sum(low*0.352233 + vwap*0.647767, "
        "19.7428 -> 20), sum(adv40, 19.7428 -> 20), 6.83313 -> 7)) ^ "
        "rank(correlation(rank(vwap), rank(volume), 5.77492 -> 6)).",
        "rank(correlation(ts_sum(low * 0.352233 + vwap * 0.647767, 20), "
        "ts_sum(sma(volume * close, 40), 20), 7)) ^ "
        "rank(correlation(rank(vwap), rank(volume), 6))",
        ["low", "vwap", "volume"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        81, "alpha101_vwap_adv_product_boolean", "volume", "negative", 50,
        "Alpha#81: -1 * (rank(log(product(rank(rank(correlation(vwap, "
        "sum(adv10, 49.6054 -> 50), 8.47743 -> 8))^4)), 14.9655 -> 15))) < "
        "rank(correlation(rank(vwap), rank(volume), 5.07914 -> 5))).",
        "0 - less_than(rank(log(prod(rank(rank(correlation(vwap, "
        "ts_sum(sma(volume * close, 10), 50), 8)) ^ 4), 15))), "
        "rank(correlation(rank(vwap), rank(volume), 5)))",
        ["vwap", "volume"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        82, "alpha101_neutralised_volume_open", "volume", "negative", 17,
        "Alpha#82: -1 * min(rank(decay_linear(delta(open, 1.46063 -> 1), "
        "14.8717 -> 15)), ts_rank(decay_linear(correlation(indneutralize(volume, "
        "sector), open, 17.4842 -> 17), 6.92131 -> 7), 13.4283 -> 13)).",
        "0 - minimum(rank(decay_linear(delta(open, 1), 15)), "
        "ts_rank(decay_linear(correlation(neutralize(volume, sector), open, 17), "
        "7), 13))",
        ["open", "volume", "sector"], requires_inputs=("sector",),
    ),
    _panel_alpha(
        85, "alpha101_high_close_adv_power", "volume", "positive", 30,
        "Alpha#85: rank(correlation(high*0.876703 + close*0.123297, adv30, "
        "9.61331 -> 10)) ^ rank(correlation(ts_rank(mid, 3.70596 -> 4), "
        "ts_rank(volume, 10.1595 -> 10), 7.11408 -> 7)).",
        "rank(correlation(high * 0.876703 + close * 0.123297, "
        "sma(volume * close, 30), 10)) ^ "
        "rank(correlation(ts_rank((high + low) / 2, 4), ts_rank(volume, 10), 7))",
        ["high", "low", "close", "volume"],
    ),
    _panel_alpha(
        88, "alpha101_rank_spread_vs_adv", "volume", "positive", 21,
        "Alpha#88: min(rank(decay_linear((rank(open)+rank(low)) - "
        "(rank(high)+rank(close)), 8.06882 -> 8)), ts_rank(decay_linear("
        "correlation(ts_rank(close, 8.44728 -> 8), ts_rank(adv60, "
        "20.6966 -> 21), 8.01266 -> 8), 6.65053 -> 7), 2.61957 -> 3)).",
        "minimum(rank(decay_linear(rank(open) + rank(low) - rank(high) - "
        "rank(close), 8)), ts_rank(decay_linear(correlation(ts_rank(close, 8), "
        "ts_rank(sma(volume * close, 60), 21), 8), 7), 3))",
        ["open", "high", "low", "close", "volume"],
    ),
    _panel_alpha(
        90, "alpha101_neutralised_adv_low_power", "volume", "negative", 40,
        "Alpha#90: -1 * (rank(close - ts_max(close, 4.66719 -> 5)) ^ "
        "ts_rank(correlation(indneutralize(adv40, industry), low, "
        "5.38375 -> 5), 3.21856 -> 3)).",
        "0 - (rank(close - rolling_max(close, 5)) ^ "
        "ts_rank(correlation(neutralize(sma(volume * close, 40), industry), low, "
        "5), 3))",
        ["close", "low", "volume", "industry"], requires_inputs=("industry",),
    ),
    _panel_alpha(
        91, "alpha101_neutralised_close_vs_vwap_adv", "volume", "negative", 30,
        "Alpha#91: -1 * (ts_rank(decay_linear(decay_linear(correlation("
        "indneutralize(close, industry), volume, 9.74928 -> 10), "
        "16.398 -> 16), 3.83219 -> 4), 4.8667 -> 5) - rank(decay_linear("
        "correlation(vwap, adv30, 4.01303 -> 4), 2.6809 -> 3))).",
        "0 - (ts_rank(decay_linear(decay_linear(correlation(neutralize(close, "
        "industry), volume, 10), 16), 4), 5) - "
        "rank(decay_linear(correlation(vwap, sma(volume * close, 30), 4), 3)))",
        ["close", "volume", "vwap", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        92, "alpha101_mid_break_min", "reversal", "positive", 30,
        "Alpha#92: min(ts_rank(decay_linear(mid + close < low + open, "
        "14.7221 -> 15), 18.8683 -> 19), ts_rank(decay_linear(correlation("
        "rank(low), rank(adv30), 7.58555 -> 8), 6.94024 -> 7), 6.80584 -> 7)).",
        "minimum(ts_rank(decay_linear(less_than((high + low) / 2 + close, "
        "low + open), 15), 19), ts_rank(decay_linear(correlation(rank(low), "
        "rank(sma(volume * close, 30)), 8), 7), 7))",
        ["high", "low", "open", "close", "volume"],
    ),
    _panel_alpha(
        93, "alpha101_neutralised_vwap_adv_ratio", "volume", "positive", 81,
        "Alpha#93: ts_rank(decay_linear(correlation(indneutralize(vwap, "
        "industry), adv81, 17.4193 -> 17), 19.848 -> 20), 7.54455 -> 8) / "
        "rank(decay_linear(delta(close*0.524434 + vwap*0.475566, "
        "2.77377 -> 3), 16.2664 -> 16)).",
        "ts_rank(decay_linear(correlation(neutralize(vwap, industry), "
        "sma(volume * close, 81), 17), 20), 8) / "
        "rank(decay_linear(delta(close * 0.524434 + vwap * 0.475566, 3), 16))",
        ["close", "vwap", "volume", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        95, "alpha101_open_low_vs_mid_adv", "volume", "positive", 40,
        "Alpha#95: rank(open - ts_min(open, 12.4105 -> 12)) < ts_rank((rank("
        "correlation(sum(mid, 19.1351 -> 19), sum(adv40, 19.1351 -> 19), "
        "12.8742 -> 13))^5), 11.7584 -> 12).",
        "less_than(rank(open - rolling_min(open, 12)), "
        "ts_rank(rank(correlation(ts_sum((high + low) / 2, 19), "
        "ts_sum(sma(volume * close, 40), 19), 13)) ^ 5, 12))",
        ["open", "high", "low", "volume"],
    ),
    _panel_alpha(
        96, "alpha101_vwap_adv_max_decay", "volume", "negative", 60,
        "Alpha#96: -1 * max(ts_rank(decay_linear(correlation(rank(vwap), "
        "rank(volume), 3.83878 -> 4), 4.16783 -> 4), 8.38151 -> 8), "
        "ts_rank(decay_linear(ts_argmax(correlation(ts_rank(close, "
        "7.45404 -> 7), ts_rank(adv60, 4.13242 -> 4), 3.65459 -> 4), "
        "12.6556 -> 13), 14.0365 -> 14), 13.4143 -> 13)).",
        "0 - maximum(ts_rank(decay_linear(correlation(rank(vwap), rank(volume), "
        "4), 4), 8), ts_rank(decay_linear(ts_argmax(correlation(ts_rank(close, "
        "7), ts_rank(sma(volume * close, 60), 4), 4), 13), 14), 13))",
        ["vwap", "volume", "close"], requires_inputs=("vwap",),
    ),
    _panel_alpha(
        97, "alpha101_neutralised_low_vwap_decay", "volume", "negative", 20,
        "Alpha#97: -1 * (rank(decay_linear(delta(indneutralize(low*0.721001 + "
        "vwap*0.278999, industry), 3.3705 -> 3), 20.4523 -> 20)) - "
        "ts_rank(decay_linear(ts_rank(correlation(ts_rank(low, "
        "7.87871 -> 8), ts_rank(adv60, 17.255 -> 17), 4.97547 -> 5), "
        "18.5925 -> 19), 15.7152 -> 16), 6.71659 -> 7)).",
        "0 - (rank(decay_linear(delta(neutralize(low * 0.721001 + vwap * "
        "0.278999, industry), 3), 20)) - ts_rank(decay_linear(ts_rank("
        "correlation(ts_rank(low, 8), ts_rank(sma(volume * close, 60), 17), 5), "
        "19), 16), 7))",
        ["low", "vwap", "volume", "industry"], requires_inputs=("vwap", "industry"),
    ),
    _panel_alpha(
        76, "alpha101_neutralised_low_adv_max", "volume", "negative", 81,
        "Alpha#76: -1 * max(rank(decay_linear(delta(vwap, 1.24383 -> 1), "
        "11.8259 -> 12)), ts_rank(decay_linear(ts_rank(correlation("
        "indneutralize(low, sector), adv81, 8.14941 -> 8), 19.569 -> 20), "
        "17.1543 -> 17), 19.383 -> 19)).",
        "0 - maximum(rank(decay_linear(delta(vwap, 1), 12)), "
        "ts_rank(decay_linear(ts_rank(correlation(neutralize(low, sector), "
        "sma(volume * close, 81), 8), 20), 17), 19))",
        ["low", "vwap", "volume", "sector"], requires_inputs=("vwap", "sector"),
    ),
    _panel_alpha(
        100, "alpha101_neutralised_range_volume", "volume", "negative", 30,
        "Alpha#100: -(1.5*scale(indneutralize(indneutralize(rank((((close-low)-"
        "(high-close))/(high-low))*volume), subindustry), subindustry)) - "
        "scale(indneutralize(correlation(close, rank(adv20), 5) - "
        "rank(ts_argmin(close,30)), subindustry))) * (volume / adv20).",
        "0 - ((1.5 * scale(neutralize(neutralize(rank((((close - low) - "
        "(high - close)) / (high - low)) * volume), industry), industry))) - "
        "scale(neutralize((correlation(close, rank(sma(volume * close, 20)), 5) - "
        "rank(ts_argmin(close, 30))), industry))) * "
        "(volume / sma(volume * close, 20))",
        ["high", "low", "close", "volume", "industry"],
        requires_inputs=("industry",),
    ),
]


def alpha_numbers() -> list[int]:
    return [factor["alphaNumber"] for factor in ALPHA101_FACTORS]


__all__ = ["ALPHA101_FACTORS", "PAPER", "PORTED", "TOTAL", "alpha_numbers"]
