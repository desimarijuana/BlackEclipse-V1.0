"""Least-privilege authorization for A2A.

An agent's powers are exactly what its `AgentDefinition` declares — never what
spawned it, never what another agent has. The flow is:

    Agent → Task → Capability → Tool → Action

Every seam that grants something (a tool to run, a delegation, an effectful
action) asks this module first. It is pure and deterministic, so it is testable
without a runtime. Trading capabilities are classified as approval-gated by
policy, so a research agent can never place a trade merely by delegating to one.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .model import AgentDefinition

#: Capability nouns that touch the real world / an account and therefore require
#: an explicit, single-use approval per the Eclipse safety model.
APPROVAL_GATED_CAPABILITIES: frozenset[str] = frozenset(
    {
        "trade_execution", "order_placement", "live_trading", "broker_action",
        "capital_transfer", "withdrawal", "external_action", "deployment",
    }
)
TRADING_CAPABILITIES: frozenset[str] = frozenset(
    {"trade_execution", "order_placement", "live_trading", "broker_action"}
)

#: Effects that are never granted by capability alone — they need an approval.
WRITE_EFFECTS: frozenset[str] = frozenset({"write", "external_action", "destructive"})


def has_capability(definition: AgentDefinition, capability: str) -> bool:
    return capability in definition.capabilities


def capabilities_of(definition: AgentDefinition) -> frozenset[str]:
    return frozenset(definition.capabilities)


def declared_tools(definition: AgentDefinition) -> Optional[frozenset[str]]:
    """The agent's tool allowlist, or None when it inherits its surface."""
    return None if definition.tools is None else frozenset(definition.tools)


def permits_tool(definition: AgentDefinition, tool: str) -> bool:
    allowed = declared_tools(definition)
    return True if allowed is None else tool in allowed


def permitted_tools(definition: AgentDefinition, requested: Iterable[str]) -> list[str]:
    """The requested tools the agent is actually allowed to use (intersection)."""
    allowed = declared_tools(definition)
    if allowed is None:
        return list(requested)
    return [t for t in requested if t in allowed]


def can_delegate(definition: AgentDefinition, child_agent_id: str) -> bool:
    """Whether `definition` may hand work to `child_agent_id`."""
    if not definition.can_delegate:
        return False
    if definition.allowed_delegates:
        return child_agent_id in definition.allowed_delegates
    return True


def requires_approval(capability: str) -> bool:
    return capability in APPROVAL_GATED_CAPABILITIES


def is_trading(capability: str) -> bool:
    return capability in TRADING_CAPABILITIES


def action_allowed(definition: AgentDefinition, *, capability: Optional[str], tool: Optional[str],
                   effect: Optional[str], approved: bool = False) -> tuple[bool, str]:
    """The ONE authorization decision for an A2A-originated action.

    Returns (allowed, reason). Fail-closed: anything not explicitly permitted is
    refused with a reason a caller can surface verbatim.
    """
    if definition.status.value != "ACTIVE":
        return False, f"{definition.id} is not active"
    if capability is not None and not has_capability(definition, capability):
        return False, f"{definition.id} does not hold the {capability!r} capability"
    if capability is not None and requires_approval(capability) and not approved:
        return False, f"{capability!r} requires an explicit approval"
    if tool is not None and not permits_tool(definition, tool):
        return False, f"{definition.id} is not allowed to use {tool!r}"
    if effect is not None and effect in WRITE_EFFECTS and not approved:
        return False, f"{effect!r} actions require an explicit approval"
    return True, "allowed"


def intersection(parent: AgentDefinition, child: AgentDefinition) -> AgentDefinition:
    """A child's effective powers are parent ∩ child — never a superset.

    Used by `spawn_agent`: a spawned agent inherits only the tools and
    capabilities BOTH declare, and can never delegate more than its parent could.
    """
    parent_tools = declared_tools(parent)
    child_tools = declared_tools(child)
    if parent_tools is None and child_tools is None:
        tools = None
    else:
        tools = sorted((parent_tools or frozenset()) & (child_tools or frozenset()))
    return child.model_copy(update={
        "tools": tools,
        "capabilities": sorted(capabilities_of(parent) & capabilities_of(child)),
        "can_delegate": parent.can_delegate and child.can_delegate,
        "allowed_delegates": [c for c in child.allowed_delegates if c in parent.allowed_delegates]
        if parent.allowed_delegates else list(child.allowed_delegates),
    })


__all__ = [
    "APPROVAL_GATED_CAPABILITIES",
    "TRADING_CAPABILITIES",
    "WRITE_EFFECTS",
    "action_allowed",
    "can_delegate",
    "capabilities_of",
    "declared_tools",
    "has_capability",
    "intersection",
    "is_trading",
    "permitted_tools",
    "permits_tool",
    "requires_approval",
]
