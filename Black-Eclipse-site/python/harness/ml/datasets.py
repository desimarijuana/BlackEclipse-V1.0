"""Dataset construction for the ML Research Lab.

One immutable dataset version = a resolved price panel + a feature matrix + a
label vector + the provenance needed to rebuild it. Data is fetched ONLY through
the shared market gateway (``stats.datasets.resolve_frame``); this module never
contacts a provider directly and never invents a missing observation.

Feature sources:
  * built-in, documented price/volume features (always available), and
  * registered Feature Registry definitions (``feature:<name>``), evaluated on
    the same per-symbol series — proving Factor Lab / Stats share one registry.

Rows are flattened ``(time-major, then symbol)`` so the temporal split engine can
treat each date's cross-section as an atomic unit.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Optional

import numpy as np

from .models import DatasetSpec, MLError
from .quality import evaluate_quality
from .targets import build_target
from ..stats.base import INVALID_INPUT, INSUFFICIENT_DATA


# ── built-in features ────────────────────────────────────────────────────────


def _returns(close: np.ndarray) -> np.ndarray:
    r = np.full(close.size, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = close[1:] / close[:-1] - 1.0
    return r


def _ret_k(close: np.ndarray, k: int) -> np.ndarray:
    out = np.full(close.size, np.nan)
    if 0 < k < close.size:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[k:] = close[k:] / close[:-k] - 1.0
    return out


def _roll_std(a: np.ndarray, k: int) -> np.ndarray:
    out = np.full(a.size, np.nan)
    for i in range(k - 1, a.size):
        window = a[i - k + 1:i + 1]
        if np.isfinite(window).sum() >= 2:
            out[i] = np.nanstd(window, ddof=1)
    return out


def _volume_z(volume: np.ndarray, k: int) -> np.ndarray:
    logv = np.where(volume > 0, np.log(volume), np.nan)
    out = np.full(volume.size, np.nan)
    for i in range(k - 1, volume.size):
        window = logv[i - k + 1:i + 1]
        m = np.nanmean(window)
        s = np.nanstd(window, ddof=1)
        if np.isfinite(s) and s > 0:
            out[i] = (logv[i] - m) / s
    return out


def _feat_close(k: int) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    return lambda close, volume: _ret_k(close, k)


def _feat_vol(k: int) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    return lambda close, volume: _roll_std(_returns(close), k)


def _feat_volume_z(k: int) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    def fn(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        if volume is None or not np.isfinite(volume).any():
            return np.full(close.size, np.nan)
        return _volume_z(volume, k)
    return fn


BUILTIN_FEATURES: dict[str, dict[str, Any]] = {
    "ret_1": {"fn": _feat_close(1), "lookback": 1, "category": "returns",
              "description": "1-period simple return"},
    "ret_5": {"fn": _feat_close(5), "lookback": 5, "category": "returns",
              "description": "5-period simple return"},
    "ret_21": {"fn": _feat_close(21), "lookback": 21, "category": "momentum",
               "description": "21-period simple return"},
    "mom_63": {"fn": _feat_close(63), "lookback": 63, "category": "momentum",
               "description": "63-period simple return"},
    "vol_21": {"fn": _feat_vol(21), "lookback": 22, "category": "volatility",
               "description": "21-period realized volatility of returns"},
    "volume_z_21": {"fn": _feat_volume_z(21), "lookback": 21, "category": "liquidity",
                    "description": "21-period z-score of log volume"},
}


def builtin_feature_catalog() -> list[dict[str, Any]]:
    return [{"name": name, "category": spec["category"], "lookback": spec["lookback"],
             "description": spec["description"], "source": "builtin"}
            for name, spec in BUILTIN_FEATURES.items()]


def _resolve_registered(name: str, registry: Any, sample: dict[str, Any]) -> Optional[np.ndarray]:
    """Evaluate a registered Feature Registry definition on one symbol's series."""
    if registry is None:
        return None
    feature = registry._store.get_feature_by_name(name) if hasattr(registry, "_store") else None
    if feature is None:
        return None
    try:
        preview = registry.preview(feature_id=feature["id"], sample=sample)
    except Exception:  # noqa: BLE001 - a broken registered feature is a data error
        return None
    values = preview.get("values")
    if values is None:
        return None
    return np.asarray([np.nan if v is None else float(v) for v in values], dtype=float)


def _feature_panel(
    name: str, close: np.ndarray, volume: np.ndarray, registry: Any, sample: dict[str, Any]
) -> np.ndarray:
    """Return a ``(T, N)`` feature panel, or raise when the feature is unknown."""
    t, n = close.shape
    if name in BUILTIN_FEATURES:
        fn = BUILTIN_FEATURES[name]["fn"]
        return np.column_stack([fn(close[:, j], volume[:, j]) for j in range(n)])
    if name.startswith("feature:"):
        reg_name = name.split(":", 1)[1]
        if registry is None:
            raise MLError(INVALID_INPUT,
                          f"feature {name!r} requires the feature registry, which is unavailable")
        panel = np.full((t, n), np.nan)
        resolved_any = False
        for j in range(n):
            col_sample = dict(sample)
            col_sample["close"] = close[:, j].tolist()
            if volume is not None:
                col_sample["volume"] = volume[:, j].tolist()
            vals = _resolve_registered(reg_name, registry, col_sample)
            if vals is not None and vals.size == t:
                panel[:, j] = vals
                resolved_any = True
        if not resolved_any:
            raise MLError(INVALID_INPUT,
                          f"registered feature {reg_name!r} was not found or produced no values", 404)
        return panel
    raise MLError(INVALID_INPUT, f"unknown feature {name!r} (not built-in and no feature: prefix)")


