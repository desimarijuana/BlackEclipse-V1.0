"""Evidence graph (Universal Financial Data Accuracy, §21).

The traceable relationship:

    Question → Claim → Derived metric → Financial fact → Source document

Every important claim is reachable back to the evidence that supports it. This
module builds that graph explicitly (nodes + typed edges) so a consumer can walk
from an answer to a source, and so an orphan — a claim with no supporting fact,
or a fact with no source — is detectable rather than invisible.

It reuses the Phase-4 claim/receipt identity where present; it does not invent a
second id scheme.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .model import DerivedMetric, FinancialFact

# Node kinds, in the §21 chain order.
NODE_KINDS = ("question", "claim", "derived_metric", "fact", "source_document")

# Edge kinds: parent → child in the chain.
EDGE_KINDS = ("supports", "derives_from", "sourced_from")


@dataclass
class Node:
    id: str
    kind: str
    label: str
    data: Optional[dict[str, Any]] = None


@dataclass
class Edge:
    source_id: str  # the parent (e.g. the claim)
    target_id: str  # the child it rests on (e.g. the fact)
    kind: str       # supports | derives_from | sourced_from


@dataclass
class EvidenceGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> str:
        self.nodes[node.id] = node
        return node.id

    def add_edge(self, source_id: str, target_id: str, kind: str) -> None:
        if kind not in EDGE_KINDS:
            raise ValueError(f"unknown edge kind {kind!r}")
        self.edges.append(Edge(source_id, target_id, kind))

    def children(self, node_id: str) -> list[str]:
        return [e.target_id for e in self.edges if e.source_id == node_id]

    def trace_to_sources(self, node_id: str) -> list[str]:
        """Every source_document node reachable from `node_id` (depth-first, cycle-safe)."""
        out: list[str] = []
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            children = self.children(current)
            if not children and self.nodes.get(current) is not None and self.nodes[current].kind == "source_document":
                out.append(current)
            stack.extend(children)
        return out

    def orphans(self) -> list[str]:
        """Facts with no source, or claims with no fact — the defects the graph exposes."""
        defects: list[str] = []
        for node in self.nodes.values():
            if node.kind == "fact":
                if not self.children(node.id):
                    defects.append(f"fact {node.id} has no source document")
            elif node.kind == "claim":
                kids = [self.nodes.get(c) for c in self.children(node.id)]
                if not any(k is not None and k.kind in ("fact", "derived_metric") for k in kids):
                    defects.append(f"claim {node.id} is not supported by any fact")
        return defects


def add_fact(graph: EvidenceGraph, fact: FinancialFact) -> str:
    """Add a fact and its source-document node (when it has one)."""
    fid = graph.add_node(Node(fact.fact_id, "fact", f"{fact.metric}={fact.value}",
                              {"metric": fact.metric, "definition": fact.definition, "value": fact.value}))
    if fact.source:
        sid = f"src:{fact.source}"
        if sid not in graph.nodes:
            graph.add_node(Node(sid, "source_document", str(fact.source), {"source_type": fact.source_type}))
        graph.add_edge(fid, sid, "sourced_from")
    return fid


def add_derived(graph: EvidenceGraph, derived: DerivedMetric) -> str:
    """Add a derived metric and derive_from edges to the facts it used."""
    did = graph.add_node(Node(f"calc:{derived.metric}:{derived.calculated_at}", "derived_metric",
                              f"{derived.metric} = {derived.value}", derived.to_dict()))
    for fact_id in derived.input_fact_ids:
        if fact_id in graph.nodes:
            graph.add_edge(did, fact_id, "derives_from")
    return did


def add_claim(graph: EvidenceGraph, claim_id: str, text: str, supporting_ids: list[str]) -> str:
    """Add a claim and support it from facts / derived metrics."""
    cid = graph.add_node(Node(claim_id, "claim", text))
    for child in supporting_ids:
        if child in graph.nodes:
            graph.add_edge(cid, child, "supports")
    return cid


__all__ = [
    "EDGE_KINDS",
    "NODE_KINDS",
    "Edge",
    "EvidenceGraph",
    "Node",
    "add_claim",
    "add_derived",
    "add_fact",
]
