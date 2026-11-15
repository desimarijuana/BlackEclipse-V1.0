"""Managed runtime for Python strategies.

Runs a user strategy's source in an ISOLATED worker process
(`sdk_worker.py`) with:

  * a separate process (own address space / lifecycle),
  * a **scrubbed environment** — no inherited credentials, no provider keys,
    no PYTHONPATH; only the OS-essential variables survive,
  * `python -I` isolated mode (no user site, no PYTHON* env influence),
  * a wall-clock **timeout** (the process is killed on overrun),
  * an **output-size cap** (a result file over the cap is rejected),
  * POSIX CPU/address-space limits where the OS supports them (best-effort;
    Windows relies on the timeout + output cap — this is stated honestly, not
    silently assumed).

This is process isolation + resource limits + no credential inheritance. It is
NOT a container: for a hard filesystem/network boundary, the strategy should run
under the harness's configured OS sandbox (Docker) — see the capability note in
`docs/quant-engine.md`. The worker never returns live orders and never touches
broker state.

The worker's result is *rehydrated* into a typed `BacktestResult` so the rest of
the quant store/tools treat it identically to a declarative backtest.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional

from .engine import BacktestResult

_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdk_worker.py")


def docker_available() -> bool:
    return shutil.which("docker") is not None


def resolve_sandbox(prefer: str = "auto") -> str:
    """Choose the isolation backend: 'docker' (container) or 'process'.

    Docker is used when an image is configured (`HARNESS_QUANT_SDK_DOCKER_IMAGE`)
    and the CLI is present; otherwise process isolation. `prefer='process'` forces
    the worker process; `prefer='docker'` returns 'docker' only when usable.
    """
    image = os.environ.get("HARNESS_QUANT_SDK_DOCKER_IMAGE")
    if prefer == "process":
        return "process"
    if image and docker_available():
        return "docker"
    return "process"


def docker_command(image: str, workdir: str, in_name: str, out_name: str,
                   entry: str = "sdk_worker.py") -> list[str]:
    """The Docker invocation for a hardened run (pure; testable)."""
    return [
        "docker", "run", "--rm", "--network", "none", "--memory", "512m", "--cpus", "1",
        "--read-only", "--pids-limit", "256", "--tmpfs", "/tmp",
        # Drop every capability and forbid setuid/privilege gain. The image keeps
        # its default user because the bind-mounted /work directory must remain
        # writable by the host uid; without capabilities there is no root power
        # to escalate with.
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-v", f"{workdir}:/work", "-w", "/work", image,
        "python", "-I", f"/work/{entry}", f"/work/{in_name}", f"/work/{out_name}",
    ]


def _posix_limits(timeout_s: float):
    """A preexec that caps CPU time and address space (POSIX only)."""
    def _apply() -> None:  # pragma: no cover - exercised only on POSIX
        try:
            import resource

            cpu = int(timeout_s) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 2))
            gib = 1 << 30
            resource.setrlimit(resource.RLIMIT_AS, (gib, gib))
        except Exception:  # noqa: BLE001 - limits are best-effort
            pass

    return _apply

# Only OS-essential variables cross into the worker. No PYTHONPATH (the worker
# fixes sys.path itself), no secrets, no provider credentials.
_ENV_ALLOW = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT",
              "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL")


class SdkRuntimeError(Exception):
    code = "SDK_RUNTIME_ERROR"


def _worker_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_ALLOW if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _rehydrate(d: dict[str, Any]) -> BacktestResult:
    return BacktestResult(
        metadata=d.get("metadata", {}),
        configuration=d.get("configuration", {}),
        metrics=d.get("metrics", {}),
        metric_definitions=d.get("metricDefinitions", {}),
        trades=d.get("trades", []),
        orders=d.get("orders", []),
        fills=d.get("fills", []),
        positions=d.get("positions", []),
        equity_curve=d.get("equityCurve", []),
        drawdown_curve=d.get("drawdownCurve", []),
        exposure=d.get("exposure", []),
        monthly_returns=d.get("monthlyReturns", []),
        warnings=d.get("warnings", []),
        errors=d.get("errors", []),
        artifacts=d.get("artifacts", {}),
        observability=d.get("observability", {}),
        capability=d.get("capability", {}),
        status=d.get("status", "OK"),
    )


def run_strategy_source(
    source: str,
    rows: dict[str, list[dict[str, Any]]],
    *,
    symbols: Optional[list[str]] = None,
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    risk_free_rate: float = 0.0,
    random_seed: int = 42,
    params: Optional[dict[str, Any]] = None,
    class_name: Optional[str] = None,
    strategy_id: Optional[str] = None,
    timeout_s: float = 60.0,
    max_output_bytes: int = 12 * 1024 * 1024,
    extra_files: Optional[dict[str, str]] = None,
    entry: str = "strategy.py",
    sandbox: str = "auto",
) -> tuple[Optional[BacktestResult], Optional[dict[str, Any]]]:
    """Run `source` (plus optional sibling `extra_files`) over `rows`.

    Returns `(result, error)` — exactly one is set. `entry` is the module file the
    worker loads; sibling modules in `extra_files` are importable by name.
    """
    if not source.strip():
        return None, {"code": "SDK_EMPTY_SOURCE", "message": "strategy source is empty"}
    if not rows:
        return None, {"code": "SDK_NO_DATA", "message": "no market data provided"}

    with tempfile.TemporaryDirectory(prefix="be-sdk-") as tmp:
        src_path = os.path.join(tmp, entry)
        in_path = os.path.join(tmp, "input.json")
        out_path = os.path.join(tmp, "output.json")
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(source)
        for name, text in (extra_files or {}).items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        payload = {
            "sourcePath": src_path, "className": class_name,
            "symbols": symbols or sorted(rows.keys()), "interval": interval,
            "initialCapital": initial_capital, "riskFreeRate": risk_free_rate,
            "randomSeed": random_seed, "params": params or {}, "rows": rows,
            "strategyId": strategy_id,
        }
        with open(in_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        backend = resolve_sandbox(sandbox)
        if backend == "docker":
            shutil.copyfile(_WORKER, os.path.join(tmp, "sdk_worker.py"))
            cmd = docker_command(os.environ["HARNESS_QUANT_SDK_DOCKER_IMAGE"], tmp,
                                 "input.json", "output.json")
        else:
            cmd = [sys.executable, "-I", _WORKER, in_path, out_path]
        preexec = _posix_limits(timeout_s) if (backend == "process" and os.name != "nt") else None
        try:
            proc = subprocess.run(
                cmd, env=_worker_env(), cwd=tmp, timeout=timeout_s,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=preexec,
            )
        except subprocess.TimeoutExpired:
            return None, {"code": "SDK_TIMEOUT",
                          "message": f"strategy exceeded the {timeout_s:.0f}s time limit",
                          "detail": {"timeoutSeconds": timeout_s}}

        if not os.path.exists(out_path):
            stderr = (proc.stderr or b"").decode("utf-8", "replace")[-2000:]
            return None, {"code": "SDK_WORKER_CRASH",
                          "message": "the strategy worker exited without a result",
                          "detail": {"returncode": proc.returncode, "stderr": stderr}}

        if os.path.getsize(out_path) > max_output_bytes:
            return None, {"code": "SDK_OUTPUT_TOO_LARGE",
                          "message": f"result exceeded {max_output_bytes} bytes"}

        with open(out_path, "r", encoding="utf-8") as fh:
            out = json.load(fh)

    if out.get("status") != "ok":
        error = out.get("error") or {"code": "SDK_STRATEGY_ERROR", "message": "unknown error"}
        return None, error
    result = _rehydrate(out["result"])
    if result.status == "FAILED":
        first = result.errors[0] if result.errors else {}
        return None, {"code": "SDK_STRATEGY_ERROR",
                      "message": first.get("message", "strategy raised during the run"),
                      "detail": {"type": first.get("type"), "symbol": first.get("symbol")},
                      "warnings": result.warnings}
    return result, None


__all__ = ["SdkRuntimeError", "run_strategy_source"]
