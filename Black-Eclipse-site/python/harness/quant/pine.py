"""The Pine Script runtime — a Pine script, run on Eclipse's own bars.

Pine is the lingua franca of TradingView: a trader already has a Pine strategy,
and today that script can only be evaluated inside TradingView. This module
runs it **here**, against the data Eclipse already holds.

The engine is AGPL-licensed (`pinets`, by LuxAlgo), so it does not run
in-process. It is a **separate program** (`Black-Eclipse-site/pine-engine/`)
that Eclipse spawns as a child process and talks to over files: a JSON request
in, a JSON response out. Nothing but data crosses the boundary, which is the
"separate programs communicating at arm's length" pattern from the GPL FAQ — the
app stays proprietary and the runner's source is public with the app.

The rules this module keeps:

- **The engine never reaches the network.** The bars come in the request, so a
  Pine script is always evaluated against the data the caller already has.
- **A missing engine is a named refusal**, not a silent empty result.
- **A Pine runtime error is the script's error**, reported with its message
  and the bar it happened on - never swallowed.
- **The child is bounded**: a timeout, a bar cap, a source cap, and a scrubbed
  environment (the child never inherits the runtime's secrets).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .errors import QuantError


class PineError(QuantError):
    code = "PINE_ERROR"


#: The engine directory, next to the python package.
def engine_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "pine-engine"


#: Refusal codes.
PINE_ENGINE_UNAVAILABLE = "PINE_ENGINE_UNAVAILABLE"
PINE_TIMEOUT = "PINE_TIMEOUT"
PINE_RUNTIME_ERROR = "PINE_RUNTIME_ERROR"
PINE_REQUEST_INVALID = "PINE_REQUEST_INVALID"


@dataclass
class PineRunConfig:
    """The bounds of one Pine run."""

    timeout_s: float = 60.0
    max_bars: int = 20_000
    max_source_chars: int = 200_000
    max_loops: int = 500_000
    symbol: str = "UNKNOWN"
    timeframe: str = "1d"

    def validate(self) -> None:
        if self.timeout_s <= 0:
            raise PineError("timeout_s must be > 0")
        if self.max_bars < 1:
            raise PineError("max_bars must be >= 1")
        if self.max_source_chars < 1:
            raise PineError("max_source_chars must be >= 1")


@dataclass
class PineResult:
    """What one Pine run produced."""

    plots: dict[str, Any] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plots": self.plots,
            "trades": self.trades,
            "warnings": self.warnings,
            "diagnostics": self.diagnostics,
        }


def _node_executable() -> Optional[str]:
    return shutil.which("node")


def _child_env() -> dict[str, str]:
    """A scrubbed environment for the child.

    The child needs a PATH (to find node) and a temp dir. It must NOT inherit
    the runtime's API keys, tokens or database paths.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "TEMP": os.environ.get("TEMP", tempfile.gettempdir()),
        "TMP": os.environ.get("TMP", tempfile.gettempdir()),
    }
    if os.name != "nt":
        env["HOME"] = os.environ.get("HOME", tempfile.gettempdir())
    return {k: v for k, v in env.items() if v}


