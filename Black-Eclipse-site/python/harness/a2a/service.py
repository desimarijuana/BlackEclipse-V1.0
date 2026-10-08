"""A2AService — the process facade over registry, bus, budgets and tasks.

One object ties the A2A layer together. It owns the Agent Registry (versioned
definitions), the durable Message Bus, per-run budgets, and the delegations that
create durable child TASKS. Execution itself is never done here: a delegated task
is dispatched by the EXISTING `TaskScheduler` through the ONE `service.run` plane.

Delegation is NON-BLOCKING by default — `delegate_task` returns a task handle
immediately and the scheduler runs it. `wait_agent`/`ask_agent` may await, but
they await an EVENT (the task's terminal bus event), never a poll or a sleep.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Optional

from ..persistence import now_iso
from . import permissions
from .agents_seed import default_agent_configs, default_definitions
from .budget import BudgetExceeded, BudgetTracker
from .bus import MessageBus
from .model import (
    AgentBudget,
    AgentDefinition,
    AgentEnvelope,
    AgentStatus,
    A2AResult,
    ApprovalStatus,
    DelegationRecord,
    DelegationStatus,
    Finding,
    MessagePriority,
    MessageType,
    MergedResult,
)
from .protocol import ProtocolError, make_envelope
from .registry import AgentRegistry, RegistryError
from .results import merge_results as _merge
from .store import A2AStore
from .supervisor import qa_checklist as _qa, review_results as _review

log = logging.getLogger("harness.a2a.service")

A2A_ERROR = "A2A_ERROR"
A2A_NO_AGENT = "A2A_NO_AGENT"
A2A_NO_CAPABLE_AGENT = "A2A_NO_CAPABLE_AGENT"
A2A_DELEGATION_REFUSED = "A2A_DELEGATION_REFUSED"
A2A_BUDGET_EXCEEDED = "A2A_BUDGET_EXCEEDED"
A2A_TASK_UNAVAILABLE = "A2A_TASK_UNAVAILABLE"
A2A_PERMISSION_DENIED = "A2A_PERMISSION_DENIED"
A2A_APPROVAL_REQUIRED = "A2A_APPROVAL_REQUIRED"

_PRIORITY_TO_TASK = {
    "LOW": "LOW", "NORMAL": "NORMAL", "HIGH": "HIGH", "URGENT": "URGENT", "CRITICAL": "CRITICAL",
}

_TERMINAL_EVENTS = {"task.completed", "task.failed", "task.cancelled"}


class A2AError(RuntimeError):
    """A structured A2A refusal. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.detail = detail or {}


def _hex(n: int = 16) -> str:
    return uuid.uuid4().hex[:n]


