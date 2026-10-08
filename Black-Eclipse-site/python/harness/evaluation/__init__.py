"""Eclipse Agent Evaluation System.

A first-class evaluation subsystem for the real Eclipse agent runtime. It runs
versioned, environment-isolated tasks through the REAL runtime, captures the
complete trajectory, grades it with a pluggable grader engine, aggregates trials
with statistics, persists everything, compares against baselines and detects
regressions — all honestly (an unmeasurable metric is ``UNKNOWN``, never ``0``, and
a gate never collapses to one blended score).

Public surface::

    from harness.evaluation import (
        EvaluationRunner, ScriptedAgentInvoker, ServiceAgentInvoker,
        EvaluationConfig, load_all_builtin, load_builtin_dataset, select_tasks,
        build_environment, Grader, GraderResult, build_graders,
        score_trial, check_thresholds, to_markdown, to_json,
        detect_regressions, mine_failure,
    )
"""

from __future__ import annotations

from .config import (
    GRADER_API_VERSION,
    TASK_SCHEMA_VERSION,
    TRAJECTORY_FORMAT_VERSION,
    EvaluationConfig,
)
from .environments import Environment, build_environment, environment_kinds
from .graders import (
    GradeContext,
    Grader,
    GraderResult,
    UNKNOWN,
    build_grader,
    build_graders,
    grader_names,
    register_grader,
)
from .regression import DEFAULT_GATES, RegressionGate, detect_regressions
from .report import to_html, to_json, to_jsonl, to_markdown, write_report
from .runner import (
    EvaluationRunner,
    InvocationResult,
    ScriptedAgentInvoker,
    ServiceAgentInvoker,
    SuiteResult,
    TaskResult,
    TrialResult,
    install_model_seam,
)
from .scoring import (
    DEFAULT_THRESHOLDS,
    DIMENSIONS,
    EvaluationScore,
    Threshold,
    check_thresholds,
    score_trial,
)
from .stats import TrialStats, aggregate_trials
from .store import EvaluationStore
from .tasks import (
    CATEGORIES,
    DIFFICULTIES,
    Dataset,
    EvaluationTask,
    TaskLimits,
    available_datasets,
    load_all_builtin,
    load_builtin_dataset,
    load_dataset,
    select_tasks,
)
from .taxonomy import FailureLabel, classify_failure
from .trajectory import Trajectory, TrajectoryEvent

__all__ = [
    "CATEGORIES",
    "DEFAULT_GATES",
    "DEFAULT_THRESHOLDS",
    "DIFFICULTIES",
    "DIMENSIONS",
    "Dataset",
    "Environment",
    "EvaluationConfig",
    "EvaluationRunner",
    "EvaluationScore",
    "EvaluationStore",
    "EvaluationTask",
    "FailureLabel",
    "GRADER_API_VERSION",
    "GradeContext",
    "Grader",
    "GraderResult",
    "InvocationResult",
    "RegressionGate",
    "ScriptedAgentInvoker",
    "ServiceAgentInvoker",
    "SuiteResult",
    "TASK_SCHEMA_VERSION",
    "TRAJECTORY_FORMAT_VERSION",
    "TaskLimits",
    "TaskResult",
    "Threshold",
    "Trajectory",
    "TrajectoryEvent",
    "TrialResult",
    "TrialStats",
    "UNKNOWN",
    "aggregate_trials",
    "available_datasets",
    "build_environment",
    "build_grader",
    "build_graders",
    "check_thresholds",
    "classify_failure",
    "detect_regressions",
    "environment_kinds",
    "grader_names",
    "install_model_seam",
    "load_all_builtin",
    "load_builtin_dataset",
    "load_dataset",
    "register_grader",
    "score_trial",
    "select_tasks",
    "to_html",
    "to_json",
    "to_jsonl",
    "to_markdown",
    "write_report",
]
