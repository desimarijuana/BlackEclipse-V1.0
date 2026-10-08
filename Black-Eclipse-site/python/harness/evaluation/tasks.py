"""The versioned evaluation-task schema and dataset loader.

A task is DATA, not code: a prompt, an environment reference, an initial state,
an expected output/state, the tools that should (or must not) be used, grader
configuration, constraints and limits. The schema is versioned
(:data:`TASK_SCHEMA_VERSION`) and every task carries its own ``version``; changing
a task BUMPS its ``version`` so historical results stay attached to the exact
task that produced them (a score is ``(task_id, task_version)``-scoped).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import TASK_SCHEMA_VERSION

# The capability classes a user can ask for. Kept in one place so the registry,
# reports and the generated capability statement agree.
CATEGORIES: tuple[str, ...] = (
    "core",
    "tools",
    "research",
    "citations",
    "finance",
    "coding",
    "browser",
    "memory",
    "planning",
    "long_horizon",
    "recovery",
    "parallel",
    "safety",
    "adversarial",
    "regression",
)

DIFFICULTIES: tuple[str, ...] = ("easy", "medium", "hard", "adversarial")

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")

# The categories a task may declare as needing a live model. In the offline
# deterministic tier these are reported `unmeasured` rather than faked.
LIVE_CATEGORIES = frozenset({"research", "citations"})


class TaskValidationError(ValueError):
    """A dataset or task is malformed. Raised loudly, never swallowed."""


@dataclass(frozen=True)
class TaskLimits:
    max_turns: int = 40
    max_tool_calls: int = 200
    max_cost: float = 0.0  # 0 = unconstrained (measured, not gated)
    token_budget: int = 0  # 0 = unconstrained
    timeout_seconds: float = 300.0

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "TaskLimits":
        data = data or {}
        return cls(
            max_turns=int(data.get("max_turns", data.get("maxTurns", 40))),
            max_tool_calls=int(data.get("max_tool_calls", data.get("maxToolCalls", 200))),
            max_cost=float(data.get("max_cost", data.get("maxCost", 0.0))),
            token_budget=int(data.get("token_budget", data.get("tokenBudget", 0))),
            timeout_seconds=float(data.get("timeout_seconds", data.get("timeoutSeconds", 300.0))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_turns": self.max_turns,
            "max_tool_calls": self.max_tool_calls,
            "max_cost": self.max_cost,
            "token_budget": self.token_budget,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class EvaluationTask:
    id: str
    name: str
    description: str
    category: str
    difficulty: str
    version: int = 1
    input: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    initial_state: dict[str, Any] = field(default_factory=dict)
    expected_output: Any = None
    expected_state: dict[str, Any] = field(default_factory=dict)
    expected_tools: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    graders: tuple[dict[str, Any], ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    limits: TaskLimits = field(default_factory=TaskLimits)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationTask":
        for required in ("id", "category", "difficulty", "input"):
            if not data.get(required):
                raise TaskValidationError(f"task '{data.get('id', '?')}' missing '{required}'")
        category = str(data["category"])
        difficulty = str(data["difficulty"])
        if category not in CATEGORIES:
            raise TaskValidationError(f"task {data['id']}: unknown category '{category}'")
        if difficulty not in DIFFICULTIES:
            raise TaskValidationError(f"task {data['id']}: unknown difficulty '{difficulty}'")
        return cls(
            id=str(data["id"]),
            version=int(data.get("version", 1)),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description") or ""),
            category=category,
            difficulty=difficulty,
            input=dict(data.get("input") or {}),
            environment=dict(data.get("environment") or {}),
            initial_state=dict(data.get("initial_state") or data.get("initialState") or {}),
            expected_output=data.get("expected_output", data.get("expectedOutput")),
            expected_state=dict(data.get("expected_state") or data.get("expectedState") or {}),
            expected_tools=tuple(data.get("expected_tools") or data.get("expectedTools") or ()),
            required_tools=tuple(data.get("required_tools") or data.get("requiredTools") or ()),
            forbidden_tools=tuple(data.get("forbidden_tools") or data.get("forbiddenTools") or ()),
            graders=tuple(data.get("graders") or ()),
            constraints=dict(data.get("constraints") or {}),
            limits=TaskLimits.from_dict(data.get("limits")),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "difficulty": self.difficulty,
            "input": self.input,
            "environment": self.environment,
            "initial_state": self.initial_state,
            "expected_output": self.expected_output,
            "expected_state": self.expected_state,
            "expected_tools": list(self.expected_tools),
            "required_tools": list(self.required_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "graders": list(self.graders),
            "constraints": self.constraints,
            "limits": self.limits.to_dict(),
            "metadata": self.metadata,
        }

    @property
    def live_only(self) -> bool:
        """True when the task can only be graded with a live model.

        A task is live-only when it says so, or when it belongs to a category
        whose quality genuinely requires a real model (research/citations). A
        scripted tier reports it `unmeasured` — never a fabricated pass.
        """
        if self.metadata.get("live_only"):
            return True
        return self.category in LIVE_CATEGORIES and not self.metadata.get("agent_script")

    @property
    def agent_script(self) -> list[dict[str, Any]]:
        """The deterministic model program, when the task ships one.

        Each step is ``{"type": "tool", "name": ..., "args": {...}}`` or
        ``{"type": "final", "content": ...}``. A task with no script cannot be
        driven by the offline (scripted) tier.
        """
        script = self.metadata.get("agent_script")
        return list(script) if isinstance(script, list) else []

    def fingerprint(self) -> str:
        """A stable content hash of the task, recorded with every result."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]


