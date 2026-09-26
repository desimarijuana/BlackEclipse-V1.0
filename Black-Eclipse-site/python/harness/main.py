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

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .agents import AGENT_PRESETS, DEFAULT_AGENT_ID
from .mcp.config import (
    MCPServerConfig,
    remove_mcp_config,
    upsert_mcp_config,
)
from .models import list_providers
from .persistence import now_iso
from .research.engine import run_research
from .research.mandate import parse_mandate
from .schemas import RunRequest, RunResult
from .service import AgenticService
from .skills.draft import propose_draft
from .skills.evaluation import evaluate_skill
from .skills.learning import capture_from_run
from .skills.lifecycle import (
    approve_promotion,
    reject_promotion,
    request_promotion,
    rollback,
)
from .skills.permissions import Actor
from .skills.runtime import SkillExecutionRequest

logging.basicConfig(level=logging.INFO, format="[harness-py] %(levelname)s %(name)s: %(message)s")

service = AgenticService()

# The service is process-wide, but FastAPI may enter/exit the lifespan more than
# once (nested test clients, reload). Reference-count so only the LAST exit tears
# MCP down — an inner lifespan must never disconnect the servers a sibling still
# uses.
_lifespan_refs = 0


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Connect configured MCP servers and register selected read-only tools. A
    # failure is a diagnostic, never a boot blocker (AgenticService.start_mcp).
    global _lifespan_refs
    _lifespan_refs += 1
    if _lifespan_refs == 1:
        # Retention: mark due AUTOMATIC memories expired on startup. Idempotent
        # and best-effort — a failure is a diagnostic, never a boot blocker.
        service.run_startup_maintenance()
        await service.start_mcp()
        # The bounded learning-review queue: reviews completed runs in the
        # background. It only creates inert records/suggestions and never enables
        # a skill. A failure is a diagnostic, never a boot blocker.
        await service.start_learning_review()
    try:
        yield
    finally:
        _lifespan_refs -= 1
        if _lifespan_refs == 0:
            # Cancel queued reviews and terminate MCP subprocesses cleanly so none
            # leak across restarts.
            await service.stop_learning_review()
            await service.stop_mcp()


app = FastAPI(title="BlackEclipse Harness Runtime", version="0.1.0", lifespan=_lifespan)

# Process start time (epoch ms). The TS launcher compares this against the
# build time of `python/harness/` to detect an orphaned runtime from an earlier
# `npm run dev` that is still holding the port and serving stale code.
_STARTED_AT_MS = int(time.time() * 1000)


def _jsonschema_available() -> bool:
    """Whether the full JSON Schema validator is installed (skill contracts)."""
    from .skills.schema_validation import jsonschema_available

    return jsonschema_available()


class StartRunResponse(BaseModel):
    success: bool
    runId: str
    status: str = "running"


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "harness-runtime",
        "startedAtMs": _STARTED_AT_MS,
        "tools": service.registry.names(),
        "agents": list(AGENT_PRESETS.keys()),
        "defaultAgentId": DEFAULT_AGENT_ID,
        "providers": [p["id"] for p in list_providers()],
        "retrieval": service.retrieval_metrics(),
        # The RESOLVED memory/skills database path + non-secret identity. This is
        # what makes a cwd-mismatch observable instead of silent. Deliberately
        # lighter than /eclipse-memory/health (no integrity_check) because this
        # endpoint is polled by the launcher.
        "eclipseMemory": {
            **service.memory.store.db.identity_summary(),
            "schemaVersion": service.memory.store.migration_status()["schemaVersion"],
            "upToDate": service.memory.store.migration_status()["upToDate"],
        },
        "runStore": {"path": service.store.path},
        "skills": {
            "installed": len(service.skill_registry.all_manifests()),
            "loadErrors": service.skill_load_errors,
            "duplicates": service.skill_registry.duplicate_ids(),
            # Whether full JSON Schema contract validation is available. False
            # means skill schemas fail closed (cannot be verified), so an
            # operator can see why and repair the runtime.
            "schemaValidation": _jsonschema_available(),
        },
        # MCP (Phase 5): configured/connected server counts + registered tool
        # count. Never includes secret values or full server output.
        "mcp": service.mcp.summary(),
    }


@app.get("/retrieval/metrics")
def retrieval_metrics() -> dict[str, Any]:
    """Retrieval-layer performance counters (cache hits/misses, in-flight)."""
    return {"success": True, **service.retrieval_metrics()}


# ── MCP server catalog (Phase 5E) ───────────────────────────────────────────
# Add / test / enable / disable / remove local stdio MCP servers and select
# their tools. Mutations require PROOF OF AUTHORIZATION, never a caller-supplied
# JSON boolean: the request must originate from the loopback interface (the
# Next.js front door / a local operator) OR present the runtime secret. A
# directly reachable Python runtime therefore cannot be handed arbitrary
# subprocess configuration by spoofing `operator: true`. Reads stay open and are
# secret-free (env KEYS only).

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_loopback(request: Request) -> bool:
    client = request.client
    host = (client.host if client else "") or ""
    return host in _LOOPBACK_HOSTS


def _valid_operator_token(request: Request) -> bool:
    """Validate the runtime secret WITHOUT ever logging or echoing it."""
    import hmac
    import os

    secret = os.environ.get("CRON_SECRET")
    if not secret or secret == "change-me-to-a-random-secret":
        return False
    provided = request.headers.get("x-harness-operator") or ""
    auth = request.headers.get("authorization") or ""
    bearer = auth[7:] if auth.startswith("Bearer ") else ""
    for candidate in (provided, bearer):
        if candidate and hmac.compare_digest(candidate, secret):
            return True
    return False


def require_operator(request: Request) -> bool:
    """FastAPI dependency: prove the caller MAY set the operator flag.

    Proof is transport/token only — NEVER a caller-supplied JSON boolean:
    the request must originate from the loopback interface (the Next.js front
    door or a local operator) OR present the runtime secret in
    `X-Harness-Operator` / a Bearer token.

    A memory/skill mutation endpoint reads the body `operator` flag only AFTER
    this dependency passes, so a directly reachable Python runtime cannot be
    handed an operator decision by spoofing `{"operator": true}`; a remote
    caller without the secret is refused before the body is considered.
    """
    if _is_loopback(request) or _valid_operator_token(request):
        return True
    raise HTTPException(
        status_code=403,
        detail="this operation requires an authorized operator (loopback or runtime secret)",
    )


