"""calculate_drawdown — episodes, durations, recovery, unrecovered periods."""

from __future__ import annotations

import numpy as np

from .base import (
    as_list,
    make_response,
    require_min_length,
    to_float_array,
)

DESCRIPTION = (
    "Drawdown analysis of a price/equity curve: wealth curve, running peak, "
    "drawdown series, maximum drawdown with start/trough/recovery indices, an "
    "episode table (depth, duration in observations and elapsed time, recovery "
    "duration) and identification of unrecovered drawdowns."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"},
                   "description": "Price or equity series, oldest first."},
        "timestamps": {"type": "array", "items": {"type": "string"},
                       "description": "Optional ISO timestamps aligned to values."},
        "topN": {"type": "integer", "minimum": 1, "default": 5},
    },
    "required": ["values"],
}


def _elapsed(timestamps: list | None, i: int, j: int) -> float | None:
    if not timestamps or i is None or j is None:
        return None
    try:
        from datetime import datetime  # noqa: PLC0415

        a = datetime.fromisoformat(str(timestamps[i]).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(timestamps[j]).replace("Z", "+00:00"))
        return abs((b - a).total_seconds())
    except (ValueError, TypeError):
        return None


def run(args: dict) -> dict:
    prices = to_float_array(args.get("values"), "values")
    require_min_length(prices, 2, "values")
    timestamps = args.get("timestamps")
    top_n = int(args.get("topN", 5))

    running_max = np.maximum.accumulate(prices)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = prices / running_max - 1.0
    drawdown = np.where(np.isfinite(drawdown), drawdown, 0.0)

    max_dd = float(drawdown.min())
    trough_idx = int(np.argmin(drawdown))
    peak_value = running_max[trough_idx]
    start_idx = int(np.where(prices[: trough_idx + 1] == peak_value)[0][-1])
    recovery_idx = None
    after = np.where(prices[trough_idx:] >= peak_value)[0]
    if after.size:
        recovery_idx = int(trough_idx + after[0])

    warnings: list[str] = []
    if recovery_idx is None:
        warnings.append("maximum drawdown has not recovered within the sample (unrecovered)")

    # ── episode detection (peak → trough → recovery) ─────────────────────────
    episodes: list[dict] = []
    peak_idx = 0
    in_dd = False
    ep_start = 0
    for i in range(1, prices.size):
        if prices[i] >= prices[peak_idx]:
            if in_dd:
                window = drawdown[ep_start: i + 1]
                tr = int(ep_start + np.argmin(window))
                episodes.append({
                    "startIndex": ep_start, "troughIndex": tr, "recoveryIndex": i,
                    "depth": float(drawdown[tr]), "durationObs": i - ep_start,
                    "recoveryObs": i - tr,
                    "durationSeconds": _elapsed(timestamps, ep_start, i),
                    "recovered": True,
                })
                in_dd = False
            peak_idx = i
        elif not in_dd:
            in_dd = True
            ep_start = peak_idx
    if in_dd:
        window = drawdown[ep_start:]
        tr = int(ep_start + np.argmin(window))
        episodes.append({
            "startIndex": ep_start, "troughIndex": tr, "recoveryIndex": None,
            "depth": float(drawdown[tr]), "durationObs": prices.size - 1 - ep_start,
            "recoveryObs": None, "durationSeconds": _elapsed(timestamps, ep_start, prices.size - 1),
            "recovered": False,
        })

    episodes.sort(key=lambda e: e["depth"])

    summary = {
        "maxDrawdown": max_dd,
        "maxDrawdownStartIndex": start_idx,
        "maxDrawdownTroughIndex": trough_idx,
        "maxDrawdownRecoveryIndex": recovery_idx,
        "maxDrawdownDurationObs": (recovery_idx - start_idx) if recovery_idx is not None else None,
        "maxDrawdownDurationSeconds": _elapsed(timestamps, start_idx, recovery_idx),
        "recovered": recovery_idx is not None,
        "episodeCount": len(episodes),
    }
    return make_response(
        "calculate_drawdown",
        {"topN": top_n},
        summary=summary,
        results={
            "drawdownSeries": as_list(drawdown),
            "runningPeak": as_list(running_max),
            "wealthCurve": as_list(prices / prices[0]) if prices[0] else None,
            "episodes": episodes[:top_n],
            "allEpisodeCount": len(episodes),
        },
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
