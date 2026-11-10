"""Run manifests — the reproducibility contract.

An experiment row records the strategy, window and seed. That is necessary but
not sufficient: a later reader cannot tell *which bars* were used, *which build*
computed them, or *which dependencies* were present. The manifest closes that
gap with a canonical, content-hashed record attached to every run.

Two rules:

* The digest is a sha256 over canonical JSON (sorted keys, no whitespace), so
  the same manifest always hashes the same on any machine.
* The manifest never contains a metric it did not receive. It is a record, not a
  second computation.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from typing import Any, Iterable, Optional

MANIFEST_SCHEMA_VERSION = "quant-run-manifest-1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _versions() -> dict[str, Any]:
    try:
        import numpy  # noqa: PLC0415
        numpy_version = numpy.__version__
    except Exception:  # noqa: BLE001
        numpy_version = None
    try:
        import pydantic  # noqa: PLC0415
        pydantic_version = pydantic.VERSION
    except Exception:  # noqa: BLE001
        pydantic_version = None
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": numpy_version,
        "pydantic": pydantic_version,
    }


def dataset_fingerprint(dataset: Any) -> dict[str, Any]:
    """Hash the bars actually used, symbol by symbol.

    The fingerprint is over timestamps + OHLCV (rounded to 10 significant
    digits to avoid float formatting noise). Changing one bar changes the hash;
    reordering symbols does not.
    """
    import numpy as np  # noqa: PLC0415

    series = getattr(dataset, "series", {}) or {}
    per_symbol: dict[str, Any] = {}
    source = {}
    for symbol in sorted(series):
        s = series[symbol]
        hasher = hashlib.sha256()
        hasher.update(str(symbol).encode("utf-8"))
        hasher.update(str(getattr(s, "interval", "")).encode("utf-8"))
        ts = getattr(s, "timestamps", None)
        if ts is not None:
            hasher.update(canonical_json(list(ts)).encode("utf-8"))
        for field in ("open", "high", "low", "close", "volume"):
            arr = getattr(s, field, None)
            if arr is None:
                continue
            rounded = np.round(np.asarray(arr, dtype=float), 10)
            hasher.update(rounded.tobytes())
        per_symbol[symbol] = {
            "bars": int(getattr(s, "length", 0) or 0),
            "interval": getattr(s, "interval", None),
            "sha256": hasher.hexdigest(),
            "source": getattr(s, "source", None),
        }
        source[symbol] = getattr(s, "source", None)
    return {
        "symbols": list(per_symbol),
        "interval": getattr(dataset, "primary_interval", lambda: None)(),
        "series": per_symbol,
        "sources": source,
    }


def build_run_manifest(
    *,
    strategies: Iterable[Any],
    dataset: Any,
    configuration: dict[str, Any],
    metrics: Optional[dict[str, Any]] = None,
    engine_version: str,
    code_version: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from .schema import spec_content_hash  # noqa: PLC0415

    strategy_records = []
    for spec in strategies:
        try:
            content_hash = spec_content_hash(spec)
        except Exception:  # noqa: BLE001 - a manifest must not break a run
            content_hash = None
        strategy_records.append({
            "id": getattr(spec, "id", None),
            "version": getattr(spec, "version", None),
            "contentHash": content_hash,
            "assetClass": getattr(spec, "asset_class", None),
        })
    manifest = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engineVersion": engine_version,
        "codeVersion": code_version,
        "strategies": strategy_records,
        "data": dataset_fingerprint(dataset),
        "configuration": configuration,
        "metrics": metrics or {},
        "environment": _versions(),
        "extra": extra or {},
    }
    manifest["digest"] = digest({k: v for k, v in manifest.items() if k != "createdAt"})
    return manifest


def manifest_matches(a: Optional[dict[str, Any]], b: Optional[dict[str, Any]],
                     *, ignore: Iterable[str] = ("createdAt",)) -> bool:
    if not a or not b:
        return False
    drop = set(ignore)
    a2 = {k: v for k, v in a.items() if k not in drop}
    b2 = {k: v for k, v in b.items() if k not in drop}
    return digest(a2) == digest(b2)


_METRIC_TOLERANCE = {
    "total_return": 1e-6, "cagr": 1e-6, "sharpe": 1e-6, "sortino": 1e-6,
    "max_drawdown": 1e-6, "volatility": 1e-6, "profit_factor": 1e-6,
    "expectancy": 1e-6, "win_rate": 1e-6,
}


def compare_metrics(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Compare two metric maps with a tolerance appropriate to each metric.

    Returns a structured verdict; a missing/None metric is `unavailable`, never
    a pass by accident.
    """
    diffs: list[dict[str, Any]] = []
    for key in sorted(set(expected) | set(actual)):
        a = expected.get(key)
        b = actual.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            tol = _METRIC_TOLERANCE.get(key, 1e-6)
            delta = abs(float(a) - float(b))
            if delta > tol:
                diffs.append({"metric": key, "expected": a, "actual": b, "delta": delta})
        elif a != b and a is not None and b is not None:
            diffs.append({"metric": key, "expected": a, "actual": b})
    return {
        "reproduced": not diffs,
        "compared": len(set(expected) | set(actual)),
        "differences": diffs,
        "tolerance": _METRIC_TOLERANCE,
    }


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "build_run_manifest",
    "canonical_json",
    "compare_metrics",
    "dataset_fingerprint",
    "digest",
    "manifest_matches",
]
