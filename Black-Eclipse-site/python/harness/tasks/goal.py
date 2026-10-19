"""Goal intake — a request becomes a durable contract, deterministically (W8.1).

Round 4's product loop starts here. `intake_goal` turns an ordinary request into
a `GoalContract` (objective, deliverables, constraints, acceptance, budgets) plus
a `TaskType` key, using ONLY deterministic vocabulary — no model call ever
decides what a goal is, what it must deliver or how it is verified.

The contract is DATA on the durable task (see `model.py`/`store.py`), never a
prompt: the scheduler reads it to pick the completion verifier (W8.4), to enforce
budgets (W8.6) and to end an unverifiable task BLOCKED with the exact missing
evidence (W8.5). `durable_decision` is the W8.2 rule that decides whether a
request should become a durable task at all; the chat path may ask the ONE
clarifying question an ambiguous request earns instead of guessing.

PURE module: no I/O, no model, no store access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .model import (
    AcceptanceCriterionInput,
    MAX_DELIVERABLES,
    MAX_GOAL_ACCEPTANCE,
    MAX_GOAL_CONSTRAINTS,
    GoalContract,
    TaskBudget,
    TaskType,
)

#: How many inferred deliverables/acceptance lines a contract may carry. The
#: pydantic contracts enforce the same caps; these keep the inference bounded.
MAX_INFERRED_STEPS = 6


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'\-]*", (text or "").lower())


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    """Phrase match on word boundaries (never a raw substring)."""
    for phrase in phrases:
        if " " in phrase:
            if phrase in text:
                return True
        elif re.search(rf"\b{re.escape(phrase)}\b", text):
            return True
    return False


# Ordered most-specific-first; the FIRST matching class wins. Every phrase is
# matched on word boundaries so "performance" never matches "form".
_TASK_TYPE_RULES: tuple[tuple[TaskType, tuple[str, ...]], ...] = (
    (TaskType.CODE, (
        "build", "implement", "code", "refactor", "fix", "debug", "compile",
        "script", "program", "app", "application", "api", "endpoint", "function",
        "class", "component", "module", "library", "cli", "website", "web app",
        "tests", "unit test", "integration test", "bug", "patch",
        # UI construction (the W0 clock class of request): a widget/page change
        # is code work even when it never says "code".
        "widget", "dashboard", "page", "route",
    )),
    (TaskType.WORKFLOW, (
        "automate", "automation", "schedule", "recurring", "every day", "daily",
        "weekly", "pipeline", "workflow", "monitor", "trigger", "cron", "etl",
    )),
    # A named production verb ("write a report") makes the DOCUMENT the goal —
    # checked before the research words it may also contain.
    (TaskType.DOCUMENT, (
        "report", "document", "memo", "write up", "write-up", "draft",
        "summary", "whitepaper", "proposal", "plan document", "minutes",
    )),
    (TaskType.FINANCE, (
        "portfolio", "valuation", "backtest", "earnings", "stock", "market",
        "price", "dividend", "risk", "allocation", "return", "sharpe", "financial",
        "p&l", "pnl", "sec filing",
    )),
    (TaskType.RESEARCH, (
        "research", "investigate", "find out", "gather", "compare", "sources",
        "cite", "citations", "evidence", "survey", "latest news",
        "look up", "search for", "deep dive",
    )),
)

# Explicit task-type names a caller may pass (never guessed from prose alone).
_TASK_TYPE_ALIASES: dict[str, TaskType] = {
    "code": TaskType.CODE, "coding": TaskType.CODE, "software": TaskType.CODE,
    "research": TaskType.RESEARCH, "investigation": TaskType.RESEARCH,
    "document": TaskType.DOCUMENT, "doc": TaskType.DOCUMENT, "writing": TaskType.DOCUMENT,
    "workflow": TaskType.WORKFLOW, "automation": TaskType.WORKFLOW,
    "finance": TaskType.FINANCE, "financial": TaskType.FINANCE,
    "general": TaskType.GENERAL, "other": TaskType.GENERAL,
}

# Verb + object ⇒ an explicit deliverable. The captured object is trimmed at the
# first clause boundary so "build a greeting app that shows X" names the app.
_DELIVERABLE_RE = re.compile(
    r"\b(?:build|create|write|make|implement|add|develop|generate|produce|draft)\s+"
    r"(?:me\s+|us\s+)?(?:a\s+|an\s+|the\s+|new\s+)?"
    r"(?:(?:small|simple|basic|little|tiny|minimal)\s+)?"
    r"([a-z0-9][^,.;\n]{2,80}?)(?=\s+(?:that|which|for|with|using|to|and|so|in|on|from|by)\b|[,.;\n]|$)",
    re.IGNORECASE,
)

# Markers that make work long-horizon even without an explicit deliverable list.
_MULTI_STEP_RE = re.compile(
    r"(\bthen\b|\bafter that\b|\bfirst\b|\bstep\s*\d\b|^\s*\d+[.)]\s|"
    r"\bend.to.end\b|\bentire\b|\bfull\b|\bcomplete\b|\bmulti.step\b)",
    re.IGNORECASE,
)

_ACCEPTANCE_SIGNALS: dict[str, tuple[str, ...]] = {
    # NOTE: the bare verb "build" is deliberately absent — "build me an app"
    # names the WORK, not a build check. Only build-specific phrases demand
    # build proof.
    "tests pass": ("test", "tests", "pytest", "unit test", "suite",
                   "the tests pass"),
    "the project builds without errors": ("compiles", "bundle", "builds",
                                           "build passes", "npm run build",
                                           "production build",
                                           "builds without errors"),
    "the type check passes": ("typecheck", "type check", "tsc", "types"),
    "lint is clean": ("lint", "eslint", "ruff"),
    "the program runs and produces its output": ("run it", "runs", "execute",
                                                 "launch", "start it"),
}


def classify_task_type(request: str) -> TaskType:
    """The deterministic task-type key for a request (never a model call)."""
    text = (request or "").lower()
    for task_type, phrases in _TASK_TYPE_RULES:
        if _has_any(text, phrases):
            return task_type
    return TaskType.GENERAL


def _coerce_task_type(value: Optional[TaskType | str]) -> Optional[TaskType]:
    if value is None:
        return None
    if isinstance(value, TaskType):
        return value
    return _TASK_TYPE_ALIASES.get(str(value).strip().lower())


def _clean_lines(values: Any, *, cap: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        line = str(raw or "").strip()[:500]
        key = line.lower()
        if not line or key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= cap:
            break
    return out


def infer_deliverables(request: str, *, cap: int = MAX_INFERRED_STEPS) -> list[str]:
    """Object phrases of build/create-style clauses; never invented, never more
    than `cap`."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _DELIVERABLE_RE.finditer(request or ""):
        phrase = re.sub(r"\s+", " ", match.group(1)).strip(" -")
        key = phrase.lower()
        if not phrase or key in seen:
            continue
        seen.add(key)
        out.append(phrase[:120])
        if len(out) >= cap:
            break
    return out


