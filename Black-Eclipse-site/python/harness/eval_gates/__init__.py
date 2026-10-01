"""Harness closeout eval gates (Phase 8).

Four OFFLINE, deterministic gates that make the defects Phases 2–5 fix unable to
regress:

  * ``capability_matrix`` — asserted in TypeScript (``scripts/eval-capability-matrix.ts``)
    because the matrix lives in ``src/lib/harness/capability.ts``.
  * ``route_health`` — on a sparse ledger, ``get_source_health``'s rendered text
    stays under ``MAX_TOOL_RESULT_CHARS`` and names at least one recorded route;
    a fixture probe is never presented as live; no persisted row carries a literal
    ``unknown`` in source/market.
  * ``workflow`` — a valid workflow, a cyclic one, an out-of-scope step and an
    approval replay each produce their documented outcome, asserted on structured
    error codes / persisted rows, never on model prose.
  * ``resume`` — a mid-run kill, asserting exactly one terminal status and zero
    duplicate tool executions after resume.

Every gate is offline and deterministic; none needs the network.
"""

from __future__ import annotations

from typing import Any, Callable

GateResult = dict[str, Any]


def _gate(name: str, fn: Callable[[], None]) -> GateResult:
    try:
        fn()
        return {"name": name, "passed": True, "failures": []}
    except AssertionError as exc:  # noqa: PERF203
        return {"name": name, "passed": False, "failures": [str(exc) or "assertion failed"]}
    except Exception as exc:  # noqa: BLE001 - a gate error is a gate failure
        return {"name": name, "passed": False, "failures": [f"{type(exc).__name__}: {exc}"]}


def run_gates() -> list[GateResult]:
    """Run the Python-side gates plus the TS capability-matrix gate."""
    from . import route_health, workflow, resume

    results = [
        _gate("route_health", route_health.run_gate),
        _gate("workflow", workflow.run_gate),
        _gate("resume", resume.run_gate),
    ]
    results.append(_run_capability_matrix_gate())
    return results


def _run_capability_matrix_gate() -> GateResult:
    """Invoke the TypeScript capability-matrix gate as a subprocess (offline)."""
    import os
    import subprocess
    import sys

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    script = os.path.join(root, "scripts", "eval-capability-matrix.ts")
    # Prefer the local tsx binary (avoid a shell + npx shim lookup that fails on
    # some Windows setups); fall back to `npx tsx`.
    tsx = os.path.join(root, "node_modules", ".bin", "tsx.cmd")
    if not os.path.exists(tsx):
        alt = os.path.join(root, "node_modules", ".bin", "tsx")
        tsx = alt if os.path.exists(alt) else ""
    cmd = [tsx, script] if tsx else ["npx", "tsx", script]
    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, timeout=180, shell=False,
        )
    except Exception as exc:  # noqa: BLE001 - a gate error is a gate failure
        return {"name": "capability_matrix", "passed": False, "failures": [str(exc)]}
    if proc.returncode != 0:
        return {
            "name": "capability_matrix", "passed": False,
            "failures": [(proc.stdout or "")[-800:] or (proc.stderr or "")[-800:]],
        }
    return {"name": "capability_matrix", "passed": True, "failures": []}


__all__ = ["run_gates"]