class A2AService:
    """Registry + bus + budgets + delegation, over a host providing a store/bus."""

    def __init__(self, host: Any, *, seed: bool = True) -> None:
        self._host = host
        self.store = A2AStore(host.store)
        self.registry = AgentRegistry(self.store, publisher=self._publish_event)
        self.bus = MessageBus(self.store, event_bus=getattr(host, "bus", None))
        self.budgets = BudgetTracker(self.store)
        self._waiters: dict[str, asyncio.Event] = {}
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._plan_cache: dict[str, str] = {}
        if seed:
            self.seed_defaults()
        self._subscribe()

    # ── seeding ────────────────────────────────────────────────────────────────

    def seed_defaults(self) -> None:
        for definition in default_definitions():
            try:
                self.registry.register_agent(definition)
            except (RegistryError, ValueError):
                continue
        self._install_agent_configs(default_agent_configs())

    def _install_agent_configs(self, configs: list[dict[str, Any]]) -> None:
        """Register AgentConfig presets so `service.run` can dispatch by agent id."""
        try:
            from ..agents import AGENT_PRESETS  # noqa: PLC0415
            from ..schemas import AgentConfig  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return
        for cfg in configs:
            if cfg["id"] in AGENT_PRESETS:
                continue
            try:
                AGENT_PRESETS[cfg["id"]] = AgentConfig(**cfg)
            except Exception:  # noqa: BLE001 - a bad preset must not block seeding
                log.warning("could not register agent preset %s", cfg.get("id"), exc_info=True)

    # ── live event bridge ───────────────────────────────────────────────────────

    def _subscribe(self) -> None:
        bus = getattr(self._host, "bus", None)
        if bus is None or not hasattr(bus, "subscribe"):
            return
        try:
            self._unsubscribe = bus.subscribe(self._on_event)
        except Exception:  # noqa: BLE001
            self._unsubscribe = None

    def _on_event(self, event: Any) -> None:
        if not isinstance(event, dict):
            return
        etype = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if etype in _TERMINAL_EVENTS:
            task_id = event.get("taskId") or data.get("taskId")
            if not task_id:
                inner = data.get("event") if isinstance(data.get("event"), dict) else {}
                task_id = inner.get("taskId") or (inner.get("data") or {}).get("taskId")
            if task_id:
                self._resolve(f"task:{task_id}")
        if etype in ("message.sent", "message.received"):
            corr = data.get("correlationId")
            mtype = data.get("type")
            if corr and mtype in (MessageType.ANSWER.value, MessageType.REVIEW_RESPONSE.value,
                                  MessageType.APPROVAL_RESPONSE.value):
                self._resolve(f"corr:{corr}")

    def _waiter(self, key: str) -> asyncio.Event:
        event = self._waiters.get(key)
        if event is None:
            event = asyncio.Event()
            self._waiters[key] = event
        return event

    def _resolve(self, key: str) -> None:
        event = self._waiters.pop(key, None)
        if event is not None:
            event.set()

    async def _wait(self, key: str, timeout_s: float) -> bool:
        event = self._waiter(key)
        if event.is_set():
            return True
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.1, timeout_s))
            return True
        except asyncio.TimeoutError:
            return False

    def _publish_event(self, event_type: str, data: dict[str, Any]) -> None:
        run_id = str(data.get("runId") or data.get("agentId") or "global")
        try:
            self.store.append_event(run_id, event_type, data)
        except Exception:  # noqa: BLE001
            pass

    async def _emit(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        self._publish_event(event_type, {"runId": run_id, **data})
        bus = getattr(self._host, "bus", None)
        if bus is not None:
            try:
                bus.publish({"type": event_type, "at": now_iso(), "data": {"runId": run_id, **data}})
            except Exception:  # noqa: BLE001
                pass

    # ── collaborators ───────────────────────────────────────────────────────────

    def _task_manager(self):
        manager = getattr(self._host, "tasks", None)
        if manager is not None:
            return manager
        from ..tasks.bootstrap import install_task_layer  # noqa: PLC0415

        install_task_layer(self._host)
        manager = getattr(self._host, "tasks", None)
        if manager is None:
            raise A2AError(A2A_TASK_UNAVAILABLE, "the task runtime is unavailable")
        return manager

    def _evidence_exists(self) -> Optional[Callable[[str], bool]]:
        evidence = getattr(self._host, "evidence_store", None)
        if evidence is None:
            return None
        db = getattr(evidence, "_store", None)
        db = getattr(db, "_db", None)
        if db is None:
            return None

        def exists(ref: str) -> bool:
            try:
                row = db.execute(
                    "SELECT 1 FROM WebResearchEvidence WHERE evidenceId=? LIMIT 1", (ref,)
                ).fetchone()
                return row is not None
            except Exception:  # noqa: BLE001
                return False

        return exists

    # ── registry-facing reads ────────────────────────────────────────────────────

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return self.registry.get_agent(agent_id).to_public()

    def list_agents(self, *, status: Optional[str] = None) -> list[dict[str, Any]]:
        return [d.to_public() for d in self.registry.list_agents(status=status)]

    def capability_index(self) -> dict[str, list[str]]:
        return self.registry.capability_index()

    def agent_status(self, agent_id: str) -> dict[str, Any]:
        definition = self.registry.get_agent(agent_id)
        delegations = self.store.list_delegations(parent_agent_id=agent_id, limit=200)
        active = [d for d in delegations if d.status in (DelegationStatus.CREATED, DelegationStatus.RUNNING)]
        return {
            "agentId": definition.id, "status": definition.status.value,
            "capabilities": definition.capabilities, "version": definition.version,
            "activeDelegations": len(active), "totalDelegations": len(delegations),
            "health": "ok" if definition.status is AgentStatus.ACTIVE else definition.status.value,
        }

    # ── delegation (§13) ─────────────────────────────────────────────────────────

    async def delegate_task(
        self, *, sender_agent_id: str, run_id: str, objective: str,
        target_agent_id: Optional[str] = None, capability: Optional[str] = None,
        context: str = "", tool_subset: Optional[list[str]] = None,
        priority: str = "NORMAL", parent_task_id: Optional[str] = None,
        root_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        root = root_run_id or run_id
        sender = self._require_agent(sender_agent_id)
        target_id = target_agent_id or (
            self.registry.capable_agent_for(capability) if capability else None
        )
        if not target_id:
            raise A2AError(
                A2A_NO_CAPABLE_AGENT,
                f"no agent can do {capability!r}" if capability else "no target agent named",
            )
        target = self._require_agent(target_id)
        if not permissions.can_delegate(sender, target_id):
            raise A2AError(
                A2A_DELEGATION_REFUSED, f"{sender_agent_id} may not delegate to {target_id}",
            )
        if target.status is not AgentStatus.ACTIVE:
            raise A2AError(A2A_DELEGATION_REFUSED, f"{target_id} is not active")
        if capability and not permissions.has_capability(target, capability):
            raise A2AError(
                A2A_DELEGATION_REFUSED, f"{target_id} does not hold {capability!r}",
            )

        # Budget: depth, one agent, one task. Fail-closed BEFORE creating anything.
        try:
            self.budgets.reserve(root, "depth")
            self.budgets.reserve(root, "agents")
            self.budgets.reserve(root, "tasks")
        except BudgetExceeded as exc:
            raise A2AError(A2A_BUDGET_EXCEEDED, exc.reason, detail={"kind": exc.kind}) from exc

        requested = tool_subset if tool_subset is not None else target.tools
        tools = permissions.permitted_tools(target, requested) if requested else None

        manager = self._task_manager()
        plan_id = self._ensure_plan(manager, root)
        from ..tasks.model import TaskPriority  # noqa: PLC0415

        task_priority = _PRIORITY_TO_TASK.get(str(priority).upper(), "NORMAL")
        task = manager.create_task(
            {
                "title": f"{target.name}: {objective[:80]}",
                "objective": objective,
                "description": context,
                "plan_id": plan_id,
                "assigned_agent_id": target_id,
                "priority": TaskPriority(task_priority),
                "metadata": {"a2a": True, "rootRunId": root, "senderAgentId": sender_agent_id},
            },
            actor_id=sender_agent_id,
        )

        correlation = "cor_" + _hex()
        record = self.store.save_delegation(DelegationRecord(
            parent_agent_id=sender_agent_id, child_agent_id=target_id, parent_run_id=run_id,
            parent_task_id=parent_task_id, child_task_id=task.id, objective=objective,
            status=DelegationStatus.CREATED,
            budget=self.budgets.child_budget(root).model_dump(by_alias=True),
            correlation_id=correlation,
        ))

        self.bus.publish(make_envelope(
            MessageType.DELEGATION, sender=sender_agent_id, recipient=target_id, run_id=run_id,
            task_id=task.id, correlation_id=correlation,
            payload={"childAgentId": target_id, "objective": objective, "tools": tools or []},
        ))
        self.bus.publish(make_envelope(
            MessageType.TASK_REQUEST, sender=sender_agent_id, recipient=target_id, run_id=run_id,
            task_id=task.id, correlation_id=correlation,
            payload={"objective": objective, "context": context, "toolSubset": tools or [],
                     "priority": task_priority},
        ))
        await self._emit(run_id, "delegation.created", {
            "delegationId": record.id, "parentAgentId": sender_agent_id,
            "childAgentId": target_id, "childTaskId": task.id,
        })
        return {
            "taskId": task.id, "delegationId": record.id, "childAgentId": target_id,
            "correlationId": correlation, "status": task.status.value, "nonBlocking": True,
        }

    async def spawn_agent(
        self, *, sender_agent_id: str, run_id: str, base_agent_id: str, objective: str,
        overrides: Optional[dict[str, Any]] = None, context: str = "",
        parent_task_id: Optional[str] = None, root_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        sender = self._require_agent(sender_agent_id)
        base = self._require_agent(base_agent_id)
        overrides = overrides or {}
        composed = permissions.intersection(sender, base)
        spawned_id = "spawned_" + _hex(10)
        definition = composed.model_copy(update={
            "id": spawned_id,
            "name": str(overrides.get("name") or f"{base.name} (spawned)"),
            "can_delegate": False,
            "allowed_delegates": [],
            "status": AgentStatus.ACTIVE,
            "version": "1.0.0",
            "created_at": "",
            "updated_at": "",
        })
        if overrides.get("systemInstructions"):
            definition.system_instructions = str(overrides["systemInstructions"])[:20_000]
        if overrides.get("tools") is not None:
            # A spawned agent can only NARROW its base's tools.
            definition.tools = permissions.permitted_tools(composed, list(overrides["tools"]))
        definition.metadata = {**definition.metadata, "spawnedBy": sender_agent_id, "ephemeral": True}
        self.registry.register_agent(definition)
        self._install_agent_configs([{
            "id": spawned_id, "name": definition.name,
            "systemPrompt": definition.system_instructions or "You are a temporary Eclipse agent.",
            "tools": definition.tools, "maxSteps": int(definition.metadata.get("maxSteps") or 6),
            "runTimeoutMs": min(600_000, definition.timeout_ms),
        }])
        result = await self.delegate_task(
            sender_agent_id=sender_agent_id, run_id=run_id, objective=objective,
            target_agent_id=spawned_id, context=context, parent_task_id=parent_task_id,
            root_run_id=root_run_id,
        )
        result["spawnedAgentId"] = spawned_id
        await self._emit(run_id, "agent.spawned", {
            "spawnedAgentId": spawned_id, "baseAgentId": base_agent_id,
            "parentAgentId": sender_agent_id,
        })
        return result

    # ── messaging (§10, §15) ──────────────────────────────────────────────────────

    def send_message(
        self, *, sender_agent_id: str, recipient_agent_id: Optional[str],
        message_type: MessageType | str, payload: Optional[dict[str, Any]] = None,
        run_id: str = "", task_id: Optional[str] = None,
        correlation_id: Optional[str] = None, priority: str = "NORMAL",
        evidence_refs: Optional[list[str]] = None,
    ) -> AgentEnvelope:
        self._require_agent(sender_agent_id)
        if recipient_agent_id is not None:
            self._require_agent(recipient_agent_id)
        envelope = make_envelope(
            message_type, sender=sender_agent_id, recipient=recipient_agent_id, run_id=run_id,
            task_id=task_id, correlation_id=correlation_id, payload=payload,
            evidence_refs=evidence_refs, priority=MessagePriority(str(priority).upper()),
        )
        stored, _ = self.bus.publish(envelope)
        return stored

    def receive_message(self, *, recipient_agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
        envelopes = self.bus.consume(recipient_agent_id, limit=limit)
        return [e.to_row() for e in envelopes]

    async def ask_agent(
        self, *, sender_agent_id: str, recipient_agent_id: str, question: str, run_id: str,
        task_id: Optional[str] = None, wait: bool = False, timeout_s: float = 60.0,
        root_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Ask another agent a structured question. Non-blocking unless `wait`."""
        self._require_agent(sender_agent_id)
        self._require_agent(recipient_agent_id)
        correlation = "cor_" + _hex()
        self.bus.publish(make_envelope(
            MessageType.QUESTION, sender=sender_agent_id, recipient=recipient_agent_id,
            run_id=run_id, task_id=task_id, correlation_id=correlation,
            payload={"question": question},
        ))
        delegated = await self.delegate_task(
            sender_agent_id=sender_agent_id, run_id=run_id, objective=question,
            target_agent_id=recipient_agent_id, context=f"Answer this question: {question}",
            root_run_id=root_run_id,
        )
        responded = False
        if wait:
            responded = await self._wait(f"task:{delegated['taskId']}", timeout_s)
        return {
            "questionEnvelopeId": correlation, "correlationId": correlation,
            "answerTaskId": delegated["taskId"], "responded": responded,
            "timedOut": bool(wait and not responded),
        }

    def broadcast_message(
        self, *, sender_agent_id: str, message_type: MessageType | str,
        payload: Optional[dict[str, Any]] = None, run_id: str = "",
        priority: str = "NORMAL",
    ) -> dict[str, Any]:
        self._require_agent(sender_agent_id)
        envelope = make_envelope(
            message_type, sender=sender_agent_id, recipient=None, run_id=run_id,
            payload=payload, priority=MessagePriority(str(priority).upper()),
        )
        stored, _ = self.bus.publish(envelope)
        return {"messageId": stored.id, "type": stored.type.value, "broadcast": True}

    # ── task steering ─────────────────────────────────────────────────────────────

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        manager = self._task_manager()
        task = manager.get_task(task_id)
        return {
            "taskId": task.id, "status": task.status.value, "progress": task.progress,
            "assignedAgentId": task.assigned_agent_id, "assignedRunId": task.assigned_run_id,
            "ready": manager.is_runnable(task), "error": task.error,
        }

    def get_task_result(self, task_id: str) -> dict[str, Any]:
        manager = self._task_manager()
        task = manager.get_task(task_id)
        stored = self.store.find_result(task_id)
        return {
            "taskId": task.id, "status": task.status.value,
            "outputReference": task.output_reference,
            "result": stored["result"] if stored else None,
            "artifacts": [a.model_dump(by_alias=True) for a in manager.list_artifacts(task_id)],
        }

    async def wait_agent(self, *, task_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
        manager = self._task_manager()
        task = manager.get_task(task_id)
        if task.status.value in ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"):
            return self.get_task_status(task_id)
        completed = await self._wait(f"task:{task_id}", timeout_s)
        status = self.get_task_status(task_id)
        status["timedOut"] = not completed and status["status"] not in (
            "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED",
        )
        return status

    async def cancel_agent(self, *, run_id: str, task_id: Optional[str] = None,
                           delegation_id: Optional[str] = None, reason: str = "") -> dict[str, Any]:
        manager = self._task_manager()
        targets: list[str] = []
        if task_id:
            targets.append(task_id)
        if delegation_id:
            record = self.store.get_delegation(delegation_id)
            if record and record.child_task_id:
                targets.append(record.child_task_id)
        if not targets:
            for record in self.store.list_delegations(parent_run_id=run_id, limit=500):
                if record.child_task_id:
                    targets.append(record.child_task_id)
        cancelled: list[str] = []
        for target in targets:
            try:
                manager.cancel_task(target, reason=reason or "cancelled by orchestrator")
                cancelled.append(target)
            except Exception:  # noqa: BLE001 - a missing/already-terminal task is not fatal
                continue
            self.bus.publish(make_envelope(
                MessageType.CANCEL, sender="eclipse-orchestrator", recipient=None,
                run_id=run_id, task_id=target, payload={"targetId": target, "reason": reason},
            ))
        await self._emit(run_id, "delegation.cancelled", {"taskIds": cancelled})
        return {"cancelledTaskIds": cancelled}

    def report_failure(self, *, sender_agent_id: str, run_id: str, task_id: Optional[str],
                       error: str, error_class: str = "A2A_FAILURE") -> dict[str, Any]:
        self._require_agent(sender_agent_id)
        self.bus.publish(make_envelope(
            MessageType.FAILURE, sender=sender_agent_id, recipient="eclipse-orchestrator",
            run_id=run_id, task_id=task_id,
            payload={"error": error, "errorClass": error_class},
        ))
        if task_id:
            try:
                self._task_manager().fail_task(task_id, error=error, error_class=error_class,
                                               actor_id=sender_agent_id)
            except Exception:  # noqa: BLE001
                pass
        return {"reported": True, "taskId": task_id}

    # ── results / merge / review (§19-25) ──────────────────────────────────────────

    def record_result(self, result: A2AResult, *, run_id: str = "") -> str:
        result_id = self.store.save_result(result, run_id=run_id or None)
        for finding in result.findings:
            self.bus.publish(make_envelope(
                MessageType.FINDING, sender=result.agent_id or "unknown", recipient="eclipse-orchestrator",
                run_id=run_id, task_id=result.task_id,
                payload={"claim": finding.claim, "confidence": finding.confidence},
                evidence_refs=finding.evidence_refs,
            ))
        self._publish_event("result.recorded", {"runId": run_id, "taskId": result.task_id})
        return result_id

    def merge_results(self, results: list[A2AResult] | list[dict[str, Any]]) -> dict[str, Any]:
        parsed = [
            r if isinstance(r, A2AResult) else A2AResult(**r) for r in results
        ]
        merged: MergedResult = _merge(parsed, evidence_exists=self._evidence_exists())
        return merged.model_dump(by_alias=True)

    def request_review(self, *, sender_agent_id: str, run_id: str, subject: str,
                       task_id: Optional[str] = None, target_agent_id: str = "qa-agent") -> dict[str, Any]:
        self._require_agent(sender_agent_id)
        self._require_agent(target_agent_id)
        correlation = "cor_" + _hex()
        self.bus.publish(make_envelope(
            MessageType.REVIEW_REQUEST, sender=sender_agent_id, recipient=target_agent_id,
            run_id=run_id, task_id=task_id, correlation_id=correlation,
            payload={"subject": subject},
        ))
        return {"reviewCorrelationId": correlation, "reviewerAgentId": target_agent_id}

    def request_approval(self, *, sender_agent_id: str, run_id: str, subject: str,
                         kind: str = "action", task_id: Optional[str] = None,
                         detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._require_agent(sender_agent_id)
        approval = self.store.save_approval({
            "runId": run_id, "agentId": sender_agent_id, "taskId": task_id, "kind": kind,
            "subject": subject, "status": ApprovalStatus.PENDING.value, "detail": detail or {},
        })
        self.bus.publish(make_envelope(
            MessageType.APPROVAL_REQUEST, sender=sender_agent_id,
            recipient="eclipse-orchestrator", run_id=run_id, task_id=task_id,
            payload={"subject": subject, "kind": kind, "approvalId": approval["id"]},
        ))
        self._publish_event("approval.requested", {"runId": run_id, "approvalId": approval["id"]})
        return {"approvalId": approval["id"], "status": ApprovalStatus.PENDING.value}

    def decide_approval(self, approval_id: str, decision: str, *, decided_by: str = "operator") -> dict[str, Any]:
        try:
            status = ApprovalStatus(str(decision).upper())
        except ValueError as exc:
            raise A2AError(A2A_ERROR, f"unknown approval decision {decision!r}") from exc
        decided = self.store.decide_approval(approval_id, status, decided_by=decided_by)
        if decided is None:
            raise A2AError(A2A_NO_AGENT, f"no pending approval {approval_id!r}")
        self._publish_event("approval.granted" if status is ApprovalStatus.GRANTED else "approval.denied",
                            {"approvalId": approval_id, "status": status.value})
        return decided

    def supervise(self, run_id: str, *, expected_agents: Optional[list[str]] = None,
                  results: Optional[list[A2AResult] | list[dict[str, Any]]] = None) -> dict[str, Any]:
        parsed = self._results_for(run_id) if results is None else [
            r if isinstance(r, A2AResult) else A2AResult(**r) for r in results
        ]
        report = _review(parsed, evidence_exists=self._evidence_exists(),
                         expected_agents=expected_agents)
        return report.model_dump(by_alias=True)

    def qa(self, run_id: str, *, expected_agents: Optional[list[str]] = None,
           results: Optional[list[A2AResult] | list[dict[str, Any]]] = None) -> dict[str, Any]:
        parsed = self._results_for(run_id) if results is None else [
            r if isinstance(r, A2AResult) else A2AResult(**r) for r in results
        ]
        return _qa(parsed, evidence_exists=self._evidence_exists(), expected_agents=expected_agents)

    def _results_for(self, run_id: str) -> list[A2AResult]:
        out: list[A2AResult] = []
        for row in self.store.list_results(run_id=run_id, limit=500):
            payload = row.get("result") or {}
            try:
                with_id = dict(payload)
                with_id.setdefault("agentId", row.get("agentId") or "")
                with_id.setdefault("taskId", row.get("taskId"))
                out.append(A2AResult(**with_id))
            except Exception:  # noqa: BLE001
                continue
        return out

    # ── helpers ─────────────────────────────────────────────────────────────────

    def budget_snapshot(self, run_id: str) -> dict[str, Any]:
        return self.budgets.snapshot(run_id)

    def _require_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self.registry.get_agent(agent_id)
        except RegistryError as exc:
            raise A2AError(A2A_NO_AGENT, exc.reason) from exc

    def _ensure_plan(self, manager: Any, root_run_id: str) -> str:
        cached = self._plan_cache.get(root_run_id)
        if cached:
            return cached
        name = f"A2A {root_run_id}"
        for plan in manager.list_plans(limit=500):
            if plan.name == name:
                self._plan_cache[root_run_id] = plan.id
                return plan.id
        from ..tasks.model import CreatePlanInput  # noqa: PLC0415

        plan = manager.create_plan(CreatePlanInput(
            name=name, objective=f"Agent-to-agent work for run {root_run_id}",
            metadata={"a2a": True, "rootRunId": root_run_id},
        ))
        self._plan_cache[root_run_id] = plan.id
        return plan.id

    def events(self, run_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        return self.store.list_events(run_id, limit=limit)

    def delegations(self, run_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        return [d.model_dump(by_alias=True)
                for d in self.store.list_delegations(parent_run_id=run_id, limit=limit)]


__all__ = [
    "A2AError",
    "A2AService",
]
