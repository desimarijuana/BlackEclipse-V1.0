"""Qlib Alpha158 — the price/volume subset that is EXACTLY expressible here.

Qlib's `Alpha158` is a *feature set*, not 158 independent signals: 9 kbar
features plus rolling operators at horizons 5/10/20/30/60. This module ports the
family whose published definitions map one-to-one onto this DSL:

  * 6 kbar features (KMID, KLEN, KMID2, KUP, KLOW, KSFT)
  * ROC, MA, STD, MAX, MIN, QTLU, QTLD, RANK, RSV, IMAX, CORR, CNTP, CNTN, VMA,
    VSTD at each of 5/10/20/60 sessions

Not ported, and not approximated:

  * `BETA`, `RSQR`, `RESI` need a regression (slope / R² / residual) this DSL
    cannot express;
  * `IMXD` needs `ts_argmin`, which is not implemented;
  * `SUMP`/`SUMN`/`SUMD`, `CORD`, `WVMA` and the pairwise `CORR` variants need
    definitions that differ between Qlib revisions — a guess would ship a
    different factor under the same name;
  * the `VWAP`/`OPEN0` price-normalisation features need a `vwap` input the data
    surface does not supply.

Every record says which definition it is, so a reader can check it against Qlib.
"""

from __future__ import annotations

from typing import Any

ZOO = "qlib158"
SOURCE = "Qlib Alpha158 feature definitions — re-implemented on harness.stats.formula"
REFERENCE = "Microsoft Qlib, Alpha158 handler (qlib.contrib.data.handler.Alpha158)"
HORIZONS: tuple[int, ...] = (5, 10, 20, 30, 60)

#: Families ported and how many features that yields: 13 base (9 kbar + OPEN0/
#: HIGH0/LOW0 + VWAP0) plus 29 per horizon. That is qlib's published 158 exactly
#: (13 + 29 * 5), which is how the arithmetic was confirmed against the source.
PORTED = 13 + 29 * len(HORIZONS)
TOTAL = 158


def _record(
    name: str,
    family: str,
    direction: str,
    lookback: int,
    description: str,
    expression: str,
    inputs: list[str],
    reference: str,
) -> dict[str, Any]:
    return {
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
        "reference": reference,
    }


