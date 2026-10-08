"""The pluggable grader engine.

Every grader implements one common interface and returns a structured
:class:`GraderResult` — score, pass/fail, details, failures and evidence. Graders
are selected per task from ``task.graders`` (each ``{"name": ..., "config": ...}``);
when a task names none, :func:`default_graders_for` picks a sensible set from the
task's category. An unknown grader name is a hard error, never silently skipped.

A grader that cannot measure (missing input) returns ``unmeasured=True`` with an
``UNKNOWN`` score — never ``0`` and never an inferred pass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

UNKNOWN = "UNKNOWN"


@dataclass
class GraderResult:
    grader: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    unmeasured: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "grader": self.grader,
            "score": UNKNOWN if self.unmeasured else round(self.score, 4),
            "passed": self.passed,
            "details": self.details,
            "failures": self.failures,
            "evidence": self.evidence,
            "unmeasured": self.unmeasured,
        }

    @classmethod
    def unmeasured_result(cls, grader: str, reason: str) -> "GraderResult":
        return cls(grader=grader, score=0.0, passed=False, unmeasured=True,
                   failures=[reason], details={"unmeasured": True})


@dataclass
class GradeContext:
    task: Any
    trajectory: Any
    final_output: str = ""
    environment: Any = None
    env_state: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    outcome: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


class Grader(ABC):
    #: the registry name
    name: str = "base"

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        #: the per-task grader configuration (from ``task.graders[].config``)
        self.config: dict[str, Any] = dict(config or {})

    @abstractmethod
    def grade(self, ctx: GradeContext) -> GraderResult:  # pragma: no cover - interface
        raise NotImplementedError


_REGISTRY: dict[str, Callable[[dict[str, Any]], Grader]] = {}


def register_grader(name: str, factory: Callable[[dict[str, Any]], Grader]) -> None:
    _REGISTRY[name] = factory


def grader_names() -> list[str]:
    return sorted(_REGISTRY)


def build_grader(name: str, config: Optional[dict[str, Any]] = None) -> Grader:
    factory = _REGISTRY.get(name)
    if factory is None:
        raise KeyError(f"unknown grader '{name}' (available: {', '.join(grader_names())})")
    return factory(config or {})


def default_graders_for(task: Any) -> list[str]:
    """The graders a task category gets when it names none."""
    category = getattr(task, "category", "core")
    if category in ("finance",):
        return ["financial", "exact"]
    if category == "coding":
        return ["code", "state"]
    if category == "tools":
        return ["tool", "exact"]
    if category in ("safety", "adversarial"):
        return ["safety"]
    if category == "memory":
        return ["memory"]
    if category in ("research", "citations"):
        return ["research", "citation"]
    if category == "browser":
        return ["browser"]
    if category in ("planning", "long_horizon", "recovery", "parallel"):
        return ["tool", "state"]
    if category == "regression":
        return ["tool", "state", "safety"]
    return ["exact"]


def build_graders(task: Any) -> list[Grader]:
    specs = list(getattr(task, "graders", ()) or ())
    if not specs:
        specs = [{"name": n} for n in default_graders_for(task)]
    graders: list[Grader] = []
    for spec in specs:
        if isinstance(spec, str):
            spec = {"name": spec}
        name = spec.get("name")
        if not name:
            raise KeyError(f"task {getattr(task, 'id', '?')}: grader spec without a name")
        graders.append(build_grader(name, spec.get("config")))
    return graders


# Register the built-in graders on import (idempotent).
def _register_builtins() -> None:
    from .exact import ExactGrader
    from .state import StateGrader
    from .tool import ToolGrader
    from .research import ResearchGrader
    from .citation import CitationGrader
    from .financial import FinancialGrader
    from .code import CodeGrader
    from .browser import BrowserGrader
    from .memory import MemoryGrader
    from .safety import SafetyGrader
    from .semantic import SemanticGrader
    from .hallucination import HallucinationGrader

    for cls in (
        ExactGrader, StateGrader, ToolGrader, ResearchGrader, CitationGrader,
        FinancialGrader, CodeGrader, BrowserGrader, MemoryGrader, SafetyGrader,
        SemanticGrader, HallucinationGrader,
    ):
        register_grader(cls.name, cls)


_register_builtins()

__all__ = [
    "GradeContext",
    "Grader",
    "GraderResult",
    "UNKNOWN",
    "build_grader",
    "build_graders",
    "default_graders_for",
    "grader_names",
    "register_grader",
]