def require_mcp_operator(request: Request) -> None:
    """FastAPI dependency: authorize an MCP mutation by transport or token.

    Loopback is trusted (zero-config local use keeps working). A remote caller
    must present the runtime secret as `X-Harness-Operator` (or a Bearer token).
    The body is never consulted, so `{"operator": true}` cannot authorize.
    """
    if _is_loopback(request) or _valid_operator_token(request):
        return
    raise HTTPException(
        status_code=403,
        detail="MCP configuration requires an authorized operator (loopback or runtime secret)",
    )


@app.get("/mcp/servers")
def list_mcp_servers() -> dict[str, Any]:
    """Configured servers + live status + discovered tools (secret-free)."""
    return {"success": True, "servers": service.mcp.public_configs(), **service.mcp.summary()}


class MCPServerUpsertRequest(BaseModel):
    """Create/replace one server. The full config is validated by pydantic."""

    server: MCPServerConfig
    reload: bool = True
    # The authoritative env key set (values are write-only and never echoed to
    # the UI, so the client sends key names to add/remove while values persist).
    envKeys: Optional[list[str]] = None  # noqa: N815


@app.post("/mcp/servers")
async def upsert_mcp_server(request: MCPServerUpsertRequest, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    upsert_mcp_config(request.server, env_keys=request.envKeys)
    summary = await service.reload_mcp() if request.reload else service.mcp.summary()
    return JSONResponse({"success": True, **summary})


@app.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    removed = remove_mcp_config(server_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Server not found")
    summary = await service.reload_mcp()
    return JSONResponse({"success": True, "removed": server_id, **summary})


@app.post("/mcp/servers/test")
async def test_mcp_server(payload: dict[str, Any], _: None = Depends(require_mcp_operator)) -> JSONResponse:
    """Connect + discover a candidate config WITHOUT persisting or activating."""
    raw = payload.get("server")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="server config is required")
    try:
        config = MCPServerConfig(**raw)
    except Exception as exc:  # noqa: BLE001 - a bad config is a 400, not a crash
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await service.mcp.test_server(config)
    return JSONResponse({"success": result.get("state") == "connected", **result})


@app.post("/mcp/reload")
async def reload_mcp(_: None = Depends(require_mcp_operator)) -> JSONResponse:
    summary = await service.reload_mcp()
    return JSONResponse({"success": True, **summary})


@app.post("/mcp/servers/{server_id}/confirm")
async def confirm_mcp_catalog(server_id: str, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    """Record the operator's review of a server's current catalog digest.

    The explicit act that lets an annotation-sourced read-only tool activate.
    """
    result = await service.confirm_mcp_catalog(server_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("reason") or "confirm failed"))
    return JSONResponse(result)


# ── Effectful-tool approvals (Phase 5G) ─────────────────────────────────────
# A write/external_action MCP tool needs an operator decision bound to the exact
# server/tool/arguments. These endpoints let the operator review and decide;
# they hold no secret material — only identity + an argument digest.


@app.get("/mcp/approvals")
def list_mcp_approvals(status: Optional[str] = None) -> dict[str, Any]:
    return {"success": True, "approvals": service.approvals.list(status)}


@app.post("/mcp/approvals/{approval_id}/decide")
async def decide_mcp_approval(
    approval_id: str, payload: dict[str, Any], _: None = Depends(require_mcp_operator)
) -> JSONResponse:
    approve = bool(payload.get("approve"))
    result = service.approvals.decide(
        approval_id, approve=approve,
        decided_by=str(payload.get("decidedBy") or "operator"),
        reason=str(payload.get("reason") or ""),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return JSONResponse({"success": True, "approval": result})


# ── Finance presets, workflows and setup diagnostics (product layer) ────────
# These describe and inspect; they never activate a server or run a tool.


@app.get("/mcp/integrations")
def list_mcp_integrations() -> dict[str, Any]:
    from .mcp.presets import list_integrations

    return {"success": True, "integrations": list_integrations()}


@app.get("/mcp/workflows")
def list_mcp_workflows() -> dict[str, Any]:
    from .mcp.presets import list_workflows

    return {"success": True, "workflows": list_workflows()}


@app.post("/mcp/diagnostics")
def mcp_diagnostics(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Setup diagnostics for every configured server + the environment.

    `knownSecrets` (secret NAMES only) lets the runtime report missing vault
    references without ever seeing a value.
    """
    known = set()
    if isinstance(payload, dict):
        for name in payload.get("knownSecrets") or []:
            if isinstance(name, str):
                known.add(name)
    resolved: dict[str, dict[str, bool]] = {}
    for cfg in service.mcp._runtimes.values():  # noqa: SLF001 - read-only inspection
        resolved[cfg.config.id] = {name: (name in known) for name in cfg.config.secret_ref_names()}
    return {"success": True, **service.mcp.diagnostics(resolved)}


class ResearchRunRequest(BaseModel):
    """A research-mandate request (Phase 4). The front door proxies this; the
    runtime owns the mandate → coverage flow. `query` is the objective."""

    query: str
    ticker: Optional[str] = None
    market: Optional[str] = None
    asOf: Optional[str] = None
    callbackBaseUrl: str
    callbackToken: Optional[str] = None
    runId: Optional[str] = None


@app.post("/research/mandate")
def research_mandate(payload: dict[str, Any]) -> dict[str, Any]:
    """Classify an objective into a typed research mandate (no retrieval)."""
    mandate = parse_mandate(
        str(payload.get("query") or ""),
        ticker=payload.get("ticker"),
        market=payload.get("market"),
        as_of=payload.get("asOf"),
    )
    return {"success": True, "mandate": mandate.model_dump()}


@app.post("/research/run")
async def research_run(request: ResearchRunRequest) -> JSONResponse:
    """Execute the evidence-grounded research flow for one objective.

    Returns the mandate, per-leg coverage, validated claims and the durable
    receipt. A general (unsupported) objective returns `supported=False` so the
    caller continues on the existing chat path.
    """
    mandate = parse_mandate(
        request.query, ticker=request.ticker, market=request.market, as_of=request.asOf
    )
    if not mandate.supported:
        return JSONResponse(
            {
                "success": True,
                "supported": False,
                "mandate": mandate.model_dump(),
                "reason": "objective is not a supported financial comparison",
            }
        )

    bridge = service.build_bridge(request.callbackBaseUrl, request.callbackToken)
    run_id = request.runId or f"research_{now_iso()}"

    async def _retrieve(req):  # noqa: ANN001 - shaped like the layer
        return await service.retrieve_for_research(bridge, req)

    outcome = await run_research(
        mandate, _retrieve, run_id=run_id,
        provider=None, model=None,
    )
    persistence_error: Optional[str] = None
    try:
        if outcome.receipt is not None:
            service.store.save_receipt(outcome.receipt.model_dump())
    except Exception as exc:  # noqa: BLE001 - persistence failure is observable, never hidden
        logging.exception("research receipt persistence failed")
        persistence_error = str(exc)

    return JSONResponse(
        {
            "success": True,
            "supported": True,
            "status": outcome.status,
            "mandate": outcome.mandate.model_dump(),
            "coverage": outcome.coverage.model_dump(),
            "metadata": outcome.metadata.model_dump() if outcome.metadata else None,
            "receipt": outcome.receipt.model_dump() if outcome.receipt else None,
            "persistenceError": persistence_error,
        }
    )


@app.get("/research/receipts")
def list_receipts(limit: int = 50) -> dict[str, Any]:
    return {"success": True, "receipts": service.store.list_receipts(limit)}


@app.get("/research/receipts/{run_id}")
def get_receipt(run_id: str) -> dict[str, Any]:
    receipt = service.store.get_receipt(run_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"success": True, "receipt": receipt}


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


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    """Server-Sent Events for one run: live status + token deltas.

    Emits `event: <type>` frames. Token deltas arrive as transient event types
    (e.g. `model.delta`) and are NOT persisted. If the run already finished,
    the persisted trace is replayed first so a late subscriber still sees it.
    A keep-alive comment every 15s prevents proxy timeouts.
    """
    queue = service.bus.open_stream(run_id)

    async def _frames() -> AsyncIterator[str]:
        try:
            # Replay what already happened (a client may connect after the run
            # started, or after it ended).
            for event in service.list_events(run_id):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            if not service.get_run(run_id) or service.is_active(run_id):
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    if event is None:
                        break
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            yield "event: stream.end\ndata: {}\n\n"
        finally:
            service.bus.close_stream(run_id, queue)

    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


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


# ── Skills (Phase 3) ────────────────────────────────────────────────────────
# The front door proxies these; Python owns the registry, permissions and
# lifecycle. Authorization is explicit: `operator=true` is only set by the front
# door after it authenticated the runtime secret (or a direct caller presenting
# it). The default actor is read-only and cannot create/enable/review skills.


def _actor(operator: bool = False, actor_id: str = "local") -> Actor:
    from .skills.permissions import OPERATOR_ACTOR

    return OPERATOR_ACTOR if operator else Actor(id=actor_id)


@app.get("/skills")
def list_skills(status: Optional[str] = None) -> dict[str, Any]:
    registry = service.skill_registry
    return {
        "success": True,
        "skills": registry.list_summaries(),
        "loadErrors": service.skill_load_errors,
        "duplicates": registry.duplicate_ids(),
    }


@app.get("/skills/{skill_id}")
def get_skill(skill_id: str) -> dict[str, Any]:
    registry = service.skill_registry
    manifest = registry.manifest(skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    record = registry.store.get_skill(skill_id)
    return {
        "success": True,
        "skill": {
            **manifest.model_dump(),
            "instructions": registry.get(skill_id).load_instructions() if registry.get(skill_id) else "",
            "storedStatus": record["status"] if record else manifest.status,
            "latestVersion": record["latestVersion"] if record else manifest.version,
            "validation": registry.validate(skill_id),
            "versions": registry.version_history(skill_id),
            "executions": registry.execution_history(skill_id, 20),
            "evaluations": registry.evaluation_history(skill_id),
            "reviews": registry.store.list_reviews(skill_id, 20),
            "events": registry.store.list_events(skill_id, 50),
        },
    }


@app.get("/skills/{skill_id}/versions")
def skill_versions(skill_id: str) -> dict[str, Any]:
    if service.skill_registry.manifest(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"success": True, "versions": service.skill_registry.version_history(skill_id)}


# ── Eclipse-Memory ──────────────────────────────────────────────────────────


@app.get("/eclipse-memory/health")
def eclipse_memory_health() -> dict[str, Any]:
    return {"success": True, **service.memory.health()}


def _memory_available() -> bool:
    """True when the memory database is readable and not corrupt.

    A corrupt database must fail HONESTLY ("memory unavailable") rather than
    answer a recall/write with wrong data. Cheap enough for the mutation/read
    paths that guard on it.
    """
    try:
        store = service.memory_store
        return bool(store.db.integrity_ok())
    except Exception:  # noqa: BLE001 - unreadable memory is unavailable memory
        return False


@app.get("/eclipse-memory/overview")
def eclipse_memory_overview() -> dict[str, Any]:
    """Real counts only — never fabricated activity."""
    store = service.memory_store
    memories = store.list_memories(limit=500, include_inactive=True)
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for memory in memories:
        by_type[memory["memoryType"]] = by_type.get(memory["memoryType"], 0) + 1
        by_status[memory["status"]] = by_status.get(memory["status"], 0) + 1
    return {
        "success": True,
        "memories": {"total": len(memories), "byType": by_type, "byStatus": by_status},
        "skills": {"installed": len(service.skill_registry.all_manifests())},
        "candidates": len(store.list_candidates(limit=500)),
        "corrections": len(store.list_corrections(limit=500)),
        "mistakes": len(store.list_mistakes(limit=500)),
        "retrievals": len(store.list_retrievals(limit=500)),
        "suggestions": len(store.list_suggestions(status="pending", limit=500)),
        "health": service.memory.health(),
    }


@app.get("/eclipse-memory/memories")
def list_memories(
    memoryType: Optional[str] = None, scope: Optional[str] = None,
    status: Optional[str] = None, subject: Optional[str] = None,
    source: Optional[str] = None, limit: int = 100,
) -> dict[str, Any]:
    return {"success": True, "memories": service.memory_store.list_memories(
        memory_type=memoryType, scope=scope, status=status, subject=subject,
        source=source, limit=limit, include_inactive=True,
    )}


@app.get("/eclipse-memory/memories/{memory_id}")
def get_memory(memory_id: str) -> dict[str, Any]:
    memory = service.memory_store.get_memory(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {
        "success": True,
        "memory": memory,
        "evidence": service.memory_store.list_evidence(memory_id),
        "links": service.memory_store.list_links(memory_id),
        "explanation": service.memory.explain_memory(memory_id),
    }


@app.get("/eclipse-memory/lifecycle")
def memory_lifecycle(view: Optional[str] = None, scopeId: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    """Lifecycle overview + a named view (active/expired/superseded/never-used/…).

    Content is returned because this is the local operator's own memory; never
    expose secrets (there are none stored — secrets are refused on write).
    """
    overview = service.memory.lifecycle_overview()
    payload: dict[str, Any] = {"success": True, **overview}
    if view:
        payload["memories"] = service.memory_store.list_lifecycle_memories(
            view, scope_id=scopeId, limit=limit,
        )
        payload["view"] = view
    return payload


@app.get("/eclipse-memory/memories/{memory_id}/explain")
def explain_memory(memory_id: str) -> dict[str, Any]:
    explanation = service.memory.explain_memory(memory_id)
    if explanation is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "explanation": explanation}


@app.post("/eclipse-memory/memories")
def create_memory(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory write requires an authorized operator")
    # A UI save is a direct human action, but it still passes the ONE shared
    # decision gate (provenance=ui_save) so privacy/content rules cannot be
    # bypassed and the write always goes through the service pipeline.
    from .eclipse_memory.decision import authorize_proposal

    try:
        decision = authorize_proposal(
            content=str(payload.get("content") or ""),
            provenance="ui_save",
            user_id=payload.get("scopeId"),
            memory_type=str(payload.get("memoryType") or "semantic"),
            scope=str(payload.get("scope") or "general"),
            scope_id=payload.get("scopeId"),
            subject=payload.get("subject"),
            confidence=float(payload.get("confidence", 0.7)),
            settings=service.memory.policy.get_all(),
        )
        outcome = service.memory.commit_decision(decision, user_id=payload.get("scopeId"))
        if not outcome.get("ok"):
            raise ValueError(decision.reason or outcome.get("reason") or "write rejected")
        memory = outcome["memory"]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - a rejected write is a 400, not a crash
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "memory": memory}


@app.patch("/eclipse-memory/memories/{memory_id}")
def patch_memory(memory_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory update requires an authorized operator")
    updated = service.memory_store.update_memory(
        memory_id, content=payload.get("content"), status=payload.get("status"),
        confidence=payload.get("confidence"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@app.post("/eclipse-memory/memories/{memory_id}/archive")
def archive_memory(memory_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory archive requires an authorized operator")
    updated = service.memory_store.archive_memory(
        memory_id, payload.get("status", "archived"), reason=payload.get("reason"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@app.post("/eclipse-memory/memories/{memory_id}/restore")
def restore_memory(memory_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory restore requires an authorized operator")
    updated = service.memory_store.restore_memory(memory_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@app.post("/eclipse-memory/memories/{memory_id}/renew")
def renew_memory(memory_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory renewal requires an authorized operator")
    days = payload.get("days")
    updated = service.memory.renew_memory(memory_id, days=int(days) if days is not None else None)
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@app.post("/eclipse-memory/retention/sweep")
def retention_sweep(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Apply the configured retention policy: due AUTOMATIC memories become
    inert (`expired`). Never deletes; explicit memories are exempt. Idempotent
    and observable (inspected/expired/skipped/ranAt)."""
    return {"success": True, **service.memory.expire_due_memories()}


@app.get("/eclipse-memory/retention")
def retention_status() -> dict[str, Any]:
    """The retention policy state + the last sweep outcome (no memory content)."""
    return {"success": True, **service.memory.retention_status()}


@app.get("/eclipse-memory/semantic-status")
def semantic_status() -> dict[str, Any]:
    """The active conflict-detection mode + semantic fallback state.

    Read-only; exposes no embedding, model path or memory content. `mode` is
    `lexical`, `lexical+semantic`, or `lexical+semantic-unavailable`. Includes
    bounded controls, backend health and diagnostic counters.
    """
    return {"success": True, **service.memory.semantic_status()}


@app.post("/eclipse-memory/semantic/rebuild")
def semantic_rebuild(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Clear/rebuild the optional local semantic index.

    Honest by design: the v1 local backends hold NO persistent index (similarity
    is computed per write over an already-authorized in-memory pool), so there is
    nothing to clear or corrupt. This reports that fact; it never deletes memory
    and never triggers a model download or network call. A future backend that
    does keep an index would clear/rebuild it here.
    """
    status = service.memory.semantic_status()
    return {
        "success": True,
        "rebuilt": False,
        "persistentIndex": False,
        "reason": (
            "no persistent semantic index exists for the active backend; "
            "similarity is computed per write"
        ),
        "backend": status.get("backend"),
        "available": status.get("semanticAvailable"),
    }


@app.post("/eclipse-memory/memories/{memory_id}/review")
def review_memory(memory_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory review requires an authorized operator")
    updated = service.memory.review_memory(memory_id, approve=bool(payload.get("approve")), reviewed_by="operator")
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "memory": updated}


@app.post("/eclipse-memory/retrieve")
def retrieve_memory(payload: dict[str, Any]) -> dict[str, Any]:
    if not _memory_available():
        raise HTTPException(status_code=503, detail="memory is unavailable (database unreadable or corrupt)")
    result = service.memory.retrieve(
        query=str(payload.get("query") or ""),
        memory_types=payload.get("types"),
        scope=payload.get("scope"),
        scope_id=payload.get("scopeId"),
        subject=payload.get("subject"),
        actor_scope=payload.get("actorScope"),
        budget_chars=int(payload.get("budgetChars", 4000)),
        limit=int(payload.get("limit", 8)),
        run_id=payload.get("runId"),
    )
    return {"success": True, "memories": result.memories, "context": result.context,
            "diagnostics": result.diagnostics}


@app.get("/eclipse-memory/retrievals")
def list_retrievals(limit: int = 50) -> dict[str, Any]:
    return {"success": True, "retrievals": service.memory_store.list_retrievals(limit)}


@app.get("/eclipse-memory/corrections")
def list_corrections(limit: int = 100) -> dict[str, Any]:
    return {"success": True, "corrections": service.memory_store.list_corrections(limit)}


@app.get("/eclipse-memory/mistakes")
def list_mistakes(runId: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    return {"success": True, "mistakes": service.memory_store.list_mistakes(runId, limit)}


@app.post("/eclipse-memory/corrections")
def create_correction(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="correction capture requires an authorized operator")
    # A correction is an explicit human action, but it still passes the shared
    # gate so a correction cannot smuggle a secret/override/financial fact into
    # durable memory.
    from .eclipse_memory.decision import authorize_proposal

    correction_text = str(payload.get("correction") or "")
    decision = authorize_proposal(
        content=correction_text, provenance="correction",
        user_id=payload.get("scopeId"),
        memory_type="correction",
        scope=str(payload.get("scope") or "user"),
        subject=payload.get("subject"),
        confidence=0.9,
        settings=service.memory.policy.get_all(),
    )
    if decision.outcome != "save":
        raise HTTPException(status_code=400, detail=decision.reason or "correction rejected")
    result = service.memory.record_correction(
        wrong=str(payload.get("wrong") or ""),
        correction=correction_text,
        subject=payload.get("subject"),
        run_id=payload.get("runId"),
        provided_by=str(payload.get("providedBy") or "user"),
        scope=str(payload.get("scope") or "user"),
        generalizable=bool(payload.get("generalizable")),
    )
    return {"success": True, **result}


@app.get("/eclipse-memory/policies")
def get_policies() -> dict[str, Any]:
    from .eclipse_memory.policy import BOUNDS, DEFAULTS, LOCKED_VALUES

    return {
        "success": True,
        "policies": service.memory.policy.get_all(),
        "defaults": DEFAULTS,
        "bounds": {k: list(v) for k, v in BOUNDS.items()},
        "locked": LOCKED_VALUES,
        "budget": service.memory.memory_budget(),
    }


@app.put("/eclipse-memory/policies")
def update_policies(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="policy changes require an authorized operator")
    updates = payload.get("policies") or {}
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="policies must be an object")
    from .eclipse_memory.policy import PolicyError

    applied: list[dict[str, Any]] = []
    try:
        for key, value in updates.items():
            applied.append(service.memory.policy.set(key, value, updated_by="operator"))
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "applied": applied, "policies": service.memory.policy.get_all()}


@app.post("/eclipse-memory/analyze/{run_id}")
def analyze_run_endpoint(run_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Deterministic post-run analysis: mistakes + (policy-gated) candidates.

    This creates records, so it requires proof of operator authorization
    (transport/token) — a body boolean cannot authorize it.
    """
    payload = payload or {}
    if service.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    result = service.memory.analyze_run(run_id, service.store, skill_store=service.skill_store)
    return {"success": True, **result}


@app.get("/eclipse-memory/events")
def list_memory_events(limit: int = 100) -> dict[str, Any]:
    return {
        "success": True,
        "events": service.memory_store.list_memory_events(limit),
        "skillEvents": service.skill_store.list_events(limit=limit),
    }


# ── Compact prompt profile (always-available personalization) ────────────────


@app.get("/eclipse-memory/profile")
def memory_profile(scopeId: Optional[str] = None) -> dict[str, Any]:
    """The current compact profile (read-only materialization, not persisted).

    Returns the selected memories, the excluded memories + reasons, the
    character/token estimate and the rendered prompt block.
    """
    if not _memory_available():
        raise HTTPException(status_code=503, detail="memory is unavailable (database unreadable or corrupt)")
    snapshot = service.memory.build_profile(scope_id=scopeId, persist=False)
    from .eclipse_memory.profile import preview_payload

    payload = preview_payload(snapshot)
    payload["history"] = service.memory.profile_history(limit=10)
    return payload


@app.get("/eclipse-memory/profile/preview")
def memory_profile_preview(scopeId: Optional[str] = None) -> dict[str, Any]:
    """A pure preview of what the next run would inject (never persisted)."""
    if not _memory_available():
        raise HTTPException(status_code=503, detail="memory is unavailable (database unreadable or corrupt)")
    return service.memory.profile_preview(scope_id=scopeId)


@app.post("/eclipse-memory/profile/rebuild")
def memory_profile_rebuild(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Materialize and PERSIST a fresh profile snapshot (operator action).

    Rebuilds the projection from current active memory and records the
    reproducible snapshot metadata. It never writes or alters a memory record.
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="profile rebuild requires an authorized operator")
    snapshot = service.memory.build_profile(
        scope_id=payload.get("scopeId"), persist=True
    )
    from .eclipse_memory.profile import preview_payload

    return {**preview_payload(snapshot), "rebuilt": True}


# ── Session history search (full-session historical recall) ─────────────────


@app.get("/session-search/health")
def session_search_health() -> dict[str, Any]:
    """Index health + whether FTS5 is available. Never claims success falsely."""
    store = service.store
    return {
        "success": True,
        "fts5": store.fts5_available(),
        "indexed": store.session_message_count(),
        "retentionDays": service.memory.policy.get("session_retention_days"),
        "historyEnabled": service.memory.policy.get("session_history_enabled"),
        "indexingEnabled": service.memory.policy.get("session_indexing_enabled"),
    }


@app.get("/session-search")
def session_search(
    q: str,
    scopeId: Optional[str] = None,
    scope: Optional[str] = None,
    runId: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search indexed session history. Historical content is context, not
    current financial evidence."""
    if not service.memory.policy.get("session_history_enabled"):
        raise HTTPException(status_code=403, detail="session history is disabled by policy")
    result = service.store.search_session_messages(
        q,
        user_id=None if scope == "global" else scopeId,
        run_id=runId,
        date_from=dateFrom,
        date_to=dateTo,
        limit=limit,
    )
    return {"success": True, **result}


@app.get("/session-search/{run_id}")
def session_open(run_id: str) -> dict[str, Any]:
    """Open a bounded window of one indexed run's messages."""
    if not service.memory.policy.get("session_history_enabled"):
        raise HTTPException(status_code=403, detail="session history is disabled by policy")
    return {"success": True, **service.store.open_session(run_id)}


@app.post("/session-search/reindex")
def session_reindex(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Reindex one run or all runs into the session search index (operator)."""
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="reindex requires an authorized operator")
    from .session_index import index_run

    if payload.get("runId"):
        return {"success": True, **index_run(service.store, str(payload["runId"]))}
    indexed = 0
    runs = service.store.list_runs(limit=int(payload.get("limit", 200)))
    for run in runs:
        result = index_run(service.store, run["id"], user_id=run.get("userId"))
        indexed += int(result.get("indexed") or 0)
    return {"success": True, "runs": len(runs), "indexed": indexed}


@app.post("/session-search/delete/{run_id}")
def session_delete(
    run_id: str, payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Remove a run's indexed messages (privacy/delete control). The full run
    trace in agent-memory is untouched."""
    if not bool((payload or {}).get("operator")):
        raise HTTPException(status_code=403, detail="session delete requires an authorized operator")
    removed = service.store.delete_session_messages(run_id)
    return {"success": True, "runId": run_id, "removed": removed}


# ── Learning review (automatic, bounded, inert outcomes) ────────────────────


@app.get("/learning-review/health")
def learning_review_health() -> dict[str, Any]:
    """Queue + audit health. Nothing here enables a skill or writes memory."""
    return {"success": True, **service.learning_review.health()}


@app.get("/learning-review")
def list_learning_reviews(status: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
    return {
        "success": True,
        "reviews": service.store.list_learning_reviews(status=status, limit=limit),
    }


@app.get("/learning-review/{review_id}")
def get_learning_review(review_id: str) -> dict[str, Any]:
    review = service.store.get_learning_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return {"success": True, "review": review}


@app.post("/learning-review/run")
def run_learning_review(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Run a review for ONE run synchronously (operator-triggered).

    Deterministic by default; `model: true` adds the optional bounded model
    review. Outcomes are inert — durable writes still pass the decision gate and
    an operator decides in the UI.
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="review requires an authorized operator")
    run_id = str(payload.get("runId") or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="runId is required")
    from .learning_review import review_run

    model_settings = None
    if bool(payload.get("model")):
        # Reuse the run's own model settings — no second adapter.
        run = service.store.get_run(run_id) or {}
        try:
            from .schemas import ModelSettings  # noqa: PLC0415

            model_settings = ModelSettings(
                provider=run.get("provider") or "openai",
                model=run.get("model") or "gpt-4o-mini",
            )
        except Exception:  # noqa: BLE001 - fall back to deterministic only
            model_settings = None
    result = review_run(service.memory, service.store, run_id, model=model_settings is not None, model_settings=model_settings)
    record = service.store.save_learning_review({
        "runId": run_id, "status": "completed", "mode": result["mode"],
        "result": result, "createdAt": now_iso(),
    })
    result["reviewId"] = record["id"]
    service.store.update_learning_review(record["id"], result=result)
    return {"success": True, "review": service.store.get_learning_review(record["id"])}


@app.post("/learning-review/decide")
def decide_learning_review(
    payload: dict[str, Any] | None = None, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Accept or reject one review outcome (operator only).

    Accepting a durable-memory outcome writes through the ONE decision gate with
    `run_analysis` provenance — no background path can bypass it. Accepting a
    skill outcome remains inert (it is still never enabled automatically).
    """
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="review decision requires an authorized operator")
    review_id = str(payload.get("reviewId") or "").strip()
    action = str(payload.get("action") or "").strip()
    if action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be accept or reject")
    review = service.store.get_learning_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    result = review.get("result") or {}
    outcomes = result.get("outcomes") or []
    index = int(payload.get("outcomeIndex") or 0)
    if index < 0 or index >= len(outcomes):
        raise HTTPException(status_code=400, detail="outcomeIndex out of range")
    outcome = outcomes[index]
    outcome["decided"] = action
    if action == "accept" and outcome.get("category") in ("durable_memory_proposal", "memory_suggestion"):
        content = (outcome.get("payload") or {}).get("content")
        if content:
            from .eclipse_memory.decision import authorize_proposal

            decision = authorize_proposal(
                content=content, provenance="run_analysis",
                memory_type=(outcome.get("payload") or {}).get("memoryType", "semantic"),
                settings=service.memory.policy.get_all(),
                user_id=payload.get("userId"),
            )
            outcome = service.memory.commit_decision(decision, user_id=payload.get("userId"))
            outcome["category"] = "durable_memory_proposal"
    service.store.update_learning_review(review_id, result={**result, "outcomes": outcomes})
    return {"success": True, "action": action, "outcome": outcome}


# ── Export / import / backup / health / reset (local operator control) ───────
@app.get("/eclipse-memory/export")
def export_memory(include_inactive: bool = True) -> dict[str, Any]:
    """A readable, versioned JSON export of the memory domain (read-only)."""
    from .eclipse_memory.transfer import export_payload

    return {"success": True, **export_payload(service.memory_store, include_inactive=include_inactive)}


@app.post("/eclipse-memory/import")
def import_memory(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Validate + import an export document through the normal write pipeline.

    Requires operator authorization. Each record is written via `write_memory`
    (privacy/type/scope/conflict/duplicate rules apply) with `imported`
    provenance, so an import can never bypass the safety gates.
    """
    from .eclipse_memory.transfer import import_payload

    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory import requires an authorized operator")
    document = payload.get("document")
    if document is None:
        # Allow the export body itself to be posted directly.
        document = payload
    try:
        report = import_payload(
            service.memory, document,
            source=str(payload.get("source") or "imported"),
            dry_run=bool(payload.get("dryRun")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **report}


@app.post("/eclipse-memory/backup")
def backup_memory(payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from .eclipse_memory.transfer import create_backup

    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory backup requires an authorized operator")
    try:
        result = create_backup(service.memory_store, payload.get("path"))
    except (FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.get("/eclipse-memory/database-health")
def memory_database_health() -> dict[str, Any]:
    from .eclipse_memory.transfer import database_health

    return {"success": True, **database_health(service.memory_store)}


@app.post("/eclipse-memory/reset")
def reset_memory_endpoint(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Reset the memory domain only. Requires explicit confirmation; backs up
    first by default; never touches skills or unrelated application data."""
    from .eclipse_memory.transfer import reset_memory as _reset

    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="memory reset requires an authorized operator")
    if payload.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="reset requires an explicit confirm=true")
    try:
        result = _reset(
            service.memory_store,
            confirm=True,
            backup_first=payload.get("backupFirst", True) is not False,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


# ── Memory suggestions (inert, non-recalled Save/Dismiss proposals) ──────────
# A suggestion is NOT a memory: it is never injected into a run. Accepting it
# writes exactly one scoped memory through the shared gate; dismissing it keeps
# a record so the same suggestion is not re-offered.


@app.get("/eclipse-memory/suggestions")
def list_suggestions(
    status: Optional[str] = "pending", scopeId: Optional[str] = None, limit: int = 100,
) -> dict[str, Any]:
    """Inert Save/Dismiss proposals.

    `scopeId` narrows the list to one user scope (plus unscoped suggestions), so
    a caller can request only their own. This app has no account system, so the
    filter is caller-supplied by design; the authoritative cross-user guard is
    the mismatch refusal in accept/dismiss below.
    """
    return {
        "success": True,
        "suggestions": service.memory_store.list_suggestions(
            status=status, scope_id=scopeId, limit=limit,
        ),
    }


@app.post("/eclipse-memory/suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="accepting a suggestion requires an authorized operator")
    result = service.memory.accept_suggestion(suggestion_id, user_id=payload.get("userId"))
    if result.get("action") == "not_found":
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if result.get("action") == "forbidden":
        raise HTTPException(status_code=403, detail=result.get("reason") or "suggestion scope denied")
    return {"success": bool(result.get("ok")), **result}


@app.post("/eclipse-memory/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="dismissing a suggestion requires an authorized operator")
    result = service.memory.dismiss_suggestion(suggestion_id, user_id=payload.get("userId"))
    if result.get("action") == "not_found":
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if result.get("action") == "forbidden":
        raise HTTPException(status_code=403, detail=result.get("reason") or "suggestion scope denied")
    return {"success": bool(result.get("ok")), **result}


@app.get("/skills/authoring/tools")
def authorable_tools() -> dict[str, Any]:
    """Tools a user skill may require, with the safe permission vocabulary."""
    from .skills.permissions import SAFE_PERMISSIONS

    return {
        "success": True,
        "tools": service.registry.names(),
        "permissions": sorted(SAFE_PERMISSIONS),
        "categories": ["research", "quality", "finance", "system"],
        "riskLevels": ["low", "medium"],
    }


@app.post("/skills/author")
def create_user_skill(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Create a user-authored skill (operator-gated)."""
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="skill.create requires an authorized operator")
    from .skills.authoring import SkillAuthoringError

    try:
        result = service.skill_registry.create_user_skill(
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            instructions=str(payload.get("instructions") or ""),
            category=str(payload.get("category") or "research"),
            tags=payload.get("tags"),
            required_tools=payload.get("requiredTools"),
            permissions=payload.get("permissions"),
            risk_level=str(payload.get("riskLevel") or "low"),
            skill_id=payload.get("skillId"),
        )
    except SkillAuthoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.put("/skills/{skill_id}/author")
def update_user_skill(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="skill.create requires an authorized operator")
    from .skills.authoring import SkillAuthoringError

    try:
        result = service.skill_registry.update_user_skill(skill_id, **payload)
    except SkillAuthoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.delete("/skills/{skill_id}/author")
def delete_user_skill(skill_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="skill.create requires an authorized operator")
    from .skills.authoring import SkillAuthoringError

    try:
        result = service.skill_registry.delete_user_skill(skill_id)
    except SkillAuthoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.post("/skills/discover")
def discover_skills(payload: dict[str, Any]) -> dict[str, Any]:
    results = service.skill_registry.discover(
        query=str(payload.get("query") or ""),
        category=payload.get("category"),
        tags=payload.get("tags"),
        status=payload.get("status"),
        risk_level=payload.get("riskLevel"),
        include_non_executable=bool(payload.get("includeNonExecutable")),
    )
    return {"success": True, "results": results}


@app.post("/skills/validate-input")
def validate_skill_input(payload: dict[str, Any]) -> dict[str, Any]:
    from .skills.runtime import validate_input

    skill_id = str(payload.get("skillId") or "")
    manifest = service.skill_registry.manifest(skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    ok, issues = validate_input(manifest.inputSchema, payload.get("input") or {}, skill_id)
    return {"success": True, "valid": ok, "issues": issues}


@app.post("/skills/{skill_id}/execute")
async def execute_skill_endpoint(
    skill_id: str, payload: dict[str, Any], request: Request,
) -> JSONResponse:
    # Execution is a legitimate NON-operator action (an enabled read-only skill),
    # so this endpoint is not blanket operator-gated. But the body `operator`
    # flag widens the actor to the operator permission set, so it may only be
    # honoured when authorization is PROVEN by transport/token — never by the
    # body alone. A remote caller that sends `{"operator": true}` without proof
    # is downgraded to the safe read-only actor.
    proven = _is_loopback(request) or _valid_operator_token(request)
    body = {**payload, "skillId": skill_id, "operator": bool(payload.get("operator")) and proven}
    execution = SkillExecutionRequest(**body)
    result = await service.run_skill(execution)
    return JSONResponse({"success": True, **result.model_dump()})


@app.get("/skill-executions")
def list_skill_executions(skillId: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    return {"success": True, "executions": service.skill_store.list_executions(skillId, limit)}


@app.get("/skill-executions/{run_id}")
def get_skill_execution(run_id: str) -> dict[str, Any]:
    execution = service.skill_store.get_execution(run_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Skill execution not found")
    return {"success": True, "execution": execution}


@app.post("/skill-executions/{run_id}/cancel")
def cancel_skill_execution(run_id: str) -> dict[str, Any]:
    cancelled = service.cancel(run_id)
    return {"success": True, "runId": run_id, "cancelled": cancelled}


@app.post("/skills/{skill_id}/evaluate")
def evaluate_skill_endpoint(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = evaluate_skill(
        skill_id, payload.get("version"), service.skill_registry,
        run_regression=bool(payload.get("runRegression")),
    )
    return {"success": result.get("ok", False), **result}


@app.get("/skills/{skill_id}/evaluations")
def list_skill_evaluations(skill_id: str) -> dict[str, Any]:
    if service.skill_registry.manifest(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"success": True, "evaluations": service.skill_store.list_evaluations(skill_id, 50)}


@app.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str) -> dict[str, Any]:
    evaluation = service.skill_store.get_evaluation(evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return {"success": True, "evaluation": evaluation}


@app.post("/skills/{skill_id}/enable")
def enable_skill(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = service.skill_registry.set_status(
        skill_id, "enabled", _actor(bool(payload.get("operator"))), payload.get("version")
    )
    return {"success": result.get("ok", False), **result}


@app.post("/skills/{skill_id}/disable")
def disable_skill(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = service.skill_registry.set_status(
        skill_id, "disabled", _actor(bool(payload.get("operator"))), payload.get("version")
    )
    return {"success": result.get("ok", False), **result}


@app.post("/skills/{skill_id}/deprecate")
def deprecate_skill(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = service.skill_registry.deprecate(
        skill_id, _actor(bool(payload.get("operator"))),
        reason=str(payload.get("reason") or "deprecated"),
        superseded_by=payload.get("supersededBy"),
    )
    return {"success": result.get("ok", False), **result}


@app.post("/skills/{skill_id}/rollback")
def rollback_skill(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = rollback(
        service.skill_registry, skill_id=skill_id,
        to_version=str(payload.get("version") or ""),
        actor=_actor(bool(payload.get("operator"))),
        reason=str(payload.get("reason") or "rollback"),
    )
    return {"success": result.get("ok", False), **result}


@app.get("/learning/candidates")
def list_candidates(status: Optional[str] = None) -> dict[str, Any]:
    return {"success": True, "candidates": service.skill_store.list_candidates(status, 100)}


@app.get("/learning/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> dict[str, Any]:
    candidate = service.skill_store.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"success": True, "candidate": candidate}


@app.post("/learning/from-run/{run_id}")
def learn_from_run(run_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    result = capture_from_run(
        run_id, service.store, service.skill_store,
        actor_is_operator=bool(payload.get("operator")),
        user_intent=str(payload.get("userIntent") or ""),
    )
    return {"success": result.get("ok", False), **result}


@app.get("/learning/eligibility/{run_id}")
def learning_eligibility(run_id: str) -> dict[str, Any]:
    """Why a run is (or is not) a learning candidate — read-only, no creation.

    Surfaces the same deterministic eligibility logic the runtime records on the
    run, so the chat UI can show the reason and link to the Learning Queue.
    """
    from .graph import learning_eligibility_for_run

    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True, **learning_eligibility_for_run(run_id, service.store)}


@app.post("/learning/candidates/{candidate_id}/generate-draft")
def generate_draft(candidate_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="skill.create requires an authorized operator")
    result = propose_draft(
        candidate_id, service.skill_store, available_tools=service.registry.names(),
        user_intent=payload.get("userIntent"),
    )
    return {"success": result.get("ok", False), **result}


@app.post("/learning/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, payload: Optional[dict[str, Any]] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload = payload or {}
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="skill.review requires an authorized operator")
    candidate = service.skill_store.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    service.skill_store.update_candidate(candidate_id, status="rejected", reviewedAt=now_iso())
    return {"success": True, "candidateId": candidate_id, "status": "rejected"}


@app.post("/skill-drafts/{skill_id}/submit-review")
def submit_draft_review(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = request_promotion(
        service.skill_registry, skill_id=skill_id, version=payload.get("version"),
        actor=_actor(bool(payload.get("operator"))), reason=str(payload.get("reason") or "submit for review"),
        evaluation_id=payload.get("evaluationId"),
    )
    return {"success": result.get("ok", False), **result}


# ── Skill quality / usefulness evidence (Phase 7) ────────────────────────────
# Measured from real execution records. Advisory only; promotion stays
# evaluation- and operator-gated.


@app.get("/skills/{skill_id}/quality")
def skill_quality(skill_id: str, version: Optional[str] = None, limit: int = 200) -> dict[str, Any]:
    from .eclipse_memory.skill_quality import skill_quality_metrics

    return {"success": True, **skill_quality_metrics(service.skill_store, skill_id, version=version, limit=limit)}


@app.get("/skills/{skill_id}/promotion-evidence")
def skill_promotion_evidence(skill_id: str, version: str) -> dict[str, Any]:
    from .eclipse_memory.skill_quality import promotion_evidence

    return {"success": True, **promotion_evidence(service.skill_store, skill_id, version)}


@app.get("/skills/{skill_id}/quality/compare")
def skill_quality_compare(skill_id: str, older: str, newer: str) -> dict[str, Any]:
    from .eclipse_memory.skill_quality import compare_versions

    return {"success": True, **compare_versions(service.skill_store, skill_id, older, newer)}


@app.post("/skill-drafts/{skill_id}/approve")
def approve_draft(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    request_id = str(payload.get("requestId") or "")
    if not request_id:
        # Resolve the newest pending request for this skill (the UI holds only
        # the skill id after submit-review).
        pending = [
            r for r in service.skill_store.list_promotion_requests(skill_id, 50)
            if r["status"] == "pending"
        ]
        if not pending:
            raise HTTPException(status_code=409, detail="no pending promotion request for this skill")
        request_id = pending[0]["id"]
    result = approve_promotion(
        service.skill_registry, request_id=request_id,
        actor=_actor(bool(payload.get("operator"))), notes=str(payload.get("notes") or ""),
    )
    return {"success": result.get("ok", False), **result}


@app.post("/skill-drafts/{skill_id}/reject")
def reject_draft(skill_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    request_id = str(payload.get("requestId") or "")
    if not request_id:
        pending = [
            r for r in service.skill_store.list_promotion_requests(skill_id, 50)
            if r["status"] == "pending"
        ]
        if pending:
            request_id = pending[0]["id"]
    if request_id:
        result = reject_promotion(
            service.skill_registry, request_id=request_id,
            actor=_actor(bool(payload.get("operator"))), reason=str(payload.get("reason") or "rejected"),
        )
        return {"success": result.get("ok", False), **result}
    # No promotion request yet: reject the draft outright.
    if not bool(payload.get("operator")):
        raise HTTPException(status_code=403, detail="skill.review requires an authorized operator")
    manifest = service.skill_registry.manifest(skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    target = service.skill_registry.resolve_version(skill_id) or manifest.version
    service.skill_registry.store.set_version_status(skill_id, target, "rejected")
    service.skill_registry.store.save_review(
        skill_id=skill_id, version=target, actor="operator", decision="rejected",
        notes=str(payload.get("reason") or "rejected"),
    )
    return {"success": True, "skillId": skill_id, "version": target, "status": "rejected"}


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