KBAR: list[dict[str, Any]] = [
    _record("qlib_kmid", "candlestick", "positive", 1,
            "KMID: (close - open) / open — the body as a share of the open.",
            "(close - open) / open", ["open", "close"], f"{REFERENCE}: KMID"),
    _record("qlib_klen", "candlestick", "negative", 1,
            "KLEN: (high - low) / open — the bar's range as a share of the open.",
            "(high - low) / open", ["open", "high", "low"], f"{REFERENCE}: KLEN"),
    _record("qlib_kmid2", "candlestick", "positive", 1,
            "KMID2: (close - open) / (high - low) — body relative to the range.",
            "(close - open) / (high - low)", ["open", "high", "low", "close"],
            f"{REFERENCE}: KMID2"),
    _record("qlib_kup", "candlestick", "negative", 1,
            "KUP: (high - max(open, close)) / open — the upper shadow.",
            "(high - where(greater_than(open, close), open, close)) / open",
            ["open", "high", "close"], f"{REFERENCE}: KUP"),
    _record("qlib_klow", "candlestick", "positive", 1,
            "KLOW: (min(open, close) - low) / open — the lower shadow.",
            "(where(less_than(open, close), open, close) - low) / open",
            ["open", "low", "close"], f"{REFERENCE}: KLOW"),
    # KUP2 / KLOW2 / KSFT2 are the range-normalised twins of KUP / KLOW / KSFT.
    # They were the three "unnamed" features until qlib's own `Alpha158DL.
    # get_feature_config` was fetched and read: its kbar block has NINE fields
    # (KMID, KLEN, KMID2, KUP, KUP2, KLOW, KLOW2, KSFT, KSFT2), not six.
    _record("qlib_kup2", "candlestick", "negative", 1,
            "KUP2: (high - max(open, close)) / (high - low + 1e-12) — the upper "
            "shadow as a share of the bar range.",
            "(high - where(greater_than(open, close), open, close)) / "
            "(high - low + 0.000000000001)",
            ["open", "high", "low", "close"], f"{REFERENCE}: KUP2"),
    _record("qlib_klow2", "candlestick", "positive", 1,
            "KLOW2: (min(open, close) - low) / (high - low + 1e-12) — the lower "
            "shadow as a share of the bar range.",
            "(where(less_than(open, close), open, close) - low) / "
            "(high - low + 0.000000000001)",
            ["open", "high", "low", "close"], f"{REFERENCE}: KLOW2"),
    _record("qlib_ksft2", "candlestick", "positive", 1,
            "KSFT2: (2*close - high - low) / (high - low + 1e-12) — where the close "
            "sits, as a share of the bar range.",
            "(2 * close - high - low) / (high - low + 0.000000000001)",
            ["high", "low", "close"], f"{REFERENCE}: KSFT2"),
    _record("qlib_ksft", "candlestick", "positive", 1,
            "KSFT: (2*close - high - low) / open — where the close sits.",
            "(2 * close - high - low) / open", ["open", "high", "low", "close"],
            f"{REFERENCE}: KSFT"),
    # OPEN0/HIGH0/LOW0 are qlib's price-level normalisations: each price relative
    # to the close, which needs no vwap.
    _record("qlib_open0", "price_level", "negative", 1,
            "OPEN0: open / close - 1 — the open's gap to the close.",
            "open / close - 1", ["open", "close"], f"{REFERENCE}: OPEN0"),
    _record("qlib_high0", "price_level", "positive", 1,
            "HIGH0: high / close - 1 — how far the high ran above the close.",
            "high / close - 1", ["high", "close"], f"{REFERENCE}: HIGH0"),
    _record("qlib_low0", "price_level", "negative", 1,
            "LOW0: low / close - 1 — how far the low ran below the close.",
            "low / close - 1", ["low", "close"], f"{REFERENCE}: LOW0"),
    # VWAP0 needs a caller-supplied `vwap`: a typical price is not a
    # volume-weighted average, so this declares the requirement instead of
    # fabricating one (see `harness.factors.contracts`).
    {
        **_record("qlib_vwap0", "price_level", "negative", 1,
                  "VWAP0: vwap / close - 1 — where volume actually traded, "
                  "relative to the close.",
                  "vwap / close - 1", ["vwap", "close"], f"{REFERENCE}: VWAP0"),
        "requiresInputs": ["vwap"],
    },
]


def _family(feature: str, d: int, template: str, description: str,
            inputs: list[str], direction: str, lookback: int) -> dict[str, Any]:
    return _record(
        f"qlib_{feature.lower()}_{d}",
        "qlib158",
        direction,
        lookback,
        description.format(d=d),
        template.format(d=d),
        inputs,
        f"{REFERENCE}: {feature}{{{d}}}",
    )


