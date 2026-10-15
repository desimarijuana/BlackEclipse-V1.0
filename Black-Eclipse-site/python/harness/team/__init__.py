"""Bot Team Orchestration — a composition layer over the existing runtime.

Five native multi-agent capabilities, none of which forks the execution plane:

  * delegation between bots (through the A2A layer, least privilege preserved);
  * concurrent specialist execution (the existing TaskScheduler, bounded per bot);
  * a validated, dependency-aware task graph (the existing Task/Plan runtime);
  * evidence-based conflict reconciliation (deterministic, never voting/averaging);
  * independent quality review with bounded repair and re-verification.

A delegated subtask IS a normal `service.run` dispatched by the scheduler. A
message and a conflict are durable rows. There is no second agent loop, no second
provider router and no second task database.
"""

from __future__ import annotations

from .bootstrap import install_team_layer
from .conflicts import ReconcileResult, detect_conflicts, reconcile, reconcile_async
from .graph import validate_graph
from .model import (
    ConflictKind,
    ConflictStatus,
    OptionalFailurePolicy,
    RepairAttempt,
    ReviewFinding,
    ReviewOutcome,
    ReviewReport,
    Severity,
    Strictness,
    TeamConflict,
    TeamDefinition,
    TeamFinding,
    TeamMember,
    TeamPolicy,
    TeamRun,
    TeamRunStatus,
    TeamSubtask,
    TeamSubtaskStatus,
)
from .review import ReviewInput, repair_plan, review
from .service import TeamError, TeamService
from .store import TeamStore
from .tools import TEAM_TOOLS, register_team_tools, team_for

__all__ = [
    "ConflictKind",
    "ConflictStatus",
    "OptionalFailurePolicy",
    "ReconcileResult",
    "RepairAttempt",
    "ReviewFinding",
    "ReviewInput",
    "ReviewOutcome",
    "ReviewReport",
    "Severity",
    "Strictness",
    "TEAM_TOOLS",
    "TeamConflict",
    "TeamDefinition",
    "TeamError",
    "TeamFinding",
    "TeamMember",
    "TeamPolicy",
    "TeamRun",
    "TeamRunStatus",
    "TeamService",
    "TeamStore",
    "TeamSubtask",
    "TeamSubtaskStatus",
    "detect_conflicts",
    "install_team_layer",
    "reconcile",
    "reconcile_async",
    "register_team_tools",
    "repair_plan",
    "review",
    "team_for",
    "validate_graph",
]
