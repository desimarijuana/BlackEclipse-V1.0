"""Isolated worker process that runs ONE user Python strategy.

Invoked as `python -I sdk_worker.py <input.json> <output.json>` from
`quant/sdk_runtime.py`. It is a separate process (its own address space, its own
lifecycle) with a scrubbed environment and no inherited credentials; the parent
enforces a wall-clock timeout and an output-size cap and never trusts stdout.

Contract:
  * input JSON: sourcePath, className?, symbols, interval, initialCapital,
    riskFreeRate, randomSeed, params, rows{symbol: [OHLCV rows]};
  * output JSON: {"status":"ok","result": <BacktestResult dict>} or
    {"status":"error","error":{...}};
  * the worker imports the harness itself (sys.path is fixed here, so the parent
    need not pass PYTHONPATH and `-I` cannot break imports).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from typing import Any

# Make `harness` importable without relying on PYTHONPATH (which -I ignores).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PY_ROOT = os.path.dirname(os.path.dirname(_HERE))  # .../python
if _PY_ROOT not in sys.path:
    sys.path.insert(0, _PY_ROOT)


def _load_module(path: str) -> Any:
    # Make sibling project modules importable by name.
    source_dir = os.path.dirname(os.path.abspath(path))
    if source_dir not in sys.path:
        sys.path.insert(0, source_dir)
    spec = importlib.util.spec_from_file_location("user_strategy", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load strategy module from {path!r}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_strategy_class(module: Any, class_name: str | None) -> Any:
    from harness.quant.sdk import Strategy

    if class_name:
        cls = getattr(module, class_name, None)
        if cls is None:
            raise ValueError(f"class {class_name!r} not found in strategy module")
        return cls
    candidates = [
        obj for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy
    ]
    if not candidates:
        raise ValueError("strategy module defines no Strategy subclass")
    if len(candidates) > 1:
        raise ValueError(
            f"strategy module defines multiple Strategy subclasses "
            f"({[c.__name__ for c in candidates]}); set className")
    return candidates[0]


def run(payload: dict[str, Any]) -> dict[str, Any]:
    from harness.quant.data import build_dataset, series_from_rows
    from harness.quant.engine import BacktestConfig
    from harness.quant.sdk import run_user_strategy

    module = _load_module(payload["sourcePath"])
    cls = _find_strategy_class(module, payload.get("className"))
    user = cls()
    interval = payload.get("interval") or "1d"
    series = {
        symbol: series_from_rows(symbol, interval, rows, source="python-sdk")
        for symbol, rows in payload["rows"].items()
    }
    dataset = build_dataset(series)
    config = BacktestConfig(
        initial_capital=float(payload.get("initialCapital", 100_000.0)),
        risk_free_rate=float(payload.get("riskFreeRate", 0.0)),
        random_seed=int(payload.get("randomSeed", 42)),
    )
    result = run_user_strategy(
        user, dataset, config,
        params=payload.get("params") or {},
        symbols=payload.get("symbols"),
        strategy_id=payload.get("strategyId"),
    )
    return {"status": "ok", "result": result.to_dict(include_series=True)}


def main() -> int:
    in_path, out_path = sys.argv[1], sys.argv[2]
    with open(in_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    try:
        out = run(payload)
    except Exception as exc:  # noqa: BLE001 - report honestly, never crash silently
        out = {
            "status": "error",
            "error": {
                "code": getattr(exc, "code", "SDK_STRATEGY_ERROR"),
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc().splitlines()[-8:],
            },
        }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