def _normalise_bars(bars: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Reduce a bar list to the shape the engine reads."""
    out: list[dict[str, Any]] = []
    for bar in list(bars or [])[:limit]:
        out.append({
            "time": int(bar.get("time") or bar.get("ts") or bar.get("timestamp") or 0),
            "o": float(bar.get("o") or bar.get("open") or 0.0),
            "h": float(bar.get("h") or bar.get("high") or 0.0),
            "l": float(bar.get("l") or bar.get("low") or 0.0),
            "c": float(bar.get("c") or bar.get("close") or 0.0),
            "v": float(bar.get("v") or bar.get("volume") or 0.0),
        })
    return out


class PineRunner:
    """Runs Pine scripts in the isolated engine."""

    def __init__(self, engine: Optional[Path] = None) -> None:
        self.engine = Path(engine) if engine else engine_dir()

    # ── availability ──────────────────────────────────────────────────────────

    def unavailable_reason(self) -> Optional[str]:
        """Why the engine cannot run, or None when it can."""
        if not _node_executable():
            return ("node is not on the PATH; the Pine engine is a Node program")
        runner = self.engine / "runner.mjs"
        if not runner.exists():
            return f"the Pine engine is missing at {self.engine}"
        if not (self.engine / "node_modules" / "pinets").exists():
            return (f"the Pine engine is not installed; run `npm run setup:pine` "
                    f"in {self.engine}")
        return None

    @property
    def available(self) -> bool:
        return self.unavailable_reason() is None

    # ── the run ───────────────────────────────────────────────────────────────

    def run(
        self,
        source: str,
        bars: list[dict[str, Any]],
        *,
        config: Optional[PineRunConfig] = None,
    ) -> PineResult:
        cfg = config or PineRunConfig()
        cfg.validate()

        reason = self.unavailable_reason()
        if reason:
            raise PineError(reason, detail={"code": PINE_ENGINE_UNAVAILABLE,
                                            "engine": str(self.engine)})

        text = str(source or "")
        if not text.strip():
            raise PineError("the Pine script is empty", detail={"code": PINE_REQUEST_INVALID})
        if len(text) > cfg.max_source_chars:
            raise PineError(
                f"the Pine script is {len(text)} characters; the limit is "
                f"{cfg.max_source_chars}",
                detail={"code": PINE_REQUEST_INVALID, "chars": len(text)})

        payload_bars = _normalise_bars(bars, cfg.max_bars)
        if not payload_bars:
            raise PineError("there are no bars to run the script on",
                            detail={"code": PINE_REQUEST_INVALID})

        with tempfile.TemporaryDirectory(prefix="eclipse-pine-") as work:
            request_path = Path(work) / "request.json"
            response_path = Path(work) / "response.json"
            request = {
                "source": text,
                "bars": payload_bars,
                "symbol": cfg.symbol,
                "timeframe": cfg.timeframe,
                "limit": len(payload_bars),
                "maxLoops": cfg.max_loops,
                "responsePath": str(response_path),
            }
            request_path.write_text(json.dumps(request), encoding="utf-8")

            try:
                completed = subprocess.run(  # noqa: S603 - a fixed argv, no shell
                    [_node_executable() or "node", "runner.mjs", str(request_path)],
                    cwd=str(self.engine),
                    env=_child_env(),
                    capture_output=True,
                    text=True,
                    timeout=cfg.timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise PineError(
                    f"the Pine script did not finish within {cfg.timeout_s:.0f}s",
                    detail={"code": PINE_TIMEOUT, "timeoutS": cfg.timeout_s}) from exc
            except OSError as exc:
                raise PineError(
                    f"the Pine engine could not be started: {exc}",
                    detail={"code": PINE_ENGINE_UNAVAILABLE}) from exc

            if not response_path.exists():
                stderr = (completed.stderr or "").strip()[:2_000]
                raise PineError(
                    "the Pine engine produced no response"
                    + (f": {stderr}" if stderr else ""),
                    detail={"code": PINE_ENGINE_UNAVAILABLE,
                            "exitCode": completed.returncode,
                            "stderr": stderr})

            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise PineError(
                    f"the Pine engine's response was not readable: {exc}",
                    detail={"code": PINE_RUNTIME_ERROR}) from exc

        if response.get("status") != "ok":
            raise PineError(
                str(response.get("message") or "the Pine script failed"),
                detail={"code": PINE_RUNTIME_ERROR,
                        "name": response.get("name"),
                        "stack": response.get("stack")})

        return PineResult(
            plots=response.get("plots") or {},
            trades=response.get("trades") or [],
            warnings=response.get("warnings") or [],
            diagnostics=response.get("diagnostics") or {},
        )


def plot_series(result: PineResult, name: str) -> list[Optional[float]]:
    """The values of one plot, in order (None while the indicator warms up)."""
    plot = (result.plots or {}).get(name) or {}
    points = plot.get("points") or []
    return [point.get("value") for point in points]


def plot_times(result: PineResult, name: str) -> list[Optional[int]]:
    plot = (result.plots or {}).get(name) or {}
    points = plot.get("points") or []
    return [point.get("time") for point in points]


__all__ = [
    "PINE_ENGINE_UNAVAILABLE",
    "PINE_REQUEST_INVALID",
    "PINE_RUNTIME_ERROR",
    "PINE_TIMEOUT",
    "PineError",
    "PineResult",
    "PineRunConfig",
    "PineRunner",
    "engine_dir",
    "plot_series",
    "plot_times",
]