@dataclass
class Dataset:
    name: str
    version: str
    tasks: list[EvaluationTask]
    metadata: dict[str, Any] = field(default_factory=dict)
    reviewed: bool = False
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    notes: str = ""

    @property
    def checksum(self) -> str:
        payload = json.dumps(
            [t.to_dict() for t in self.tasks], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasetName": self.name,
            "datasetVersion": self.version,
            "schemaVersion": TASK_SCHEMA_VERSION,
            "reviewed": self.reviewed,
            "reviewer": self.reviewer,
            "reviewedAt": self.reviewed_at,
            "notes": self.notes,
            "checksum": self.checksum,
            "metadata": self.metadata,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def by_id(self, task_id: str) -> Optional[EvaluationTask]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


def dataset_checksum(tasks: list[EvaluationTask]) -> str:
    payload = json.dumps(
        [t.to_dict() for t in tasks], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def load_dataset(path: str) -> Dataset:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    return dataset_from_dict(raw, source=path)


def dataset_from_dict(raw: dict[str, Any], *, source: str = "<memory>") -> Dataset:
    if not isinstance(raw, dict) or "tasks" not in raw:
        raise TaskValidationError(f"{source}: a dataset must be an object with a 'tasks' list")
    tasks = [EvaluationTask.from_dict(item) for item in raw.get("tasks") or []]
    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            raise TaskValidationError(f"{source}: duplicate task id '{task.id}'")
        seen.add(task.id)
    return Dataset(
        name=str(raw.get("datasetName") or raw.get("name") or os.path.basename(source)),
        version=str(raw.get("datasetVersion") or raw.get("version") or "0"),
        tasks=tasks,
        metadata=dict(raw.get("metadata") or {}),
        reviewed=bool(raw.get("reviewed", False)),
        reviewer=raw.get("reviewer"),
        reviewed_at=raw.get("reviewedAt") or raw.get("reviewed_at"),
        notes=str(raw.get("notes") or ""),
    )


def available_datasets() -> list[str]:
    if not os.path.isdir(DATASETS_DIR):
        return []
    return sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(DATASETS_DIR)
        if name.endswith(".json")
    )


def load_builtin_dataset(name: str) -> Dataset:
    path = os.path.join(DATASETS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        raise TaskValidationError(
            f"unknown dataset '{name}' (available: {', '.join(available_datasets()) or 'none'})"
        )
    return load_dataset(path)


def load_all_builtin() -> Dataset:
    """Every built-in dataset merged, with per-task ids preserved."""
    tasks: list[EvaluationTask] = []
    names: list[str] = []
    for name in available_datasets():
        ds = load_builtin_dataset(name)
        names.append(f"{ds.name}@{ds.version}")
        tasks.extend(ds.tasks)
    ids = {t.id for t in tasks}
    if len(ids) != len(tasks):
        raise TaskValidationError("built-in datasets contain duplicate task ids")
    return Dataset(name="eclipse-benchmark", version="1", tasks=tasks,
                   metadata={"datasets": names})


def select_tasks(
    dataset: Dataset,
    *,
    task_id: Optional[str] = None,
    suite: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    tier: Optional[int] = None,
) -> list[EvaluationTask]:
    """Filter a dataset. `suite` matches a task's ``metadata.suite`` or category."""
    tasks = list(dataset.tasks)
    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
    if suite:
        tasks = [
            t for t in tasks
            if t.category == suite or t.metadata.get("suite") == suite
            or suite in (t.metadata.get("suites") or [])
        ]
    if category:
        tasks = [t for t in tasks if t.category == category]
    if difficulty:
        tasks = [t for t in tasks if t.difficulty == difficulty]
    if tier is not None:
        tasks = [t for t in tasks if int(t.metadata.get("tier", 1)) <= tier]
    return tasks


__all__ = [
    "CATEGORIES",
    "DATASETS_DIR",
    "DIFFICULTIES",
    "Dataset",
    "EvaluationTask",
    "LIVE_CATEGORIES",
    "TaskLimits",
    "TaskValidationError",
    "available_datasets",
    "dataset_checksum",
    "dataset_from_dict",
    "load_all_builtin",
    "load_builtin_dataset",
    "load_dataset",
    "select_tasks",
]
