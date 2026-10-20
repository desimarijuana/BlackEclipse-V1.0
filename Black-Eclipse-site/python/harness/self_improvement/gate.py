"""Offline release gate for the RSL conductor (R8).

Deterministic and network-free: one scripted recursive experiment with `k=2`
exercises proposal validation, per-candidate verification, anonymous selection,
conservative composition, the recorded `EvaluationRun` and the measured metric
block. It never applies a change and never touches the developer's databases.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from ..code.evolution_store import EvolutionStore
from ..evaluation.repair_metrics import metrics_from_rsl_runs, rsl_runs_from_store
from ..evaluation.store import EvaluationStore
from ..persistence import AgentMemoryStore
from .drift import DRIFT, drift_signal
from .recursion import run_recursive


def _candidate() -> dict[str, Any]:
    return {
        "id": "evo_rsl_gate",
        "signature": "sig-rsl-gate",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "A repeated timeout needs a bounded fix.",
        "targetPath": "python/harness/rsl_gate_fixture.py",
        "proposedOps": [{
            "op": "create",
            "path": "python/harness/rsl_gate_fixture.py",
            "content": "VALUE = 1\n",
            "reason": "scripted gate fixture",
        }],
        "createdByRunId": "run-rsl-gate",
    }


def _variants() -> list[dict[str, Any]]:
    return [
        {
            "kind": "invariant",
            "targetPath": "python/harness/rsl_gate_a.py",
            "ops": [{
                "op": "create", "path": "python/harness/rsl_gate_a.py",
                "content": "A = 1\n", "reason": "invariant fixture",
            }],
        },
        {
            "kind": "domain",
            "targetPath": "python/harness/rsl_gate_b.py",
            "ops": [{
                "op": "create", "path": "python/harness/rsl_gate_b.py",
                "content": "B = 1\n", "reason": "domain fixture",
            }],
        },
    ]


def run_offline_rsl_gate() -> dict[str, Any]:
    """Run one deterministic RSL end-to-end; return a pass/fail record."""
    directory = tempfile.mkdtemp(prefix="be-rsl-gate-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    failures: list[str] = []
    summary: dict[str, Any] = {}
    try:
        eval_store = EvaluationStore(store)
        scores = {"v1": 0.5, "v2": 0.6}

        def verify(proposal: Any) -> dict[str, Any]:
            return {
                "passed": True,
                "benchmark": "MEASURED",
                "score": scores.get(proposal.id),
                "runId": f"scripted-{proposal.id}",
            }

        async def measure(_composed: dict[str, Any]) -> dict[str, Any]:
            return {"passed": True, "benchmark": "MEASURED", "score": 0.8}

        result = asyncio.run(run_recursive(
            _candidate(),
            verify_fn=verify,
            k=2,
            variants=_variants(),
            seed=7,
            measure=measure,
            eval_store=eval_store,
            run_store=store,
        ))
        metrics = metrics_from_rsl_runs(rsl_runs_from_store(store))
        attempts = EvolutionStore(store).experiments_started_since(
            "1970-01-01T00:00:00.000Z",
        )
        summary = {
            "k": result.get("k"),
            "selection": (result.get("selection") or {}).get("chosen"),
            "composition": (result.get("composition") or {}).get("decision"),
            "benchmark": result.get("benchmark"),
            "metrics": metrics,
        }

        if result.get("refused"):
            failures.append("recursive experiment was refused")
        if result.get("k") != 2:
            failures.append("k was not 2")
        if (result.get("selection") or {}).get("nCandidates") != 2:
            failures.append("selection did not see two verified candidates")
        if (result.get("composition") or {}).get("decision") != "composed":
            failures.append("composition did not beat the best single candidate")
        if result.get("benchmark") != "MEASURED":
            failures.append("gate did not record a measured benchmark")
        if attempts != 2:
            failures.append(f"k did not count against the budget (attempts={attempts})")
        if metrics.get("rsl_experiments") != 1:
            failures.append("metric block did not count the RSL experiment")
        if metrics.get("rsl_accepted") != 1:
            failures.append("metric block did not count the accepted experiment")
        if metrics.get("rsl_rejected") != 0 or metrics.get("rsl_unmeasured") != 0:
            failures.append("metric block misclassified the experiment")
        if metrics.get("regression_rate") != 0.0:
            failures.append("metric block did not measure regression_rate as 0.0")

        current = [
            {"runId": f"gate-ok-{index}", "agentId": "gate-agent",
             "status": "completed" if index < 10 else "failed",
             "createdAt": f"2026-10-21T00:{index:02d}:00Z"}
            for index in range(30)
        ]
        baseline = [
            {"runId": f"gate-base-{index}", "agentId": "gate-agent",
             "status": "completed",
             "createdAt": f"2026-10-20T00:{index:02d}:00Z"}
            for index in range(100)
        ]
        drift = drift_signal(
            current + baseline, scope="gate-agent", window=30, baseline=100,
        )
        summary["drift"] = {
            "status": drift.get("status"),
            "drop": drift.get("drop"),
            "anchor": drift.get("anchor"),
        }
        if drift.get("status") != DRIFT:
            failures.append("drift gate did not detect the scripted regression")
        if drift.get("drop") is None or float(drift["drop"]) <= 0.1:
            failures.append("drift gate did not measure a drop above threshold")
        if not drift.get("anchor"):
            failures.append("drift gate did not pin an episode anchor")
    except Exception as exc:  # noqa: BLE001 - a gate reports the failure, never hides it
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        store.close()

    return {
        "passed": not failures,
        "failures": failures,
        "summary": summary,
    }


def format_rsl_gate_report(result: dict[str, Any]) -> str:
    summary = result.get("summary") or {}
    metrics = summary.get("metrics") or {}
    drift = summary.get("drift") or {}
    return (
        f"rsl gate: {'PASS' if result.get('passed') else 'FAIL'} "
        f"k={summary.get('k')} selection={summary.get('selection')} "
        f"composition={summary.get('composition')} "
        f"experiments={metrics.get('rsl_experiments')} "
        f"accepted={metrics.get('rsl_accepted')} "
        f"rejected={metrics.get('rsl_rejected')} "
        f"unmeasured={metrics.get('rsl_unmeasured')} "
        f"regression_rate={metrics.get('regression_rate')} "
        f"drift={drift.get('status')} drift_drop={drift.get('drop')}"
        + (f" failures={result.get('failures')}" if result.get("failures") else "")
    )


__all__ = ["format_rsl_gate_report", "run_offline_rsl_gate"]
