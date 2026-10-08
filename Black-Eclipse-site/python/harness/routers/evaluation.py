"""API surface for the Agent Evaluation system.

Follows the runtime's router conventions: ``APIRouter(tags=[...])`` with every
route (reads AND mutations) depending on ``require_operator``. The evaluation
store is bound to the ONE ``agent-memory.db`` connection.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["evaluation"])


def _eval_store() -> Any:
    from ..evaluation.store import EvaluationStore

    store = getattr(service, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="evaluation runtime unavailable")
    return EvaluationStore(store)


class StartRunBody(BaseModel):
    dataset: str = ""
    suite: str = ""
    taskId: str = ""
    trials: Optional[int] = Field(default=None, ge=1, le=50)
    live: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None


@router.get("/evaluation/runs")
def list_runs(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "runs": _eval_store().list_runs(limit=limit)}


@router.get("/evaluation/runs/{run_id}")
def get_run(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _eval_store()
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"success": True, "run": run, "metrics": store.list_regressions(run_id=run_id)}


@router.get("/evaluation/runs/{run_id}/trials")
def list_trials(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "trials": _eval_store().list_trials(run_id)}


@router.get("/evaluation/runs/{run_id}/trajectory/{trial_id}")
def get_trajectory(run_id: str, trial_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    for trial in _eval_store().list_trials(run_id):
        if trial["id"] == trial_id or trial["trialId"] == trial_id:
            return {"success": True, "trajectory": trial.get("trajectory")}
    raise HTTPException(status_code=404, detail="trial not found")


@router.get("/evaluation/tasks")
def list_tasks(category: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "tasks": _eval_store().list_tasks(category=category)}


@router.get("/evaluation/baselines")
def list_baselines(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "baselines": _eval_store().list_baselines(limit=limit)}


@router.get("/evaluation/regressions")
def list_regressions(run_id: Optional[str] = None, limit: int = 100,
                     _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "regressions": _eval_store().list_regressions(run_id=run_id, limit=limit)}


@router.get("/evaluation/failures")
def list_failures(run_id: Optional[str] = None, limit: int = 200,
                  _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "failures": _eval_store().list_failures(run_id=run_id, limit=limit)}


@router.get("/evaluation/candidates")
def list_candidates(status: Optional[str] = None, limit: int = 200,
                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "candidates": _eval_store().list_candidates(status=status, limit=limit)}


@router.post("/evaluation/runs")
def start_run(body: StartRunBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    import asyncio  # noqa: PLC0415

    from ..evaluation.gate import run_offline_gate
    from ..evaluation.runner import EvaluationRunner, ScriptedAgentInvoker

    store = getattr(service, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="evaluation runtime unavailable")

    if body.live:
        from ..evaluation.runner import ServiceAgentInvoker
        from ..evaluation.store import EvaluationStore
        from ..evaluation.tasks import load_all_builtin, load_builtin_dataset, select_tasks
        from ..schemas import ModelSettings

        settings = None
        if body.provider or body.model:
            settings = ModelSettings(provider=body.provider or "ollama",
                                     model=body.model or "llama3.1")
        invoker = ServiceAgentInvoker(service, settings)
        dataset = load_builtin_dataset(body.dataset) if body.dataset else load_all_builtin()
        tasks = select_tasks(dataset, task_id=body.taskId or None, suite=body.suite or None)
        runner = EvaluationRunner(store, invoker=invoker, eval_store=EvaluationStore(store))
        suite = asyncio.run(runner.run_suite(
            tasks, dataset_name=dataset.name, dataset_version=dataset.version,
            dataset_checksum=dataset.checksum, suite=body.suite, trials=body.trials,
            tier=2, persist=True,
        ))
        return {"success": True, "runId": suite.run_id, "aggregates": suite.aggregates,
                "categories": suite.categories}

    # Offline deterministic tier runs on a private temp store (never the dev DB).
    suite = run_offline_gate(dataset_name=body.dataset, suite=body.suite,
                             trials=body.trials or 1, task_id=body.taskId)
    return {"success": True, "runId": suite.run_id, "aggregates": suite.aggregates,
            "categories": suite.categories, "thresholds": suite.thresholds}


@router.get("/evaluation/report/{run_id}")
def get_report(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _eval_store()
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    trials = store.list_trials(run_id)
    return {
        "success": True,
        "run": run,
        "trials": len(trials),
        "passed": sum(1 for t in trials if t["passed"]),
        "unmeasured": sum(1 for t in trials if t["unmeasured"]),
        "failures": store.list_failures(run_id=run_id),
        "regressions": store.list_regressions(run_id=run_id),
    }


__all__ = ["router"]
