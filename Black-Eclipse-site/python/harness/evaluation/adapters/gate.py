"""Run the offline external-adapter gate (C8.2)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any, Iterable, Optional

from ..runner import EvaluationRunner, ScriptedAgentInvoker
from ..store import EvaluationStore
from .base import ADAPTERS, FixtureAdapter


def _run_one(adapter: FixtureAdapter, *, trials: int = 1) -> dict[str, Any]:
    from ...persistence import AgentMemoryStore  # noqa: PLC0415

    directory = tempfile.mkdtemp(prefix="be-eval-external-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        tasks = adapter.load(limit=50)
        if not tasks:
            return {**adapter.info().to_dict(), "passed": False, "suiteOk": False,
                    "aggregates": {}, "error": "no fixture tasks"}
        runner = EvaluationRunner(
            store, invoker=ScriptedAgentInvoker(store), eval_store=EvaluationStore(store),
        )
        suite = asyncio.run(runner.run_suite(
            tasks, dataset_name=adapter.name, dataset_version=adapter.version,
            dataset_checksum="", suite="external", trials=trials, tier=0, persist=False,
        ))
        return {
            **adapter.info().to_dict(),
            "passed": bool(suite.passed),
            "suiteOk": bool(suite.passed),
            "aggregates": dict(suite.aggregates),
            "tasks": len(tasks),
            "error": None if suite.passed else "one or more fixture tasks failed",
        }
    finally:
        store.close()


def run_external_gate(
    adapters: Optional[Iterable[FixtureAdapter]] = None, *, trials: int = 1,
) -> dict[str, Any]:
    selected = list(adapters or ADAPTERS)
    results = [_run_one(adapter, trials=trials) for adapter in selected]
    available = [r for r in results if r.get("available")]
    failed = [r["name"] for r in available if not r.get("passed")]
    return {
        "ok": bool(results) and not failed,
        "adapters": results,
        "available": len(available),
        "missing": [r["name"] for r in results if not r.get("available")],
        "failed": failed,
    }


__all__ = ["run_external_gate"]