def infer_acceptance(request: str, task_type: TaskType) -> list[str]:
    """Deterministic acceptance lines derived from the request's own words.

    CODE gets a base "the produced files exist" plus a line per check the
    request names (tests/build/typecheck/lint/run); the SAME words drive the
    code verifier's required evidence, so acceptance and verification cannot
    drift apart. Other types get one structural line each.
    """
    text = (request or "").lower()
    if task_type is TaskType.CODE:
        lines = ["the produced files exist"]
        for line, signals in _ACCEPTANCE_SIGNALS.items():
            if _has_any(text, signals):
                lines.append(line)
        return lines
    if task_type is TaskType.RESEARCH:
        return ["claims trace to named sources"]
    if task_type is TaskType.DOCUMENT:
        return ["the document artifact is delivered"]
    if task_type is TaskType.WORKFLOW:
        return ["the workflow completed with an observable result"]
    if task_type is TaskType.FINANCE:
        return ["financial claims carry provenance"]
    return ["the requested result is delivered"]


@dataclass
class GoalIntake:
    """What `intake_goal` concluded about one request."""

    contract: GoalContract
    task_type: TaskType
    title: str
    questions: list[str] = field(default_factory=list)
    ambiguous: bool = False
    durable: bool = False
    durable_reason: str = ""

    @property
    def criteria(self) -> list[AcceptanceCriterionInput]:
        """The acceptance lines as task criteria (deduped, bounded)."""
        return [AcceptanceCriterionInput(text=line) for line in self.contract.acceptance]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.model_dump(by_alias=True),
            "taskType": self.task_type.value,
            "title": self.title,
            "questions": list(self.questions),
            "ambiguous": self.ambiguous,
            "durable": self.durable,
            "durableReason": self.durable_reason,
        }


def durable_decision(
    contract: GoalContract, task_type: TaskType, request: str,
) -> tuple[bool, str]:
    """The W8.2 rule: does this request deserve a durable task?

    Long-horizon, multi-deliverable or resumable work ⇒ a task; a one-line
    answer stays a single turn. Deterministic and explainable — the reason is
    returned, never hidden.
    """
    if task_type is TaskType.CODE:
        return True, "code work is built, run and verified as a durable task"
    if task_type is TaskType.WORKFLOW:
        return True, "workflows run and resume as durable tasks"
    if len(contract.deliverables) >= 2:
        return True, "multiple deliverables"
    if contract.budgets is not None:
        return True, "an explicit budget was declared"
    if _MULTI_STEP_RE.search(request or ""):
        return True, "the request describes multi-step work"
    return False, "a single short result does not need a durable task"