def _apply_missing_policy(x: np.ndarray, policy: str) -> np.ndarray:
    if policy == "fill_zero":
        return np.where(np.isfinite(x), x, 0.0)
    return x  # drop / forward_fill handled at the panel level before flattening


def _forward_fill_panel(panel: np.ndarray) -> np.ndarray:
    out = panel.copy()
    t = out.shape[0]
    for i in range(1, t):
        mask = ~np.isfinite(out[i])
        out[i, mask] = out[i - 1, mask]
    return out


def _data_hash(payload: dict[str, Any], X: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(payload, sort_keys=True, default=str).encode())
    h.update(np.ascontiguousarray(X, dtype=np.float32).tobytes())
    return h.hexdigest()


def _panel_resolve(result: dict[str, Any]) -> np.ndarray:
    return np.asarray(result["values"], dtype=float)


def build_dataset(
    gateway: Any,
    spec: DatasetSpec,
    *,
    registry: Any = None,
    forward_fill: bool = False,
) -> dict[str, Any]:
    """Resolve and assemble one dataset version. Returns ``{manifest, arrays}``.

    Raises ``MLError`` (never returns fabricated data) when the gateway cannot
    supply the requested symbols/series.
    """
    from ..stats.datasets import resolve_frame  # noqa: PLC0415

async def build_dataset(
    gateway: Any,
    spec: DatasetSpec,
    *,
    registry: Any = None,
    forward_fill: bool = False,
) -> dict[str, Any]:
    """Resolve and assemble one dataset version. Returns ``{manifest, arrays}``.

    Raises ``MLError`` (never returns fabricated data) when the gateway cannot
    supply the requested symbols/series.
    """
    from ..stats.datasets import resolve_frame  # noqa: PLC0415

    if not spec.symbols:
        raise MLError(INVALID_INPUT, "at least one symbol is required")
    if not spec.feature_names:
        raise MLError(INVALID_INPUT, "at least one feature is required")
    if spec.missing_policy not in ("drop", "forward_fill", "fill_zero"):
        raise MLError(INVALID_INPUT, f"unknown missing policy {spec.missing_policy!r}")

    close_res = await resolve_frame(gateway, spec.symbols, interval=spec.interval,
                                    start=spec.start, end=spec.end, field="close")
    symbols = close_res["symbols"]
    timestamps = [str(t) for t in close_res["timestamps"]]
    close = _panel_resolve(close_res)
    try:
        volume = _panel_resolve(await resolve_frame(
            gateway, spec.symbols, interval=spec.interval, start=spec.start,
            end=spec.end, field="volume"))
    except Exception:  # noqa: BLE001 - volume is optional
        volume = np.full_like(close, np.nan)

    t, n = close.shape
    sample = {"close": close[:, 0].tolist()}

    panels = []
    for name in spec.feature_names:
        panel = _feature_panel(name, close, volume, registry, sample)
        if forward_fill or spec.missing_policy == "forward_fill":
            panel = _forward_fill_panel(panel)
        panels.append(panel)
    feature_names = list(spec.feature_names)
    X_panel = np.stack(panels, axis=2) if panels else np.empty((t, n, 0))  # (T, N, D)

    target = build_target(close, spec.target)
    y_panel = target["values"]  # (T, N)

    # flatten time-major: row r = t_index * N + symbol_index
    X_flat = X_panel.reshape(t * n, len(feature_names))
    y_flat = y_panel.reshape(t * n)
    label_start = np.repeat(target["labelStart"], n)
    label_end = np.repeat(target["labelEnd"], n)
    row_timestamp = [timestamps[r // n] for r in range(t * n)]
    row_symbol = [symbols[r % n] for r in range(t * n)]

    if spec.missing_policy == "fill_zero":
        X_flat = _apply_missing_policy(X_flat, "fill_zero")

    quality = evaluate_quality(
        X=X_flat, y=y_flat, feature_names=feature_names, timestamps=row_timestamp,
        symbols=row_symbol, task=target["task"], min_coverage=spec.min_coverage,
    )

    spec_payload = spec.to_dict()
    data_hash = _data_hash({"spec": spec_payload, "symbols": symbols,
                            "timestamps": timestamps, "target": spec.target.to_dict()}, X_flat)

    manifest = {
        "schemaVersion": "1.0.0",
        "symbols": symbols,
        "interval": spec.interval,
        "start": spec.start,
        "end": spec.end,
        "featureNames": feature_names,
        "rows": int(t * n),
        "dates": int(t),
        "nSymbols": int(n),
        "target": {**spec.target.to_dict(),
                   "nClasses": len(target["classes"]) if target["classes"] else spec.target.n_classes,
                   "task": target["task"], "classes": target["classes"],
                   "bins": target["bins"]},
        "missingPolicy": spec.missing_policy,
        "coverage": quality["summary"].get("coverage", 0.0),
        "quality": quality,
        "dataHash": data_hash,
        "timestampRange": [timestamps[0], timestamps[-1]] if timestamps else [None, None],
        "spec": spec_payload,
    }
    arrays = {
        "X": X_flat,
        "y": y_flat,
        "labelStart": label_start,
        "labelEnd": label_end,
        "timestamps": timestamps,
        "symbols": symbols,
        "featureNames": feature_names,
        "perSymbolRows": n,
        "targetTask": target["task"],
        "targetClasses": target["classes"],
    }
    return {"manifest": manifest, "arrays": arrays}


def _resolve_panel(result: dict[str, Any]) -> dict[str, Any]:
    return result


def reconstruct_feature_names(manifest: dict[str, Any]) -> list[str]:
    return list(manifest.get("featureNames") or [])


__all__ = [
    "build_dataset",
    "builtin_feature_catalog",
    "BUILTIN_FEATURES",
    "reconstruct_feature_names",
]
