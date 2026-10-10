"""UI Engineering Agent — the Engineer-mode orchestration (Phase 7).

When a UI request needs genuinely NEW functionality (mode `engineer`/`both` from
`mode.py`), Eclipse does not invent a parallel agent loop: it creates a DURABLE
engineering task on the EXISTING Task / Plan runtime. The scheduled task is then
executed by the existing code capability (worktree isolation, the filesystem /
terminal / execution-verification tools), which already owns repository
understanding, checks, preview and the bounded repair loop.

This module adds only the UI-specific glue:
  * translate a request into a plan + task with UI acceptance criteria,
  * close the loop by registering the engineered component back into the catalog
    (so a follow-up Compose request can use it),
  * attach the produced component/artifacts as task evidence.

Compose-mode requests are NOT turned into tasks — they are answered by the
`ui_*` composition tools directly. `start` says so honestly instead of creating
a task nobody needs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..tasks.model import AcceptanceCriterionInput, CriterionState, CreatePlanInput, CreateTaskInput
from .model import UiComponentSpec

log = logging.getLogger("harness.ui.engineering")

#: The acceptance criteria every UI engineering task carries. The third is
#: satisfied programmatically by `register_component` (the loop closure).
DEFAULT_ACCEPTANCE: tuple[str, ...] = (
    "The new UI capability's source is implemented and type-checks.",
    "Automated tests for the new capability pass.",
    "The capability is registered in the UI catalog (ui_register_engineered_component).",
    "The resulting page renders correctly in the preview.",
)

_CATALOG_CRITERION_MARKER = "registered in the UI catalog"


class UiEngineeringError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UiEngineering:
    """Compose the UI engineering workflow onto the existing Task / Plan runtime."""

    def __init__(self, ui: Any, tasks: Any) -> None:
        self._ui = ui
        self._tasks = tasks

    @property
    def available(self) -> bool:
        return self._tasks is not None

    def plan(self, text: str, *, blueprint_id: Optional[str] = None, owner_id: Optional[str] = None) -> dict[str, Any]:
        """Classify a request (Phase 6) and report the mode + suggested tools."""
        return self._ui.classify_request(text, blueprint_id=blueprint_id, owner_id=owner_id)

    def start(
        self,
        text: str,
        *,
        blueprint_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        title: Optional[str] = None,
        agent_id: str = "code-agent",
        autonomy: str = "edit_verify",
        priority: str = "NORMAL",
        model_settings: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a durable engineering task for an Engineer/Both-mode request.

        The plan is moved to RUNNING so the EXISTING task scheduler dispatches it
        through the normal run path — creating a plan in PLANNING and stopping
        there is what left "build me a new widget" silently unfinished. When the
        caller supplies `model_settings` (the invoking run's provider/model), it is
        pinned on the plan metadata so the dispatched task uses the operator's
        configured model rather than an env default.
        """
        if self._tasks is None:
            raise UiEngineeringError("UI_ENGINEERING_UNAVAILABLE", "the task runtime is not available")
        decision = self._ui.classify_request(text, blueprint_id=blueprint_id, owner_id=owner_id)
        if decision["mode"] == "compose":
            return {
                "created": False,
                "mode": "compose",
                "reasons": decision["reasons"],
                "suggestedTools": decision["suggestedTools"],
                "message": "This request can be Composed from registered components; no engineering task was created.",
            }
        name = (title or text.strip() or "UI engineering task")[:120]
        metadata: dict[str, Any] = {
            "kind": "ui-engineering", "mode": decision["mode"],
            "blueprintId": blueprint_id, "autonomy": autonomy,
        }
        if isinstance(model_settings, dict) and model_settings.get("provider") and model_settings.get("model"):
            metadata["modelSettings"] = dict(model_settings)
        plan = self._tasks.create_plan(CreatePlanInput(
            name=name, objective=text, agent_id=agent_id, metadata=metadata,
        ))
        task = self._tasks.create_task(CreateTaskInput(
            title=name, description=text, objective=text, plan_id=plan.id,
            assigned_agent_id=agent_id, priority=priority,
            acceptance_criteria=[AcceptanceCriterionInput(text=c) for c in DEFAULT_ACCEPTANCE],
            metadata=metadata,
        ))
        # Dispatch: the scheduler only claims tasks whose plan is RUNNING.
        dispatched = False
        try:
            self._tasks.start_plan(plan.id)
            dispatched = True
        except Exception:  # noqa: BLE001 - a transition race must not lose the task
            log.warning("could not start engineering plan %s", plan.id, exc_info=True)
        return {
            "created": True,
            "mode": decision["mode"],
            "planId": plan.id,
            "taskId": task.id,
            "dispatched": dispatched,
            "acceptance": list(DEFAULT_ACCEPTANCE),
            "suggestedTools": decision["suggestedTools"],
        }

    def status(self, plan_id: str) -> dict[str, Any]:
        if self._tasks is None:
            raise UiEngineeringError("UI_ENGINEERING_UNAVAILABLE", "the task runtime is not available")
        return self._tasks.plan_view(plan_id)

    def register_component(self, task_id: str, spec: UiComponentSpec, *, actor: Optional[str] = None) -> dict[str, Any]:
        """Close the engineer→compose loop: register the new component + evidence.

        The component is added to the ONE catalog (and persisted), the "registered
        in the UI catalog" acceptance criterion is satisfied with evidence, and a
        `ui-component` artifact is attached to the engineering task.
        """
        if self._tasks is None:
            raise UiEngineeringError("UI_ENGINEERING_UNAVAILABLE", "the task runtime is not available")
        saved = self._ui.register_component(spec, actor=actor)
        satisfied: list[str] = []
        try:
            for criterion in self._tasks.list_criteria(task_id):
                if _CATALOG_CRITERION_MARKER in criterion.text and criterion.state != CriterionState.PASSED:
                    self._tasks.set_criterion(criterion.id, CriterionState.PASSED, evidence=f"component:{saved.id}")
                    satisfied.append(criterion.id)
            self._tasks.attach_artifact(
                task_id, uri=f"ui-component:{saved.id}", kind="ui-component", label=saved.display_name,
            )
        except Exception:  # noqa: BLE001 - registration succeeded; evidence is best-effort
            log.warning("ui engineering evidence attachment failed", exc_info=True)
        return {"taskId": task_id, "componentId": saved.id, "satisfiedCriteria": satisfied}

    def link_artifact(self, task_id: str, *, uri: str, kind: str = "file", label: Optional[str] = None) -> dict[str, Any]:
        if self._tasks is None:
            raise UiEngineeringError("UI_ENGINEERING_UNAVAILABLE", "the task runtime is not available")
        artifact = self._tasks.attach_artifact(task_id, uri=uri, kind=kind, label=label)
        return {"taskId": task_id, "artifactId": artifact.id, "uri": uri}


__all__ = ["DEFAULT_ACCEPTANCE", "UiEngineering", "UiEngineeringError"]