ROLLING: list[dict[str, Any]] = []
for d in HORIZONS:
    ROLLING.extend([
        _family("ROC", d, "close / lag(close, {d}) - 1",
                "ROC{{{d}}}: rate of change over {{d}} sessions.",
                ["close"], "positive", d + 1),
        _family("MA", d, "rolling_mean(close, {d}) / close",
                "MA{{{d}}}: mean close over {{d}} sessions, relative to today.",
                ["close"], "negative", d),
        _family("STD", d, "rolling_std(close, {d}) / close",
                "STD{{{d}}}: close volatility over {{d}} sessions.",
                ["close"], "negative", d),
        _family("MAX", d, "rolling_max(high, {d}) / close",
                "MAX{{{d}}}: highest high over {{d}} sessions, relative to close.",
                ["high", "close"], "positive", d),
        _family("MIN", d, "rolling_min(low, {d}) / close",
                "MIN{{{d}}}: lowest low over {{d}} sessions, relative to close.",
                ["low", "close"], "negative", d),
        _family("QTLU", d, "rolling_quantile(close, {d}, 0.8) / close",
                "QTLU{{{d}}}: 80th-percentile close over {{d}} sessions.",
                ["close"], "positive", d),
        _family("QTLD", d, "rolling_quantile(close, {d}, 0.2) / close",
                "QTLD{{{d}}}: 20th-percentile close over {{d}} sessions.",
                ["close"], "negative", d),
        _family("RANK", d, "ts_rank(close, {d})",
                "RANK{{{d}}}: rank of today's close inside its {{d}}-session window.",
                ["close"], "positive", d),
        _family("RSV", d,
                "(close - rolling_min(low, {d})) / (rolling_max(high, {d}) - rolling_min(low, {d}))",
                "RSV{{{d}}}: close position inside the {{d}}-session high-low range.",
                ["high", "low", "close"], "positive", d),
        _family("IMAX", d, "ts_argmax(high, {d}) / {d}",
                "IMAX{{{d}}}: 0-based position of the {{d}}-session high, scaled by {{d}}.",
                ["high"], "negative", d),
        _family("IMIN", d, "ts_argmin(low, {d}) / {d}",
                "IMIN{{{d}}}: 0-based position of the {{d}}-session low, scaled by {{d}}.",
                ["low"], "positive", d),
        _family("IMXD", d, "(ts_argmax(high, {d}) - ts_argmin(low, {d})) / {d}",
                "IMXD{{{d}}}: distance between the {{d}}-session high and low positions.",
                ["high", "low"], "positive", d),
        _family("BETA", d, "slope(close, {d}) / close",
                "BETA{{{d}}}: OLS slope of close against time over {{d}} sessions, "
                "relative to close.",
                ["close"], "positive", d),
        _family("RSQR", d, "r2(close, {d})",
                "RSQR{{{d}}}: R-squared of the {{d}}-session close trend.",
                ["close"], "positive", d),
        _family("RESI", d, "resi(close, {d}) / close",
                "RESI{{{d}}}: residual of today's close from its {{d}}-session "
                "trend, relative to close.",
                ["close"], "negative", d),
        _family("CORR", d, "correlation(close, log(volume + 1), {d})",
                "CORR{{{d}}}: correlation of close with log volume over {{d}} sessions.",
                ["close", "volume"], "negative", d + 1),
        _family("CNTP", d, "rolling_mean(greater_than(close, lag(close, 1)), {d})",
                "CNTP{{{d}}}: share of up days in the last {{d}} sessions.",
                ["close"], "positive", d + 1),
        _family("CNTN", d, "rolling_mean(less_than(close, lag(close, 1)), {d})",
                "CNTN{{{d}}}: share of down days in the last {{d}} sessions.",
                ["close"], "negative", d + 1),
        _family("VMA", d, "rolling_mean(volume, {d}) / (volume + 1)",
                "VMA{{{d}}}: mean volume over {{d}} sessions, relative to today.",
                ["volume"], "negative", d),
        _family("VSTD", d, "rolling_std(volume, {d}) / (volume + 1)",
                "VSTD{{{d}}}: volume volatility over {{d}} sessions.",
                ["volume"], "negative", d),
        # -- the "flow" families, transcribed from qlib's Alpha158DL:
        # Ref/Sum/Mean/Greater/Std map to lag/ts_sum/rolling_mean/greater_than/
        # rolling_std one-to-one, and the stated +1 guards are kept verbatim.
        _family("CORD", d,
                "correlation(close / lag(close, 1), "
                "log(volume / lag(volume, 1) + 1), {d})",
                "CORD{{{d}}}: correlation of returns with log volume change.",
                ["close", "volume"], "positive", d + 1),
        _family("CNTD", d,
                "rolling_mean(less_than(close, lag(close, 1)), {d}) - "
                "rolling_mean(greater_than(close, lag(close, 1)), {d})",
                "CNTD{{{d}}}: down-day share minus up-day share.",
                ["close"], "positive", d + 1),
        _family("SUMP", d,
                "ts_sum(where(greater_than(close - lag(close, 1), 0), "
                "close - lag(close, 1), 0), {d}) / "
                "(ts_sum(abs(close - lag(close, 1)), {d}) + 1)",
                "SUMP{{{d}}}: up-move share of total absolute movement.",
                ["close"], "positive", d + 1),
        _family("SUMN", d,
                "ts_sum(where(greater_than(lag(close, 1) - close, 0), "
                "lag(close, 1) - close, 0), {d}) / "
                "(ts_sum(abs(close - lag(close, 1)), {d}) + 1)",
                "SUMN{{{d}}}: down-move share of total absolute movement.",
                ["close"], "negative", d + 1),
        _family("SUMD", d,
                "(ts_sum(where(greater_than(close - lag(close, 1), 0), "
                "close - lag(close, 1), 0), {d}) - "
                "ts_sum(where(greater_than(lag(close, 1) - close, 0), "
                "lag(close, 1) - close, 0), {d})) / "
                "(ts_sum(abs(close - lag(close, 1)), {d}) + 1)",
                "SUMD{{{d}}}: net up-minus-down movement share (SUMP - SUMN).",
                ["close"], "positive", d + 1),
        _family("WVMA", d,
                "rolling_std(abs(close / lag(close, 1) - 1) * volume, {d}) / "
                "(rolling_mean(abs(close / lag(close, 1) - 1) * volume, {d}) + 1)",
                "WVMA{{{d}}}: volatility of volume-weighted absolute returns.",
                ["close", "volume"], "negative", d),
        # VSUM*: the same up/down/net share, but over DOLLAR volume
        # (`$volume * $close`), so a large move on thin volume counts less.
        # `Greater` keeps the value in qlib, hence the `where` (see SUMP's note).
        _family("VSUMP", d,
                "ts_sum(where(greater_than(volume * close - lag(volume * close, 1), 0), "
                "volume * close - lag(volume * close, 1), 0), {d}) / "
                "(ts_sum(abs(volume * close - lag(volume * close, 1)), {d}) + 1)",
                "VSUMP{{{d}}}: up-move share of absolute dollar-volume change.",
                ["close", "volume"], "positive", d + 1),
        _family("VSUMN", d,
                "ts_sum(where(greater_than(lag(volume * close, 1) - volume * close, 0), "
                "lag(volume * close, 1) - volume * close, 0), {d}) / "
                "(ts_sum(abs(volume * close - lag(volume * close, 1)), {d}) + 1)",
                "VSUMN{{{d}}}: down-move share of absolute dollar-volume change.",
                ["close", "volume"], "negative", d + 1),
        _family("VSUMD", d,
                "(ts_sum(where(greater_than(volume * close - lag(volume * close, 1), 0), "
                "volume * close - lag(volume * close, 1), 0), {d}) - "
                "ts_sum(where(greater_than(lag(volume * close, 1) - volume * close, 0), "
                "lag(volume * close, 1) - volume * close, 0), {d})) / "
                "(ts_sum(abs(volume * close - lag(volume * close, 1)), {d}) + 1)",
                "VSUMD{{{d}}}: net dollar-volume movement share (VSUMP - VSUMN).",
                ["close", "volume"], "positive", d + 1),
    ])

QLIB158_FACTORS: list[dict[str, Any]] = [*KBAR, *ROLLING]


def qlib_positions_port() -> dict[str, Any]:
    """What is ported vs total, as data a tool or doc can report."""
    return {"zoo": ZOO, "ported": PORTED, "total": TOTAL, "reference": REFERENCE}


__all__ = ["HORIZONS", "KBAR", "PORTED", "QLIB158_FACTORS", "ROLLING", "TOTAL", "qlib_positions_port"]
