"""FastAPI application for the harness runtime.

Endpoints (called by the thin TS front door):
    GET  /health                 — readiness for the TS proxy
    GET  /models                 — universal provider catalog
    GET  /agents                 — agent presets
    POST /runs                   — execute (or background) a run
    POST /runs/{id}/cancel       — cooperative cancellation
    GET  /runs                   — list runs
    GET  /runs/{id}              — one run
    GET  /runs/{id}/events       — persisted trace
    GET  /usage                  — token-consumption analytics

The service never trusts the caller: pydantic validates every body.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .agents import AGENT_PRESETS, DEFAULT_AGENT_ID
from .models import list_providers
from .schemas import RunRequest, RunResult
from .service import AgenticService

logging.basicConfig(level=logging.INFO, format="[harness-py] %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="BlackEclipse Harness Runtime", version="0.1.0")
service = AgenticService()


class StartRunResponse(BaseModel):
    success: bool
    runId: str
    status: str = "running"


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "harness-runtime",
        "tools": service.registry.names(),
        "agents": list(AGENT_PRESETS.keys()),
        "defaultAgentId": DEFAULT_AGENT_ID,
        "providers": [p["id"] for p in list_providers()],
    }


@app.get("/models")
def models() -> dict[str, Any]:
    return {"success": True, "providers": list_providers()}


@app.get("/agents")
def agents() -> dict[str, Any]:
    return {
        "success": True,
        "defaultAgentId": DEFAULT_AGENT_ID,
        "agents": [a.model_dump() for a in AGENT_PRESETS.values()],
    }


@app.post("/runs")
async def start_run(request: RunRequest, background: bool = False) -> JSONResponse:
    try:
        if background:
            await service.run_background(request)
            return JSONResponse(StartRunResponse(success=True, runId=request.runId).model_dump(), status_code=202)
        result: RunResult = await service.run(request)
        return JSONResponse({"success": True, **result.model_dump()})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logging.exception("run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/runs")
def list_runs(limit: int = 50) -> dict[str, Any]:
    return {"success": True, "runs": service.list_runs(limit)}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True, "run": run}


@app.get("/usage")
def usage(days: int = 30) -> dict[str, Any]:
    """Token-consumption analytics over the agent-memory database.

    `byDay`/`byModel`/`recent` rows may total 0 when a provider omitted usage;
    `totals.runsWithUsage` says how many runs actually reported tokens, so the
    UI can be honest instead of showing a fabricated figure.
    """
    return {"success": True, **service.usage_summary(days)}


@app.get("/runs/{run_id}/events")
def get_events(run_id: str) -> dict[str, Any]:
    if not service.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "success": True,
        "runId": run_id,
        "events": service.list_events(run_id),
        "toolExecutions": service.list_tool_executions(run_id),
    }


class CancelResponse(BaseModel):
    success: bool
    runId: str
    cancelled: bool


@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    if not service.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    cancelled = service.cancel(run_id)
    return CancelResponse(success=True, runId=run_id, cancelled=cancelled).model_dump()


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
