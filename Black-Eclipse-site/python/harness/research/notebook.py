"""Isolated research notebooks over immutable datasets.

Untrusted analytical Python is executed in the ONE bounded sandbox primitive
(`code.sandbox`), never in the FastAPI process. The notebook receives a
materialized, read-only copy of one dataset version as a CSV; it gets NO provider
credentials, NO vault values, NO callback token and NO proxy (see
`sandbox.build_env`), and its run is wall-clock + output + memory bounded.

This is the operator-driven counterpart to the declarative `analyze_dataset`
tool: `analyze_dataset` is safe for unattended agents; `run_notebook` is an
explicit, operator-gated request to execute code.
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

_NOTEBOOK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                              ".black-eclipse", "quant", "notebooks"))
_DEFAULT_TIMEOUT_S = 30
_MAX_CODE_CHARS = 20_000
_OUTPUT_CAP_BYTES = 256 * 1024


class NotebookError(RuntimeError):
    code = "NOTEBOOK_ERROR"


def materialize_dataset(dataset_store: Any, dataset_id: str, version: Optional[str],
                        workdir: str, symbols: Optional[list[str]] = None) -> tuple[str, int]:
    """Write the dataset version to `workdir/dataset.csv` (read-only input).
    Returns (path, row_count)."""
    artifact = dataset_store.read_artifact(dataset_id, version)
    series: dict[str, list[dict[str, Any]]] = artifact.get("series", {})
    if symbols:
        wanted = {s.upper() for s in symbols}
        series = {k: v for k, v in series.items() if k.upper() in wanted}
    path = os.path.join(workdir, "dataset.csv")
    rows = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "timestamp", "open", "high", "low", "close", "volume"])
        for symbol, bars in series.items():
            for b in bars:
                writer.writerow([symbol, b.get("timestamp"), b.get("open"), b.get("high"),
                                 b.get("low"), b.get("close"), b.get("volume")])
                rows += 1
    return path, rows


def run_notebook(code: str, *, dataset_path: Optional[str], timeout_s: int = _DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """Execute `code` in the sandbox with a read-only dataset CSV available.

    Returns a structured result. A missing sandbox is an honest refusal, never an
    unbounded fallback run.
    """
    from ..code import sandbox

    if not code or len(code) > _MAX_CODE_CHARS:
        raise NotebookError(f"code must be 1..{_MAX_CODE_CHARS} characters")
    timeout_s = max(1, min(int(timeout_s), 120))

    os.makedirs(_NOTEBOOK_ROOT, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix=f"nb_{uuid.uuid4().hex[:12]}_", dir=_NOTEBOOK_ROOT)
    script = os.path.join(workdir, "main.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(code)

    env = sandbox.build_env({"ECLIPSE_DATASET_PATH": dataset_path or "", "PYTHONDONTWRITEBYTECODE": "1"})
    spec = sandbox.RunSpec(
        argv=[sys.executable, "-I", script],
        cwd=Path(workdir),
        env=env,
        timeout_s=timeout_s,
        output_cap_bytes=_OUTPUT_CAP_BYTES,
        network=False,
        memory_mb=1024,
    )
    try:
        result = sandbox.run(spec)
    except sandbox.SandboxUnavailable as exc:
        return {"status": "UNAVAILABLE", "error": {"code": "SANDBOX_UNAVAILABLE", "message": str(exc)}}
    return {
        "status": "OK" if (result.exit_code == 0 and not result.timed_out) else "FAILED",
        "exitCode": result.exit_code,
        "timedOut": result.timed_out,
        "output": result.output,
        "truncated": result.truncated,
        "durationMs": result.duration_ms,
        "backend": result.backend,
        "memoryPeakMb": result.memory_peak_mb,
        "workdir": workdir,
    }


__all__ = ["NotebookError", "materialize_dataset", "run_notebook"]
