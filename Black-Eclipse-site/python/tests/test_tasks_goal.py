"""Round 4 (W8.1/W8.6): the deterministic goal intake and contract budgets.

The intake is PURE vocabulary — these tests pin the classification, the
deliverable/acceptance inference, the ONE-question ambiguity rule, the durable
decision and the budget comparison. Nothing here needs a model or a run.
"""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.tasks.goal import (
    budget_violations,
    classify_task_type,
    durable_decision,
    intake_goal,
)
from harness.tasks.manager import TaskError, TaskManager
from harness.tasks.model import (
    CreatePlanInput,
    CreateTaskInput,
    GoalContract,
    TaskBudget,
    TaskType,
)
from harness.tasks.store import TaskStore


# ── Task-type classification ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("build me a small greeting app with tests", TaskType.CODE),
        ("add a multi-zone world clock to the dashboard", TaskType.CODE),
        ("refactor the scheduler and fix the retry bug", TaskType.CODE),
        ("research the best EV charging networks and cite sources", TaskType.RESEARCH),
        ("write a report summarizing the market landscape", TaskType.DOCUMENT),
        ("automate a daily pipeline that monitors filings", TaskType.WORKFLOW),
        ("compare the portfolio risk to the benchmark", TaskType.FINANCE),
        ("what is the weather", TaskType.GENERAL),
    ],
)
def test_classify_task_type(phrase, expected):
    assert classify_task_type(phrase) is expected


def test_explicit_task_type_wins_over_inference():
    intake = intake_goal("build an app", task_type="research")
    assert intake.task_type is TaskType.RESEARCH


# ── Intake: deliverables, acceptance, ambiguity, durability ──────────────────


def test_intake_derives_deliverables_and_acceptance_from_words():
    intake = intake_goal("build a small greeting app with tests")
    assert intake.task_type is TaskType.CODE
    assert "greeting app" in intake.contract.deliverables
    # The VERB "build" must not demand a build record — only a build check does.
    assert intake.contract.acceptance == ["the produced files exist", "tests pass"]
    assert intake.durable is True
    assert intake.ambiguous is False


def test_explicit_fields_win_over_inference():
    intake = intake_goal(
        "build an app",
        deliverables=["greeting.py"],
        acceptance=["the file exists and prints hello"],
        constraints=["no new dependencies"],
        budgets={"max_tool_calls": 5},
    )
    assert intake.contract.deliverables == ["greeting.py"]
    assert intake.contract.acceptance == ["the file exists and prints hello"]
    assert intake.contract.constraints == ["no new dependencies"]
    assert intake.contract.budgets == TaskBudget(max_tool_calls=5)


def test_ambiguous_request_earns_exactly_one_question():
    intake = intake_goal("help")
    assert intake.ambiguous is True
    assert len(intake.questions) == 1
    assert intake.durable is False


def test_empty_request_asks_what_to_produce():
    intake = intake_goal("   ")
    assert intake.ambiguous is True
    assert "produce" in intake.questions[0].lower()


def test_durable_decision_reasons():
    contract = GoalContract(objective="x", deliverables=["a", "b"])
    durable, reason = durable_decision(contract, TaskType.GENERAL, "do a and b")
    assert durable is True and "multiple deliverables" in reason
    durable, reason = durable_decision(GoalContract(objective="q"), TaskType.GENERAL, "quick q")
    assert durable is False and "single short result" in reason
    durable, reason = durable_decision(
        GoalContract(objective="q", budgets=TaskBudget(max_tool_calls=3)),
        TaskType.GENERAL, "q",
    )
    assert durable is True and "budget" in reason


# ── Budgets ───────────────────────────────────────────────────────────────────


def test_budget_violations_names_each_exceeded_cap():
    budgets = TaskBudget(max_duration_ms=1000, max_tool_calls=2, max_tokens=50)
    violations = budget_violations(
        budgets, elapsed_ms=2000, tool_calls=2, tokens=51
    )
    assert len(violations) == 2
    assert any("2000 ms" in v for v in violations)
    assert any("51 tokens" in v for v in violations)


def test_model_step_budget_is_enforced_and_parallel_workers_declared():
    budgets = TaskBudget(max_model_steps=3, max_parallel_workers=2)
    violations = budget_violations(budgets, model_steps=5)
    assert violations and "5 model steps exceed the contract budget of 3" in violations[0]
    assert budget_violations(budgets, model_steps=3) == []


def test_budget_violations_are_honest_about_unmeasured_facts():
    budgets = TaskBudget(max_tokens=10)
    assert budget_violations(budgets, tool_calls=999) == []
    assert budget_violations(None, tokens=10_000) == []


# ── Persistence: the contract is DATA on the task ────────────────────────────


@pytest.fixture()
def manager(tmp_path):
    return TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))


def test_task_round_trips_type_and_contract_and_creates_criteria(manager):
    plan = manager.create_plan(CreatePlanInput(name="goal"))
    contract = GoalContract(
        objective="build a greeting app", deliverables=["greeting app"],
        acceptance=["the produced files exist", "tests pass"],
    )
    task = manager.create_task(CreateTaskInput(
        title="greeting app", plan_id=plan.id, objective=contract.objective,
        task_type=TaskType.CODE, goal_contract=contract,
    ))
    # The contract's acceptance lines became the task's criteria (deduped).
    texts = [c.text for c in manager.list_criteria(task.id)]
    assert texts == ["the produced files exist", "tests pass"]

    fresh = manager.get_task(task.id)
    assert fresh.task_type is TaskType.CODE
    assert fresh.goal_contract is not None
    assert fresh.goal_contract.deliverables == ["greeting app"]
    assert fresh.goal_contract.acceptance == ["the produced files exist", "tests pass"]

    # A restart (a NEW store/manager over the same DB) reads it back.
    reopened = TaskManager(TaskStore(AgentMemoryStore(manager._store._store.path)))  # noqa: SLF001
    assert reopened.get_task(task.id).goal_contract.deliverables == ["greeting app"]


def test_update_validates_task_type_and_contract(manager):
    plan = manager.create_plan(CreatePlanInput(name="p"))
    task = manager.create_task(CreateTaskInput(title="t", plan_id=plan.id))

    updated = manager.update_task(task.id, {
        "taskType": "code",
        "goalContract": {"objective": "x", "acceptance": ["tests pass"]},
    })
    assert updated.task_type is TaskType.CODE
    assert updated.goal_contract.acceptance == ["tests pass"]

    with pytest.raises(TaskError) as err:
        manager.update_task(task.id, {"taskType": "not-a-type"})
    assert err.value.code == "VALIDATION_ERROR"
    with pytest.raises(TaskError) as err:
        manager.update_task(task.id, {"goalContract": {"bogusField": 1}})
    assert err.value.code == "VALIDATION_ERROR"


def test_explicit_criteria_are_not_duplicated_by_the_contract(manager):
    plan = manager.create_plan(CreatePlanInput(name="p"))
    task = manager.create_task(CreateTaskInput(
        title="t", plan_id=plan.id,
        acceptance_criteria=[{"text": "tests pass"}],
        goal_contract=GoalContract(acceptance=["tests pass", "the files exist"]),
    ))
    texts = [c.text for c in manager.list_criteria(task.id)]
    assert texts == ["tests pass", "the files exist"]
