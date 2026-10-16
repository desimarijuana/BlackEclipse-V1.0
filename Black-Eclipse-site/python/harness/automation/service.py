"""Automation service facade (§40) — the one entry point for API, tools and UI.

Owns CRUD, lifecycle transitions, validation/testing, manual execution, dry run,
history, versioning and observability. The engine owns WHEN; this owns the
durable domain operations. No agentic logic here.
"""

from __future__ import annotations

from typing import Any, Optional

from ..persistence import now_iso
from .engine import AutomationEngine
from .lifecycle import TransitionError, assert_lifecycle_transition
from .model import (
    ACTION_KINDS,
    AutomationDefinition,
    DeliveryPolicy,
    ExecutionPolicy,
    PermissionPolicy,
    ResourceLimits,
    RetryPolicy,
    ConcurrencyPolicy,
)
from .store import AutomationStore, new_automation_id
from .validation import ValidationIssue, is_valid, validate_automation


class AutomationError(ValueError):
    """A domain refusal with a stable code (maps to an HTTP 4xx)."""

    def __init__(self, code: str, message: str, *, issues: Optional[list[ValidationIssue]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = issues or []


# Fields a PATCH may replace (absent = preserve).
_PATCHABLE = (
    "name", "description", "trigger", "condition", "action", "execution", "retry",
    "concurrency", "limits", "permissions", "delivery", "scope_id", "tags", "state",
)


class AutomationService:
    def __init__(self, service: Any, store: AutomationStore, engine: AutomationEngine) -> None:
        self._service = service
        self._store = store
        self._engine = engine

    # ── Validation ───────────────────────────────────────────────────────────
    def validate(self, definition: AutomationDefinition) -> list[ValidationIssue]:
        return validate_automation(
            definition,
            skill_registry=getattr(self._service, "skill_registry", None),
            workflow_store=self._safe_workflow_store(),
            known_agents=self._known_agents(),
            tool_names=self._tool_names(),
        )

    def _safe_workflow_store(self) -> Any:
        try:
            return self._service.workflow_store()
        except Exception:  # noqa: BLE001
            return None

    def _known_agents(self) -> Optional[set[str]]:
        try:
            from ..agents import AGENT_PRESETS  # noqa: PLC0415

            return set(AGENT_PRESETS.keys())
        except Exception:  # noqa: BLE001
            return None

    def _tool_names(self) -> Optional[set[str]]:
        try:
            return set(self._service.registry.schemas().keys())
        except Exception:  # noqa: BLE001
            return None

    def _assert_valid(self, definition: AutomationDefinition) -> None:
        issues = self.validate(definition)
        if not is_valid(issues):
            first = next(i for i in issues if i.severity == "error")
            raise AutomationError("INVALID_AUTOMATION", first.message, issues=issues)

    # ── CRUD ─────────────────────────────────────────────────────────────────
    def create(self, payload: dict[str, Any], *, created_by: Optional[str] = None) -> AutomationDefinition:
        now = now_iso()
        data = dict(payload)
        data.setdefault("id", new_automation_id())
        data.setdefault("version", 1)
        data.setdefault("state", "draft")
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        data.setdefault("trigger", {})
        data.setdefault("action", {})
        try:
            definition = AutomationDefinition(**data)
        except Exception as exc:  # noqa: BLE001 - a malformed body is a domain error
            raise AutomationError("INVALID_AUTOMATION", str(exc)) from exc
        self._assert_valid(definition)
        saved = self._store.save_automation(definition, created_by=created_by)
        if saved.state == "active":
            self._engine.refresh_schedule(saved.id)
            saved = self._store.get_automation(saved.id) or saved
        return saved

    def get(self, automation_id: str) -> Optional[AutomationDefinition]:
        return self._store.get_automation(automation_id)

    def create_definition(
        self, definition: AutomationDefinition, *, created_by: Optional[str] = None,
    ) -> AutomationDefinition:
        """Create from an already-built definition (legacy adapter / migration)."""
        self._assert_valid(definition)
        saved = self._store.save_automation(definition, created_by=created_by)
        if saved.state == "active":
            self._engine.refresh_schedule(saved.id)
            saved = self._store.get_automation(saved.id) or saved
        return saved

    def list(self, *, limit: int = 200, scope_id: Optional[str] = None, state: Optional[str] = None) -> list[AutomationDefinition]:
        return self._store.list_automations(limit=limit, scope_id=scope_id, state=state)

    # ── Proactive monitors (§ Phase 3) ────────────────────────────────────────
    def list_monitors(self) -> list[dict[str, Any]]:
        """The closed catalogue of portfolio monitors a user may arm."""
        from ..advisory.monitors import list_monitors  # noqa: PLC0415

        return list_monitors()

    def create_monitor(
        self, monitor_id: str, params: dict[str, Any], *,
        name: Optional[str] = None, objective: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> AutomationDefinition:
        """Arm a monitor from the catalogue. Saved OFF; the operator turns it on."""
        from ..advisory.monitors import build_definition  # noqa: PLC0415

        try:
            definition = build_definition(monitor_id, params or {}, name=name, objective=objective)
        except ValueError as exc:
            raise AutomationError("INVALID_MONITOR", str(exc)) from exc
        return self.create_definition(definition, created_by=created_by)

    def update(
        self, automation_id: str, patch: dict[str, Any], *, updated_by: Optional[str] = None,
    ) -> AutomationDefinition:
        current = self._store.get_automation(automation_id)
        if current is None:
            raise AutomationError("NOT_FOUND", "automation not found")
        fields: dict[str, Any] = {}
        for key in _PATCHABLE:
            if key in patch and patch[key] is not None:
                fields[key] = patch[key]
        if not fields:
            return current
        candidate = current.model_copy(update={**fields, "version": current.version + 1, "updated_at": now_iso()})
        # Re-validate the typed sub-models (a malformed dict must be refused).
        candidate = self._retype(candidate, fields)
        self._assert_valid(candidate)
        saved = self._store.save_automation(candidate, created_by=updated_by)
        self._engine.refresh_schedule(saved.id)
        return self._store.get_automation(saved.id) or saved

    def _retype(self, candidate: AutomationDefinition, fields: dict[str, Any]) -> AutomationDefinition:
        try:
            model = AutomationDefinition(**candidate.model_dump(by_alias=False))
        except Exception as exc:  # noqa: BLE001
            raise AutomationError("INVALID_AUTOMATION", str(exc)) from exc
        return model

    def delete(self, automation_id: str) -> bool:
        return self._store.delete_automation(automation_id)

    # ── Lifecycle ────────────────────────────────────────────────────────────
    def set_state(self, automation_id: str, state: str, *, actor: str = "operator") -> AutomationDefinition:
        current = self._store.get_automation(automation_id)
        if current is None:
            raise AutomationError("NOT_FOUND", "automation not found")
        try:
            assert_lifecycle_transition(current.state, state)
        except TransitionError as exc:
            raise AutomationError(exc.code, exc.message) from exc
        if state == "active":
            self._assert_valid(current)
        updated = current.model_copy(update={"state": state, "updated_at": now_iso()})
        saved = self._store.save_automation(updated, snapshot=False)
        self._engine.refresh_schedule(saved.id)
        return self._store.get_automation(saved.id) or saved

    def enable(self, automation_id: str, *, actor: str = "operator") -> AutomationDefinition:
        return self.set_state(automation_id, "active", actor=actor)

    def disable(self, automation_id: str, *, actor: str = "operator") -> AutomationDefinition:
        return self.set_state(automation_id, "disabled", actor=actor)

    def pause(self, automation_id: str, *, actor: str = "operator") -> AutomationDefinition:
        """Pause prevents future triggers. It does NOT kill an active execution."""
        return self.set_state(automation_id, "paused", actor=actor)

    def resume(self, automation_id: str, *, actor: str = "operator") -> AutomationDefinition:
        return self.set_state(automation_id, "active", actor=actor)

    def archive(self, automation_id: str, *, actor: str = "operator") -> AutomationDefinition:
        return self.set_state(automation_id, "archived", actor=actor)

    # ── Execution ────────────────────────────────────────────────────────────
    async def run_now(self, automation_id: str, *, trigger_ref: Optional[str] = None) -> Optional[str]:
        return await self._engine.fire(automation_id, trigger_type="manual", trigger_ref=trigger_ref)

    async def resume_execution(self, execution_id: str) -> bool:
        """Resume a waiting execution once its approval has been granted."""
        return await self._engine.resume_execution(execution_id)

    async def dry_run(self, automation_id: str) -> Optional[dict[str, Any]]:
        return await self._engine.dry_run(automation_id)

    async def test(self, automation_id: str) -> Optional[dict[str, Any]]:
        definition = self._store.get_automation(automation_id)
        if definition is None:
            return None
        issues = self.validate(definition)
        return {
            "automationId": automation_id,
            "valid": is_valid(issues),
            "issues": [i.to_dict() for i in issues],
            "plannedActions": await self._engine.dry_run(automation_id),
        }

    def cancel_execution(self, execution_id: str) -> bool:
        execution = self._store.get_execution(execution_id)
        if execution is None or execution["state"] in ("completed", "failed", "cancelled", "timed_out", "skipped", "blocked"):
            return False
        task = self._engine._active.get(execution_id)  # noqa: SLF001 - cooperative cancel
        if task is not None:
            task.cancel()
        self._store.finish_execution(
            execution_id, state="cancelled", outcome_reason="Stopped by an operator."
        )
        self._store.append_execution_event(execution_id, "cancelled", {"reason": "operator"})
        return True

    def reset_breaker(self, automation_id: str, *, reset_by: str = "operator") -> Optional[AutomationDefinition]:
        return self._engine.reset_breaker(automation_id, reset_by=reset_by)

    # ── History / observability ──────────────────────────────────────────────
    def history(self, automation_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._store.list_executions(automation_id, limit=limit)

    def get_execution(self, execution_id: str) -> Optional[dict[str, Any]]:
        execution = self._store.get_execution(execution_id)
        if execution is None:
            return None
        execution["events"] = self._store.list_execution_events(execution_id)
        execution["deliveries"] = self._store.list_deliveries(execution_id)
        return execution

    def timeline(self, execution_id: str) -> list[dict[str, Any]]:
        return self._store.list_execution_events(execution_id)

    def versions(self, automation_id: str) -> list[dict[str, Any]]:
        return self._store.list_versions(automation_id)

    def version(self, automation_id: str, version: int) -> Optional[dict[str, Any]]:
        return self._store.get_version(automation_id, version)

    def status(self, automation_id: str) -> Optional[dict[str, Any]]:
        definition = self._store.get_automation(automation_id)
        if definition is None:
            return None
        executions = self._store.list_executions(automation_id, limit=200)
        completed = [e for e in executions if e["state"] == "completed"]
        failed = [e for e in executions if e["state"] == "failed"]
        durations = []
        for execution in executions:
            start = execution.get("startedAt")
            end = execution.get("finishedAt")
            if start and end:
                from .timeutil import parse_iso  # noqa: PLC0415

                s, e = parse_iso(start), parse_iso(end)
                if s and e:
                    durations.append((e - s).total_seconds())
        total_cost = sum(e["cost"] or 0.0 for e in executions)
        total_tokens = sum(e["tokens"] or 0 for e in executions)
        finished = len(completed) + len(failed)
        return {
            "automationId": automation_id,
            "state": definition.state,
            "version": definition.version,
            "nextRunAt": definition.next_run_at,
            "lastRunAt": definition.last_run_at,
            "breaker": definition.breaker,
            "executionCount": len(executions),
            "successCount": len(completed),
            "failureCount": len(failed),
            "successRate": (len(completed) / finished) if finished else None,
            "averageDurationS": (sum(durations) / len(durations)) if durations else None,
            "totalCost": total_cost if total_cost else None,
            "totalTokens": total_tokens if total_tokens else None,
            "lastExecution": self._store.last_execution(automation_id),
        }

    def metrics(self) -> dict[str, Any]:
        return self._engine.metrics()


__all__ = ["AutomationError", "AutomationService"]
