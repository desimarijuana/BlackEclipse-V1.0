"""Registration of the adapter node packs added after the core registry.

Every pack here is a thin adapter over a runtime that already exists — SKILL
execution, a single bounded structured model call, the committee runner, the one
channel service, the approval store, the memory store. None of them own a loop.

Keeping the wiring here (rather than in `nodes.py`) is what let the packs grow
while `nodes.py` stayed under the module-size ceiling. `build_default_registry`
calls `register_extra_packs` once, after the core packs, so registration order
stays deterministic.
"""

from __future__ import annotations

from typing import Any

from .agent_structured_nodes import build_structured_agent_nodes
from .approval_nodes import build_approval_nodes
from .memory_nodes import build_memory_nodes
from .output_nodes import build_output_nodes
from .skill_nodes import build_skill_nodes
from .team_nodes import build_team_nodes
from .utility_nodes import build_utility_nodes

#: Ordered so a duplicate id is caught against the pack that came before it.
PACKS = (
    # A skill node is a thin adapter over the existing SKILL runtime
    # (`execute_skill`): same permissions, same version resolution.
    build_skill_nodes,
    # One bounded structured model call each — no tools, no agent loop.
    build_structured_agent_nodes,
    # Pure primitives (assert / fallback / extract) and the memory adapters.
    build_utility_nodes,
    build_memory_nodes,
    # Committee run + the two output adapters (chart spec, channel notify).
    build_team_nodes,
    build_output_nodes,
    # The human-approval gate (durable runs pause and re-check).
    build_approval_nodes,
)


def register_extra_packs(registry: Any) -> None:
    """Register every adapter pack, in the order listed in `PACKS`."""
    for builder in PACKS:
        for definition in builder():
            registry.register(definition)


__all__ = ["PACKS", "register_extra_packs"]
