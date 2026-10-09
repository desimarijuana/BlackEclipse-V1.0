"""Eval-gate route group.

Exposes the offline, deterministic harness closeout gates (`harness.eval_gates`)
over an operator-gated HTTP surface, so an operator (or a deployment check) can
run them on demand and see the structured result. Every gate is offline and
deterministic; the TypeScript capability-matrix gate runs as a subprocess.

This is the runtime wiring for `harness/eval_gates/` — previously the package was
only exercised by the offline eval CLI. `require_operator` gates the route
exactly like the other operator surfaces.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from ..deps import require_operator

router = APIRouter(tags=["eval-gates"])


@router.get("/eval/gates")
async def run_eval_gates(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Run the harness closeout gates and return each result.

    Runs off the event loop (the capability-matrix gate shells out to tsx). A
    gate that raises is reported as a failed gate, never a 500.
    """
    from ..eval_gates import run_gates  # noqa: PLC0415

    results = await asyncio.to_thread(run_gates)
    passed = sum(1 for r in results if r.get("passed"))
    return {
        "success": all(r.get("passed") for r in results),
        "passed": passed,
        "total": len(results),
        "gates": results,
    }


__all__ = ["router"]