def intake_goal(
    request: str,
    *,
    task_type: Optional[TaskType | str] = None,
    deliverables: Optional[list[str]] = None,
    constraints: Optional[list[str]] = None,
    acceptance: Optional[list[str]] = None,
    budgets: Optional[dict[str, Any] | TaskBudget] = None,
    title: Optional[str] = None,
) -> GoalIntake:
    """Turn a request into a `GoalIntake` — contract, type, questions, verbosity.

    Explicit fields always win over inference. When neither an explicit nor an
    inferred deliverable/acceptance exists, the intake is AMBIGUOUS and carries
    exactly ONE clarifying question instead of guessing (W8.1).
    """
    text = (request or "").strip()
    resolved_type = _coerce_task_type(task_type) or classify_task_type(text)

    explicit_deliverables = _clean_lines(deliverables, cap=MAX_DELIVERABLES)
    inferred_deliverables = [] if explicit_deliverables else infer_deliverables(text)
    clean_deliverables = explicit_deliverables or inferred_deliverables

    explicit_acceptance = _clean_lines(acceptance, cap=MAX_GOAL_ACCEPTANCE)
    clean_acceptance = explicit_acceptance or infer_acceptance(text, resolved_type)

    clean_constraints = _clean_lines(constraints, cap=MAX_GOAL_CONSTRAINTS)

    clean_budgets: Optional[TaskBudget] = None
    if isinstance(budgets, TaskBudget):
        clean_budgets = budgets
    elif isinstance(budgets, dict) and budgets:
        clean_budgets = TaskBudget(**budgets)

    contract = GoalContract(
        objective=text, deliverables=clean_deliverables,
        constraints=clean_constraints, acceptance=clean_acceptance,
        budgets=clean_budgets,
    )

    questions: list[str] = []
    if not text and not explicit_deliverables and not explicit_acceptance:
        questions.append("What should Eclipse produce? A one-line description is enough.")
    elif (not text and not explicit_deliverables) or (
        len(_words(text)) <= 3 and not explicit_deliverables
        and not explicit_acceptance
    ):
        questions.append(
            "Should Eclipse produce anything specific for this, or just answer it?"
        )
    ambiguous = bool(questions)

    durable, reason = durable_decision(contract, resolved_type, text)
    if not text and not explicit_deliverables:
        durable, reason = False, "there is nothing to execute yet"

    clean_title = (title or "").strip()
    if not clean_title:
        clean_title = (text[:120] or "Goal").strip()
        if clean_title and len(clean_title) == 120:
            clean_title = clean_title[:117] + "..."

    return GoalIntake(
        contract=contract, task_type=resolved_type, title=clean_title,
        questions=questions, ambiguous=ambiguous, durable=durable,
        durable_reason=reason,
    )


def budget_violations(
    budgets: Optional[TaskBudget],
    *,
    elapsed_ms: Optional[int] = None,
    tool_calls: Optional[int] = None,
    tokens: Optional[int] = None,
    model_steps: Optional[int] = None,
) -> list[str]:
    """The contract's caps this outcome violated, in plain words (W8.6).

    Only measurable facts are compared; a `None` observation never violates a
    cap (an unmeasured dimension is not a violation).
    """
    if budgets is None:
        return []
    violations: list[str] = []
    if budgets.max_duration_ms is not None and elapsed_ms is not None:
        if elapsed_ms > budgets.max_duration_ms:
            violations.append(
                f"elapsed {int(elapsed_ms)} ms exceeds the contract budget "
                f"of {budgets.max_duration_ms} ms"
            )
    if budgets.max_tool_calls is not None and tool_calls is not None:
        if tool_calls > budgets.max_tool_calls:
            violations.append(
                f"{int(tool_calls)} tool calls exceed the contract budget "
                f"of {budgets.max_tool_calls}"
            )
    if budgets.max_tokens is not None and tokens is not None:
        if tokens > budgets.max_tokens:
            violations.append(
                f"{int(tokens)} tokens exceed the contract budget "
                f"of {budgets.max_tokens}"
            )
    if budgets.max_model_steps is not None and model_steps is not None:
        if model_steps > budgets.max_model_steps:
            violations.append(
                f"{int(model_steps)} model steps exceed the contract budget "
                f"of {budgets.max_model_steps}"
            )
    return violations


__all__ = [
    "GoalIntake",
    "budget_violations",
    "classify_task_type",
    "durable_decision",
    "infer_acceptance",
    "infer_deliverables",
    "intake_goal",
]
