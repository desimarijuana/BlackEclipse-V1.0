"""The strategy graph model — the authoring representation a visual builder emits.

This is the typed, serializable *graph* the Visual Strategy Builder edits. It is
NOT a general-purpose workflow graph: its nodes are strategy concerns (data,
indicators, logic, entry/exit, sizing, stops, risk) and it compiles to the ONE
canonical `StrategySpec` IR (`quant/compiler.py`). The IR — not the graph — is
the source of truth; a graph is equivalent to its compiled IR.

Kept deliberately small and pydantic-validated so an untrusted graph from a UI
or an agent is shape-checked before the compiler reasons about it.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

GRAPH_SCHEMA_VERSION = "1.0.0"


class StrategyIdentity(BaseModel):
    """The identity block a graph carries so it compiles to a full spec."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    asset_class: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    type: str
    version: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    from_port: str = Field(default="out", alias="fromPort")
    to_node: str = Field(alias="to")
    to_port: str = Field(default="in", alias="toPort")


class StrategyGraph(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(default=GRAPH_SCHEMA_VERSION, alias="schemaVersion")
    strategy: StrategyIdentity
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def parse_graph(source: Union[str, dict[str, Any]]) -> StrategyGraph:
    """Parse a strategy graph from JSON text or a dict."""
    if isinstance(source, str):
        data = json.loads(source)
    else:
        data = dict(source)
    if not isinstance(data, dict):
        raise ValueError("strategy graph must be an object")
    return StrategyGraph.model_validate(data)


__all__ = [
    "GRAPH_SCHEMA_VERSION",
    "GraphEdge",
    "GraphNode",
    "StrategyGraph",
    "StrategyIdentity",
    "parse_graph",
]
