"""C8 conformance cases: fault matrix, golden traces, contract checks.

Each case returns a `CaseResult`; the runner owns ordering, JSON output and exit
codes. Cases are deliberately small and deterministic — the point is a runnable
gate that names the failing invariant, not another test framework.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
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
from ...observability.probe import probe_metric_names, run_probe
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


# ── W8 signal contract ──────────────────────────────────────────────────────
_W8_CAPABILITIES = {
    "modelGateway": True, "contextLadder": True, "parallelTools": True,
    "autonomy": True, "learningEval": True, "runKernelIntegrity": True,
    "fileCheckpoints": True, "asyncDelegation": True,
}


def _w8_hub():
    hub = ObservabilityHub(
        ObservabilityConfig(jsonl_dir="", otel_enabled=False, langfuse_enabled=False, sentry_enabled=False),
        capture_inmemory=False, start_exporters=False,
    )
    return hub, RunEventProjector(hub)


def _w8_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    hub, projector = _w8_hub()
    for event in events:
        projector.handle(event)
    return hub.release_report(capabilities_override=_W8_CAPABILITIES)


def signal_model_attempt() -> CaseResult:
    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "model.candidate_plan", "runId": "r1", "at": 1.1,
         "data": {"candidates": [{"provider": "a", "model": "m"}], "excluded": [], "fallbackDepth": 1}},
        {"type": "model.attempt.completed", "runId": "r1", "at": 1.2,
         "data": {"outcome": "completed", "latencyMs": 10, "ttftMs": 4, "priced": True}},
        {"type": "model.attempt.failed", "runId": "r1", "at": 1.3,
         "data": {"outcome": "failed", "errorClass": "SERVER_ERROR", "willFallback": True}},
        {"type": "model.fallback", "runId": "r1", "at": 1.4, "data": {"attempts": 2}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ])
    model = report["model"]
    ok = (
        model["attempts"] == 2 and model["fallbacks"] == 1
        and model["fallbackSuccessRate"] == 1.0
        and report["latency"]["ttft"]["samples"] == 1
    )
    return CaseResult("signal.model_attempt", "signal", ok,
                      "attempts, fallback numerator and TTFT reach the report",
                      {"model": model, "ttft": report["latency"]["ttft"]})


def signal_model_ttft() -> CaseResult:
    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "model.requested", "runId": "r1", "at": 1.1, "data": {"step": 1}},
        {"type": "model.first_token", "runId": "r1", "at": 1.2, "data": {"ttftMs": 123}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ])
    ttft = report["latency"]["ttft"]
    ok = ttft["samples"] == 1 and ttft["p95"] == 123.0
    return CaseResult("signal.model_ttft", "signal", ok,
                      "first token becomes a TTFT observation, not a generic event",
                      {"ttft": ttft})


def signal_context_compression() -> CaseResult:
    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "memory.history_bounded", "runId": "r1", "at": 1.1,
         "data": {"window": 200000, "windowKnown": True, "usageRatio": 0.42, "gate": "continue"}},
        {"type": "context.compressed", "runId": "r1", "at": 1.2,
         "data": {"stage": "summary", "ok": True, "usedModel": True}},
        {"type": "context.compressed", "runId": "r1", "at": 1.3,
         "data": {"stage": "skeleton", "ok": False, "reason": "timeout"}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ])
    context = report["context"]
    ok = (
        context["usageRatio"]["samples"] == 1
        and context["compactions"]["samples"] == 2
        and context["compactions"]["failures"] == 1
        and context["compactions"]["failureRate"] == 0.5
    )
    return CaseResult("signal.context_compression", "signal", ok,
                      "pressure, summary and skeleton outcomes are distinguishable",
                      {"context": context})


def signal_tool_batch() -> CaseResult:
    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "tool.batch_plan", "runId": "r1", "at": 1.1,
         "data": {"calls": 2, "batches": [[0, 1]], "parallelSafe": [True, True]}},
        {"type": "tool.batch", "runId": "r1", "at": 1.2,
         "data": {"calls": 2, "batches": 1, "maxConcurrency": 2,
                  "orderingViolations": 0, "durationMs": 40}},
        {"type": "tool.guardrail", "runId": "r1", "at": 1.3,
         "data": {"rule": "identical_call", "count": 3, "action": "warn"}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ])
    batches = report["tools"]["batches"]
    guardrails = report["tools"]["guardrails"]
    report["integrity"]["toolBatchOrderingViolations"] = 1
    from ...observability.gate import evaluate_gate

    injected = evaluate_gate(report, {"checks": [{
        "name": "ordering", "path": "integrity.toolBatchOrderingViolations",
        "kind": "invariant", "max": 0, "requires": "parallelTools",
    }]})
    ok = (
        batches["count"] == 1 and batches["orderingViolations"] == 0
        and guardrails["warn"] == 1 and injected.ok is False
    )
    return CaseResult("signal.tool_batch", "signal", ok,
                      "batch size, concurrency and guardrail outcome are recorded; "
                      "an injected ordering violation fails the gate",
                      {"batches": batches, "guardrails": guardrails, "gate": injected.to_dict()})


def signal_integrity_unknown_effect() -> CaseResult:
    from ...observability.gate import evaluate_gate

    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "effect.unknown", "runId": "r1", "at": 1.1,
         "data": {"name": "broker_order", "reason": "outcome_unknown"}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ])
    gate = evaluate_gate(report, {"checks": [{
        "name": "effect_unknown", "path": "integrity.effectUnknown",
        "kind": "invariant", "max": 0, "requires": "runKernelIntegrity",
    }]})
    ok = report["integrity"]["effectUnknown"] == 1 and gate.ok is False
    return CaseResult("signal.integrity_unknown_effect", "signal", ok,
                      "an unknown effect is counted and fails the invariant gate",
                      {"integrity": report["integrity"], "gate": gate.to_dict()})


def signal_integrity_lease_lost() -> CaseResult:
    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "run.lease_lost", "runId": "r1", "at": 1.1, "data": {"runtimeId": "other"}},
    ])
    ok = report["integrity"]["leaseLost"] == 1
    return CaseResult("signal.integrity_lease_lost", "signal", ok,
                      "a lost lease reaches the integrity section",
                      {"integrity": report["integrity"]})


def signal_file_checkpoint() -> CaseResult:
    report = _w8_report([
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "checkpoint.created", "runId": "r1", "at": 1.1,
         "data": {"op": "created", "files": 2, "bytes": 2048}},
        {"type": "checkpoint.failed", "runId": "r1", "at": 1.2,
         "data": {"op": "failed", "reason": "CHECKPOINT_STORE_FULL"}},
        {"type": "checkpoint.restored", "runId": "r1", "at": 1.3,
         "data": {"op": "restored", "restored": 2}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ])
    files = report["fileCheckpoints"]
    ok = (
        files["created"] == 1 and files["failed"] == 1 and files["restored"] == 1
        and files["failureRate"] == 0.5
    )
    return CaseResult("signal.file_checkpoint", "signal", ok,
                      "created, failed and restored are distinguishable",
                      {"fileCheckpoints": files})


def signal_goal_verdict() -> CaseResult:
    report = _w8_report([
        {"type": "goal.verdict", "at": 1.0, "data": {"verdict": "done", "turn": 1}},
        {"type": "goal.verdict", "at": 1.1, "data": {"verdict": "done", "turn": 2}},
        {"type": "goal.verdict", "at": 1.2, "data": {"verdict": "blocked", "turn": 3}},
    ])
    goals = report["goals"]
    ok = (
        goals["samples"] == 3 and goals["verdicts"]["done"] == 2
        and goals["completionRate"] == round(2 / 3, 6)
        and goals["blockedRate"] == round(1 / 3, 6)
    )
    return CaseResult("signal.goal_verdict", "signal", ok,
                      "verdicts roll up into completion and blocked rates",
                      {"goals": goals})


def signal_skill_evaluation() -> CaseResult:
    report = _w8_report([
        {"type": "skill.evaluation_completed", "at": 1.0,
         "data": {"ok": True, "status": "passed", "cases": 3}},
        {"type": "skill.evaluation_completed", "at": 1.1,
         "data": {"ok": False, "status": "needs_review", "cases": 0}},
    ])
    evals = report["learning"]["executionEvals"]
    ok = evals["total"] == 2 and evals["passed"] == 1 and evals["needsReview"] == 1
    return CaseResult("signal.skill_evaluation", "signal", ok,
                      "behavioural evaluation outcomes reach the learning section",
                      {"executionEvals": evals})


def contract_slo_report_v2() -> CaseResult:
    report = run_probe(runs=6)
    required = {"schema", "capabilities", "runs", "latency", "model", "context",
                "tools", "goals", "learning", "integrity", "slos"}
    objectives = (report.get("slos") or {}).get("objectives") or []
    ok = (
        required <= set(report)
        and report.get("schema") == 2
        and bool(report.get("capabilities"))
        and "unmeasured" in (report.get("slos") or {})
        and bool(objectives)
        and all("measured" in item for item in objectives)
    )
    return CaseResult("contract.slo_report_v2", "contract", ok,
                      "release report carries schema v2, capabilities and unmeasured objectives",
                      {"keys": sorted(report), "objectives": len(objectives)})


def contract_unmeasured_gate() -> CaseResult:
    from ...observability.gate import evaluate_gate

    hub, _ = _w8_hub()
    report = hub.release_report(capabilities_override=_W8_CAPABILITIES)
    required = evaluate_gate(report, {"checks": [{
        "name": "ttft_p95", "path": "latency.ttft.p95", "kind": "percentile",
        "thresholdMs": 15000, "samplesPath": "latency.ttft.samples",
        "minSamples": 50, "requireSamples": True,
    }]})
    optional = evaluate_gate(report, {"checks": [{
        "name": "ttft_p95", "path": "latency.ttft.p95", "kind": "percentile",
        "thresholdMs": 15000, "samplesPath": "latency.ttft.samples",
        "minSamples": 50, "requireSamples": False,
    }]})
    ok = (
        required.ok is False and required.checks[0].status == "unmeasured"
        and optional.ok is True and optional.checks[0].status == "skipped"
    )
    return CaseResult("contract.unmeasured_gate", "contract", ok,
                      "missing samples fail only when the check requires them",
                      {"required": required.to_dict(), "optional": optional.to_dict()})


def contract_alert_metric_names() -> CaseResult:
    rules_path = Path(__file__).resolve().parents[4] / "deploy" / "prometheus" / "blackeclipse.rules.yml"
    if not rules_path.exists():
        return CaseResult("contract.alert_metric_names", "contract", False,
                          "the shipped alert rules file is missing", {"path": str(rules_path)})
    text = rules_path.read_text(encoding="utf-8")
    referenced: set[str] = set()
    for match in re.findall(r"\beclipse_[a-zA-Z0-9_]+", text):
        base = re.sub(r"_(bucket|sum|count)$", "", match)
        referenced.add(base)
    available = probe_metric_names(runs=6)
    missing = sorted(referenced - available)
    ok = bool(referenced) and not missing
    return CaseResult("contract.alert_metric_names", "contract", ok,
                      "every alert metric exists in the shipped exposition",
                      {"referenced": sorted(referenced), "missing": missing})


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
    signal_model_attempt,
    signal_model_ttft,
    signal_context_compression,
    signal_tool_batch,
    signal_integrity_unknown_effect,
    signal_integrity_lease_lost,
    signal_file_checkpoint,
    signal_goal_verdict,
    signal_skill_evaluation,
    contract_slo_report_v2,
    contract_unmeasured_gate,
    contract_alert_metric_names,
)


__all__ = ["CASES", "CaseResult"]
