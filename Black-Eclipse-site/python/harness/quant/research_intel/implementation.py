"""Run one registered research implementation in a separate process.

The method specification may carry `implementation: {"kind": "python",
"source": "..."}"`. The source must define `run(rows, params) -> dict`.

This is the generic path for methods that are not built in. The parent writes
the source and data to a temp directory, launches the worker with `python -I`, a
scrubbed environment, a wall-clock timeout and an output-size cap. It never
executes the code inside the API process.

Process isolation is not a container. A hard filesystem/network boundary is the
harness sandbox's responsibility; the result says `isolation: "process"` so the
claim is honest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Iterable

_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "implementation_worker.py")
_ENV_ALLOW = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT",
              "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL")
_MAX_OUTPUT_BYTES = 2_000_000


class ImplementationError(Exception):
    code = "IMPLEMENTATION_ERROR"


def _env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_ALLOW if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_implementation(
    source: str,
    rows: Iterable[Any] | None,
    params: dict[str, Any] | None = None,
    *,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Run `source` in an isolated worker. Returns a structured result."""
    if not str(source or "").strip():
        return {"status": "inconclusive", "reason": "the implementation is empty"}
    with tempfile.TemporaryDirectory(prefix="eclipse-research-") as work:
        source_path = os.path.join(work, "method_impl.py")
        in_path = os.path.join(work, "input.json")
        out_path = os.path.join(work, "output.json")
        with open(source_path, "w", encoding="utf-8") as fh:
            fh.write(str(source))
        with open(in_path, "w", encoding="utf-8") as fh:
            json.dump({"sourcePath": source_path, "rows": list(rows or []),
                       "params": params or {}}, fh, ensure_ascii=False,
                      default=str)
        from ..sdk_runtime import docker_command, resolve_sandbox

        backend = resolve_sandbox("auto")
        if backend == "docker":
            import shutil

            shutil.copyfile(_WORKER, os.path.join(work, "implementation_worker.py"))
            with open(in_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            payload["sourcePath"] = "/work/method_impl.py"
            with open(in_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, default=str)
            image = os.environ.get("HARNESS_QUANT_SDK_DOCKER_IMAGE", "")
            command = docker_command(image, work, "input.json", "output.json",
                                     entry="implementation_worker.py")
        else:
            command = [sys.executable, "-I", _WORKER, in_path, out_path]
        try:
            proc = subprocess.run(
                command, cwd=work, env=_env(), timeout=max(1.0, float(timeout_s)),
                capture_output=True, text=True,
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "the implementation timed out",
                    "isolation": backend}
        if proc.returncode != 0:
            return {"status": "failed",
                    "error": (proc.stderr or "the worker exited with an error")[-2000:],
                    "isolation": backend}
        try:
            size = os.path.getsize(out_path)
        except OSError:
            return {"status": "failed", "error": "the worker produced no output",
                    "isolation": backend}
        if size > _MAX_OUTPUT_BYTES:
            return {"status": "failed", "error": "the output exceeded the size cap",
                    "isolation": backend}
        with open(out_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    if payload.get("status") != "ok":
        return {"status": "failed", "error": payload.get("error") or "worker error",
                "isolation": backend}
    result = payload.get("result") or {}
    return {"status": "OK", "metrics": result, "isolation": backend,
            "note": "Ran in a separate process with a scrubbed environment and a timeout."}


__all__ = ["ImplementationError", "run_implementation"]
