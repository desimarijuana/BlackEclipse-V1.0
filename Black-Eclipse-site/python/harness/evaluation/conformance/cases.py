"""C8 conformance cases: fault matrix, golden traces, contract checks.

Each case returns a `CaseResult`; the runner owns ordering, JSON output and exit
codes. Cases are deliberately small and deterministic — the point is a runnable
gate that names the failing invariant, not another test framework.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ...observability.config import ObservabilityConfig
from ...observability.core import ObservabilityHub
from ...observability.events import HOOKS
from ...observability.integration import RunEventProjector
from ...observability.probe import run_probe
from ...retry_policy import RetryPolicy, RunDeadline, is_retryable, retry_async


@dataclass
class CaseResult:
    id: str
    kind: str
    ok: bool
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "ok": self.ok,
            "detail": self.detail, "evidence": self.evidence,
        }


class Fault(Exception):
    def __init__(self, status: int | None = None, message: str = "") -> None:
        super().__init__(message or f"fault {status}")
        if status is not None:
            self.status_code = status


async def _retry_count(exc_factory: Callable[[int], BaseException], *, attempts: int = 3) -> int:
    calls = {"n": 0}

    async def call() -> str:
        calls["n"] += 1
        if calls["n"] < attempts:
            raise exc_factory(calls["n"])
        return "ok"

    policy = RetryPolicy(attempts=attempts, base_delay_s=0.0, max_delay_s=0.0, jitter=False)
    result = await retry_async(call, policy)
    return calls["n"] if result == "ok" else -1


def _connect_error() -> BaseException:
    try:
        import httpx  # noqa: PLC0415
        return httpx.ConnectError("connection reset")
    except Exception:  # noqa: BLE001
        return ConnectionResetError("connection reset")


def fault_retry_429() -> CaseResult:
    calls = asyncio.run(_retry_count(lambda n: Fault(429, "rate limited")))
    return CaseResult("fault.retry_429", "fault", calls == 3,
                      f"429 retried to success in {calls} calls", {"calls": calls})


def fault_retry_500() -> CaseResult:
    calls = asyncio.run(_retry_count(lambda n: Fault(500, "server error")))
    return CaseResult("fault.retry_500", "fault", calls == 3,
                      f"500 retried to success in {calls} calls", {"calls": calls})


def fault_retry_disconnect() -> CaseResult:
    calls = asyncio.run(_retry_count(lambda n: _connect_error()))
    return CaseResult("fault.retry_disconnect", "fault", calls == 3,
                      f"disconnect retried to success in {calls} calls", {"calls": calls})


def fault_no_retry_400() -> CaseResult:
    calls = {"n": 0}

    async def call() -> str:
        calls["n"] += 1
        raise Fault(400, "bad request")

    try:
        asyncio.run(retry_async(call, RetryPolicy(attempts=3, base_delay_s=0.0, jitter=False)))
    except Fault:
        pass
    return CaseResult("fault.no_retry_400", "fault", calls["n"] == 1,
                      f"400 attempted {calls['n']} time(s)", {"calls": calls["n"]})


def fault_no_retry_cancel() -> CaseResult:
    calls = {"n": 0}

    async def call() -> str:
        calls["n"] += 1
        raise asyncio.CancelledError()

    cancelled = False
    try:
        asyncio.run(retry_async(call, RetryPolicy(attempts=3, base_delay_s=0.0, jitter=False)))
    except asyncio.CancelledError:
        cancelled = True
    ok = cancelled and calls["n"] == 1 and not is_retryable(asyncio.CancelledError())
    return CaseResult("fault.no_retry_cancel", "fault", ok,
                      "cancellation is never retried", {"calls": calls["n"]})


def fault_deadline_blocks_retry() -> CaseResult:
    calls = {"n": 0}

    async def call() -> str:
        calls["n"] += 1
        raise Fault(429, "rate limited")

    deadline = RunDeadline(0)
    try:
        asyncio.run(retry_async(
            call, RetryPolicy(attempts=3, base_delay_s=0.0, jitter=False), deadline=deadline,
        ))
    except Fault:
        pass
    ok = calls["n"] == 1 and deadline.expired()
    return CaseResult("fault.deadline_blocks_retry", "fault", ok,
                      "an expired run deadline refuses a retry", {"calls": calls["n"]})


def fault_duplicate_effect() -> CaseResult:
    import tempfile
    import os

    from ...persistence import AgentMemoryStore
    from ...run_effects import RunEffects

    directory = tempfile.mkdtemp(prefix="be-conflict-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        effects = RunEffects(store)
        effects.begin("r", 1, "c1", "order_submit", "external_action")
        effects.begin("r", 1, "c1", "order_submit", "external_action")
        first = effects.state("r", 1, "c1")
        effects.finish("r", 1, "c1", ok=True)
        done = effects.state("r", 1, "c1")
        ok = first == "started" and done == "done"
        return CaseResult("fault.duplicate_effect", "fault", ok,
                          "a second begin is idempotent; finish records done",
                          {"first": first, "done": done})
    finally:
        store.close()


# ── process-level kill matrix ────────────────────────────────────────────────
_PYTHON_DIR = Path(__file__).resolve().parents[3]
_WORKER = Path(__file__).resolve().parent / "crash_worker.py"


def _crash_matrix(mode: str) -> CaseResult:
    from ...persistence import AgentMemoryStore
    from ...run_effects import RunEffects

    directory = Path(tempfile.mkdtemp(prefix=f"be-crash-{mode}-"))
    db_path = directory / "agent-memory.db"
    effect_log = directory / "effects.log"
    launcher = (
        f"import sys, runpy; sys.path.insert(0, {str(_PYTHON_DIR)!r}); "
        f"sys.argv = [{str(_WORKER)!r}, {str(db_path)!r}, {str(effect_log)!r}, {mode!r}]; "
        f"runpy.run_path({str(_WORKER)!r}, run_name='__main__')"
    )
    crashed = subprocess.run([sys.executable, "-c", launcher], capture_output=True,
                             text=True, timeout=60)
    store = AgentMemoryStore(str(db_path))
    try:
        effects = RunEffects(store)
        prior = effects.state("crash_run", 1, "c1")
        executed = False
        final = prior
        if prior == "started":
            effects.mark_unknown("crash_run", 1, "c1")
            final = "unknown"
        elif prior == "done":
            final = "done"
        else:
            effects.begin("crash_run", 1, "c1", "order_submit", "external_action")
            with open(effect_log, "a", encoding="utf-8") as handle:
                handle.write("effect\n")
            effects.finish("crash_run", 1, "c1", ok=True)
            final = "done"
            executed = True
    finally:
        store.close()
    effects_count = len(effect_log.read_text(encoding="utf-8").splitlines()) if effect_log.exists() else 0

    expected = {
        "before_begin": {"prior": None, "final": "done", "executed": True, "count": 1},
        "after_begin": {"prior": "started", "final": "unknown", "executed": False, "count": 0},
        "after_effect": {"prior": "started", "final": "unknown", "executed": False, "count": 1},
        "after_finish": {"prior": "done", "final": "done", "executed": False, "count": 1},
    }[mode]
    ok = (
        crashed.returncode == (0 if mode == "after_finish" else 9)
        and prior == expected["prior"]
        and final == expected["final"]
        and executed is expected["executed"]
        and effects_count == expected["count"]
    )
    return CaseResult(
        f"fault.crash_{mode}", "fault", ok,
        f"kill {mode}: prior={prior!r} final={final!r} executed={executed} effects={effects_count}",
        {"mode": mode, "returncode": crashed.returncode, "prior": prior,
         "final": final, "executed": executed, "effects": effects_count},
    )


def fault_crash_before_begin() -> CaseResult:
    return _crash_matrix("before_begin")


def fault_crash_after_begin() -> CaseResult:
    return _crash_matrix("after_begin")


def fault_crash_after_effect() -> CaseResult:
    return _crash_matrix("after_effect")


def fault_crash_after_finish() -> CaseResult:
    return _crash_matrix("after_finish")


# ── golden trace ─────────────────────────────────────────────────────────────
def _golden_hub() -> ObservabilityHub:
    return ObservabilityHub(
        ObservabilityConfig(jsonl_dir="", otel_enabled=False, langfuse_enabled=False, sentry_enabled=False),
        capture_inmemory=False, start_exporters=False,
    )


def golden_run_step_tool() -> CaseResult:
    hub = _golden_hub()
    projector = RunEventProjector(hub)
    base = 1000.0
    events = [
        {"type": "run.created", "runId": "g1", "at": base, "data": {"agentId": "a"}},
        {"type": "step.started", "runId": "g1", "at": base, "data": {"step": 1, "stepId": "g1:step:1"}},
        {"type": "model.requested", "runId": "g1", "at": base + 0.01, "data": {"step": 1}},
        {"type": "model.request.started", "runId": "g1", "at": base + 0.01,
         "data": {"step": 1, "provider": "p", "model": "m"}},
        {"type": "tool.requested", "runId": "g1", "at": base + 0.02,
         "data": {"name": "t", "toolCallId": "c1", "step": 1}},
        {"type": "tool.completed", "runId": "g1", "at": base + 0.03,
         "data": {"name": "t", "toolCallId": "c1", "step": 1, "durationMs": 1}},
        {"type": "model.completed", "runId": "g1", "at": base + 0.03,
         "data": {"step": 1, "promptTokens": 1, "completionTokens": 1, "totalTokens": 2}},
        {"type": "step.completed", "runId": "g1", "at": base + 0.04,
         "data": {"step": 1, "status": "ok", "toolCalls": 1}},
        {"type": "run.completed", "runId": "g1", "at": base + 0.05, "data": {"steps": 1}},
    ]
    for event in events:
        projector.handle(event)
    trace = hub.get_trace(hub.recent_traces(1)[0])
    by_name = {span["name"]: span for span in trace}
    run = by_name.get("eclipse.run")
    step = by_name.get("eclipse.step")
    tool = by_name.get("eclipse.tool.t")
    llm = by_name.get("eclipse.llm")
    ok = bool(run and step and tool and llm)
    parent_ok = ok and step["parentSpanId"] == run["spanId"] and \
        tool["parentSpanId"] == step["spanId"] and llm["parentSpanId"] == step["spanId"]
    terminal_ok = ok and run.get("status") == "OK" and step.get("attributes", {}).get("status") == "ok"
    expected = {
        "spans": sorted(by_name), "parentage": bool(parent_ok), "terminal": bool(terminal_ok),
    }
    return CaseResult("golden.run_step_tool", "golden", bool(parent_ok and terminal_ok),
                      "run->step->tool/llm tree and terminal state", expected)


# ── contract checks ─────────────────────────────────────────────────────────
def contract_event_vocabulary() -> CaseResult:
    required = {"onRunStart", "onRunEnd", "onStepStart", "onStepEnd",
                "onToolStart", "onToolEnd", "onError"}
    missing = sorted(required - HOOKS)
    ok = not missing and all(hook.startswith("on") for hook in HOOKS)
    return CaseResult("contract.event_vocabulary", "contract", ok,
                      "closed hook vocabulary includes the step hooks",
                      {"hooks": len(HOOKS), "missing": missing})


def contract_tool_manifest() -> CaseResult:
    from ...public import TOOL_MANIFEST_VERSION, tool_manifest

    manifest = tool_manifest()
    digest = str(manifest.get("digest") or "")
    tools = manifest.get("tools") or []
    bad = [
        tool.get("name") for tool in tools
        if not tool.get("permission") or (tool.get("permission") != "read" and not tool.get("effect"))
    ]
    ok = (
        manifest.get("manifestVersion") == TOOL_MANIFEST_VERSION
        and len(digest) == 16
        and bool(tools)
        and not bad
    )
    return CaseResult("contract.tool_manifest", "contract", ok,
                      "portable tool manifest is versioned, digested and honest",
                      {"version": manifest.get("manifestVersion"), "tools": len(tools),
                       "digest": digest, "unclassified": bad[:5]})


def contract_slo_report() -> CaseResult:
    report = run_probe(runs=6)
    runs = report.get("runs") or {}
    required = {"created", "terminal", "orphaned"}
    ok = (
        required <= set(runs)
        and isinstance(report.get("latency"), dict)
        and isinstance(report.get("cost"), dict)
        and isinstance(report.get("slos"), dict)
    )
    return CaseResult("contract.slo_report", "contract", ok,
                      "release report carries runs/latency/cost/slos",
                      {"keys": sorted(report)})


def contract_plugin_sdk() -> CaseResult:
    from ...plugins.manifest import SDK_VERSION

    ok = bool(SDK_VERSION) and isinstance(SDK_VERSION, str)
    return CaseResult("contract.plugin_sdk", "contract", ok,
                      "plugin SDK declares a version", {"sdkVersion": SDK_VERSION})


CASES: tuple[Callable[[], CaseResult], ...] = (
    fault_retry_429,
    fault_retry_500,
    fault_retry_disconnect,
    fault_no_retry_400,
    fault_no_retry_cancel,
    fault_deadline_blocks_retry,
    fault_duplicate_effect,
    fault_crash_before_begin,
    fault_crash_after_begin,
    fault_crash_after_effect,
    fault_crash_after_finish,
    golden_run_step_tool,
    contract_event_vocabulary,
    contract_tool_manifest,
    contract_slo_report,
    contract_plugin_sdk,
)


__all__ = ["CASES", "CaseResult"]
