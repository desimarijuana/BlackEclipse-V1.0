"""C5 one agent fabric: spawn, blackboard and deterministic synthesis."""

from .board import BoardStore
from .model import (
    MAX_CHILDREN,
    MAX_DEPTH,
    MAX_STEPS,
    MAX_TIMEOUT_S,
    MAX_TOKENS,
    ChildOutcome,
    SpawnBudget,
    SpawnSpec,
)
from .service import (
    reconcile_budget,
    spec_from_dict,
    spawn_child,
    spawn_many,
    synthesize,
)
from .tools import register_spawn_tools

__all__ = [
    "BoardStore",
    "ChildOutcome",
    "MAX_CHILDREN",
    "MAX_DEPTH",
    "MAX_STEPS",
    "MAX_TIMEOUT_S",
    "MAX_TOKENS",
    "SpawnBudget",
    "SpawnSpec",
    "reconcile_budget",
    "register_spawn_tools",
    "spec_from_dict",
    "spawn_child",
    "spawn_many",
    "synthesize",
]
