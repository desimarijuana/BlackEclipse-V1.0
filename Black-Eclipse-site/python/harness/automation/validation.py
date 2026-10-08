"""Automation validation + testing (§36, §37).

`validate_automation` catches every class of misconfiguration BEFORE activation
and returns actionable issues (severity + stable code + the field). `test_automation`
is validation plus a dry-run dispatch plan, so a user can see exactly what would
happen without performing any side effect.

Never fabricates success: a referenced workflow/agent/skill/tool that does not
exist is an ERROR, not a warning. Unknown EVENT types are allowed (the event
vocabulary is open-ended by design), but the type must be a well-formed name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .conditions import ConditionError, validate_condition
from .model import AutomationDefinition, DELIVERY_ADAPTERS, NON_RETRYABLE_ERROR_CLASSES
from .timeutil import TimezoneError, resolve_timezone

ERROR = "error"
WARNING = "warning"

# Action types that require a specific binding.
_ACTION_REQUIRES = {
    "execute_workflow": "workflow_id",
    "call_tool": "tool_name",
    "run_agent": "objective",
    "execute_task": None,  # objective OR skill
    "delegate_agent": "objective",
    "send_notification": "notification_template",
    "generate_report": None,
    "run_code": "tool_name",
    "browser_action": "tool_name",
    "create_task": None,
    "custom_action": "tool_name",
}

# Obvious secret material that must never be embedded in a definition (§29).
_SECRET_KEYS = frozenset({
    "apikey", "api_key", "password", "passwd", "secret", "token", "access_token",
    "refresh_token", "private_key", "client_secret", "authorization",
})


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "field": self.field, "message": self.message}


def _contains_secret(data: Any, path: str = "") -> Optional[str]:
    if isinstance(data, dict):
        for key, value in data.items():
            key_l = str(key).lower()
            if key_l in _SECRET_KEYS and value:
                return f"{path}.{key}".lstrip(".")
            found = _contains_secret(value, f"{path}.{key}".lstrip("."))
            if found:
                return found
    elif isinstance(data, list):
        for index, item in enumerate(data):
            found = _contains_secret(item, f"{path}[{index}]")
            if found:
                return found
    return None


def validate_automation(
    definition: AutomationDefinition,
    *,
    skill_registry: Any = None,
    workflow_store: Any = None,
    known_agents: Optional[set[str]] = None,
    tool_names: Optional[set[str]] = None,
    known_variables: Optional[set[str]] = None,
) -> list[ValidationIssue]:
    """Return every validation issue for a definition (empty ⇒ valid)."""
    issues: list[ValidationIssue] = []
    trigger = definition.trigger
    action = definition.action

    # ── Trigger ──────────────────────────────────────────────────────────────
    try:
        resolve_timezone(trigger.timezone)
    except TimezoneError as exc:
        issues.append(ValidationIssue(ERROR, "INVALID_TIMEZONE", "trigger.timezone", exc.message))

    if trigger.type == "cron":
        from ..jobs.cron import CronError, parse_cron  # noqa: PLC0415

        try:
            parse_cron(trigger.cron or "")
        except CronError as exc:
            issues.append(ValidationIssue(ERROR, "INVALID_CRON", "trigger.cron", exc.message))
    elif trigger.type == "interval":
        if not trigger.interval_seconds or trigger.interval_seconds < 60:
            issues.append(ValidationIssue(
                ERROR, "INVALID_INTERVAL", "trigger.intervalSeconds",
                "an interval must be at least 60 seconds",
            ))
    elif trigger.type == "one_time":
        from .timeutil import parse_iso  # noqa: PLC0415

        if parse_iso(trigger.run_at) is None:
            issues.append(ValidationIssue(
                ERROR, "INVALID_RUN_AT", "trigger.runAt", "run_at must be an ISO-8601 timestamp",
            ))
    elif trigger.type == "event":
        event_type = trigger.event_type or ""
        if not event_type or "." not in event_type or " " in event_type:
            issues.append(ValidationIssue(
                ERROR, "INVALID_EVENT", "trigger.eventType",
                "an event type must be a dotted name like 'filing.created'",
            ))
    elif trigger.type == "condition":
        if trigger.condition is None:
            issues.append(ValidationIssue(ERROR, "INVALID_CONDITION", "trigger.condition", "a condition trigger needs a condition"))
        else:
            _validate_condition(trigger.condition.expression, known_variables, "trigger.condition.expression", issues)

    # An optional gate condition on any trigger.
    if definition.condition is not None:
        _validate_condition(definition.condition.expression, known_variables, "condition.expression", issues)

    # ── Action ───────────────────────────────────────────────────────────────
    if action.type not in _ACTION_REQUIRES:
        issues.append(ValidationIssue(ERROR, "INVALID_ACTION", "action.type", f"unknown action type {action.type!r}"))
    else:
        required = _ACTION_REQUIRES[action.type]
        if required and not getattr(action, required, None):
            issues.append(ValidationIssue(
                ERROR, "INVALID_ACTION", f"action.{required}", f"action {action.type!r} requires {required}",
            ))
        if action.type == "execute_task" and not (action.skill_id or action.objective):
            issues.append(ValidationIssue(
                ERROR, "INVALID_ACTION", "action",
                "an execute_task action needs a skill or an objective",
            ))
        if action.workspace_root and not action.autonomy:
            issues.append(ValidationIssue(
                WARNING, "AUTONOMY_ABSENT", "action.autonomy",
                "a workspace is bound but no autonomy profile is set; code tools stay unavailable",
            ))

    # ── Referenced entities ──────────────────────────────────────────────────
    if action.workflow_id and workflow_store is not None:
        try:
            if workflow_store.get(action.workflow_id) is None:
                issues.append(ValidationIssue(ERROR, "WORKFLOW_NOT_FOUND", "action.workflowId", f"no workflow {action.workflow_id!r}"))
        except Exception:  # noqa: BLE001 - an unreadable store is reported, not fatal
            issues.append(ValidationIssue(WARNING, "WORKFLOW_UNVERIFIED", "action.workflowId", "the workflow store could not be read"))
    if action.skill_id and skill_registry is not None:
        try:
            manifest = skill_registry.manifest(action.skill_id)
            if manifest is None:
                issues.append(ValidationIssue(ERROR, "SKILL_NOT_FOUND", "action.skillId", f"skill {action.skill_id!r} is not installed"))
        except Exception:  # noqa: BLE001
            issues.append(ValidationIssue(WARNING, "SKILL_UNVERIFIED", "action.skillId", "the skill registry could not be read"))
    if action.agent_id and known_agents is not None and action.agent_id not in known_agents:
        issues.append(ValidationIssue(ERROR, "AGENT_NOT_FOUND", "action.agentId", f"no agent {action.agent_id!r}"))
    if action.tool_name and tool_names is not None and action.tool_name not in tool_names:
        issues.append(ValidationIssue(ERROR, "TOOL_NOT_FOUND", "action.toolName", f"no tool {action.tool_name!r}"))

    # ── Delivery ─────────────────────────────────────────────────────────────
    if definition.delivery.adapter not in DELIVERY_ADAPTERS:
        issues.append(ValidationIssue(ERROR, "UNKNOWN_ADAPTER", "delivery.adapter", f"unknown delivery adapter {definition.delivery.adapter!r}"))
    for target in definition.delivery.targets:
        if target.adapter not in DELIVERY_ADAPTERS:
            issues.append(ValidationIssue(ERROR, "UNKNOWN_ADAPTER", "delivery.targets", f"unknown delivery adapter {target.adapter!r}"))

    # ── Retry / resource limits / concurrency ────────────────────────────────
    retry = definition.retry
    overlap = set(retry.retryable_classes) & set(retry.non_retryable_classes)
    if overlap:
        issues.append(ValidationIssue(
            ERROR, "CONFLICTING_RETRY_CLASSES", "retry",
            f"error class {sorted(overlap)[0]!r} is both retryable and non-retryable",
        ))
    if retry.max_attempts > 1:
        non_retryable = set(retry.non_retryable_classes) | NON_RETRYABLE_ERROR_CLASSES
        if retry.retryable_classes and set(retry.retryable_classes) <= non_retryable:
            issues.append(ValidationIssue(
                ERROR, "CONFLICTING_RETRY_CLASSES", "retry.retryableClasses",
                "every retryable class is non-retryable; retries would never happen",
            ))
    limits = definition.limits
    if limits.max_runtime_s is not None and limits.max_runtime_s > definition.execution.max_runtime_s:
        issues.append(ValidationIssue(
            WARNING, "LIMIT_ABOVE_TIMEOUT", "limits.maxRuntimeS",
            "the resource limit exceeds the execution timeout and will never bind",
        ))
    if limits.max_retries is not None and limits.max_retries > retry.max_attempts:
        issues.append(ValidationIssue(
            WARNING, "LIMIT_ABOVE_RETRIES", "limits.maxRetries",
            "the retry limit exceeds max_attempts and will never bind",
        ))
    concurrency = definition.concurrency
    if concurrency.on_conflict == "cancel_previous" and concurrency.max_concurrent_runs > 1:
        issues.append(ValidationIssue(
            ERROR, "CONFLICTING_CONCURRENCY", "concurrency",
            "cancel_previous requires max_concurrent_runs = 1",
        ))

    # ── Permission policy: deny wins; conflicting grants are refused ─────────
    perms = definition.permissions
    both = set(perms.allowed) & set(perms.denied)
    if both:
        issues.append(ValidationIssue(
            ERROR, "CONFLICTING_PERMISSIONS", "permissions",
            f"{sorted(both)[0]!r} is both allowed and denied",
        ))
    if perms.requires_approval and not perms.approval_scope:
        issues.append(ValidationIssue(
            WARNING, "APPROVAL_SCOPE_ABSENT", "permissions.approvalScope",
            "approval is required but no scope label is set",
        ))

    # ── Secrets must be references, never values (§29) ───────────────────────
    for field_name, data in (
        ("action.config", action.config), ("action.toolArgs", action.tool_args),
        ("action.workflowInput", action.workflow_input),
    ):
        found = _contains_secret(data)
        if found:
            issues.append(ValidationIssue(
                ERROR, "EMBEDDED_SECRET", field_name,
                f"{field_name} contains secret-like key {found!r}; store a credential reference instead",
            ))

    return issues


def _validate_condition(expression: str, known_variables: Optional[set[str]], field: str, issues: list[ValidationIssue]) -> None:
    try:
        validate_condition(expression, known_variables=known_variables)
    except ConditionError as exc:
        issues.append(ValidationIssue(ERROR, "INVALID_CONDITION", field, exc.message))


def is_valid(issues: list[ValidationIssue]) -> bool:
    return not any(issue.severity == ERROR for issue in issues)


__all__ = ["ERROR", "WARNING", "ValidationIssue", "is_valid", "validate_automation"]
