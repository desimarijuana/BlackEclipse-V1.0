"""Learning journey / provenance graph (Phase 6).

A **derived read model** — not a second source of truth. Every node and edge is
projected from canonical eclipse-memory / agent-memory rows; nothing is stored
here and no writes go through it. The graph exists so a user can ask "how did
this skill or memory come to exist?" and see the chain.

Safety:
  * Secrets never appear: node labels/ids are ids and type metadata; memory
    content is truncated and only included when it is not secret-shaped.
  * Scope isolation is respected: the caller's readable scopes filter the set.
  * Archival is reversible: archived/superseded/rejected items are included as
    *inactive* nodes with a status, never deleted.
  * Node/edge counts are bounded so a large store cannot blow up the payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _now_iso() -> str:
    # Match the store's timestamp format so generatedAt/watermark compare
    # lexicographically with canonical record timestamps.
    from .eclipse_memory.db import now_iso  # noqa: PLC0415

    return now_iso()

MAX_NODES = 400
MAX_EDGES = 800
MAX_LABEL_CHARS = 120

# Node kinds and their status vocabulary.
NODE_KINDS = (
    "memory", "skill", "skill_version", "correction", "mistake",
    "learning_candidate", "evaluation", "promotion", "execution", "session",
    # Phase 10: a repeated-problem candidate and its code-change attempts.
    "evolution_candidate", "evolution_attempt",
)

# Edge relations.
EDGE_RELATIONS = (
    "created_from", "corrected_by", "superseded_by", "used_in",
    "derived_from", "promoted_from", "evaluated_by", "related_to",
    "attempted_on",
)


@dataclass
class GraphNode:
    id: str
    kind: str
    label: str
    status: str = "active"
    scope: Optional[str] = None
    createdAt: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "label": self.label,
            "status": self.status, "scope": self.scope,
            "createdAt": self.createdAt, **self.meta,
        }


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "relation": self.relation}


def _label(text: Optional[str]) -> str:
    if not text:
        return ""
    clean = " ".join(str(text).split())
    return clean[:MAX_LABEL_CHARS] + ("…" if len(clean) > MAX_LABEL_CHARS else "")


def build_learning_journey(
    store: Any,
    *,
    scope_id: Optional[str] = None,
    readable_scopes: Optional[list[str]] = None,
    kinds: Optional[list[str]] = None,
    statuses: Optional[list[str]] = None,
    since: Optional[str] = None,
) -> dict[str, Any]:
    """Project the learning journey from canonical rows.

    `scope_id`/`readable_scopes` restrict the projected set (scope isolation).
    `kinds`/`statuses`/`since` are user filters. Derived only; never writes.
    """
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    # Edges discovered while walking rows; resolved after ALL nodes are known, so
    # a forward reference (a supersession target listed later) still links.
    pending_edges: list[tuple[str, str, str]] = []
    want_kinds = set(kinds) if kinds else None
    want_statuses = set(statuses) if statuses else None

    def allow(node_kind: str, node_status: str, created: Optional[str]) -> bool:
        if want_kinds and node_kind not in want_kinds:
            return False
        if want_statuses and node_status not in want_statuses:
            return False
        if since and created and created < since:
            return False
        return True

    def add(node: GraphNode) -> None:
        if len(nodes) >= MAX_NODES:
            return
        if not allow(node.kind, node.status, node.createdAt):
            return
        nodes[node.id] = node

    def link(source: str, target: str, relation: str) -> None:
        if source and target and source != target:
            pending_edges.append((source, target, relation))

    # ── Memories ────────────────────────────────────────────────────────────
    try:
        memories = store.list_memories(limit=MAX_NODES)
    except Exception:  # noqa: BLE001 - a partial store still yields a graph
        memories = []
    for memory in memories:
        if scope_id and memory.get("scope") == "user" and memory.get("scopeId") not in (None, scope_id):
            continue
        node = GraphNode(
            id=memory["id"], kind="memory",
            label=_label(memory.get("content")), status=memory.get("status", "active"),
            scope=memory.get("scope"), createdAt=memory.get("createdAt"),
            meta={
                "memoryType": memory.get("memoryType"),
                "authority": memory.get("authority"),
                "source": memory.get("source"),
                "confidence": memory.get("confidence"),
            },
        )
        add(node)
        if memory.get("supersededBy"):
            link(memory["id"], memory["supersededBy"], "superseded_by")
        if memory.get("sourceRunId"):
            link(memory["id"], f"session:{memory['sourceRunId']}", "created_from")

    # ── Skills + versions ───────────────────────────────────────────────────
    try:
        skills = store.list_skills()
    except Exception:  # noqa: BLE001
        skills = []
    for skill in skills:
        add(GraphNode(
            id=f"skill:{skill['id']}", kind="skill",
            label=_label(skill.get("name") or skill["id"]),
            status=skill.get("status", "active"), createdAt=skill.get("createdAt"),
            meta={"skillId": skill["id"], "category": skill.get("category")},
        ))
        try:
            versions = store.list_versions(skill["id"])
        except Exception:  # noqa: BLE001
            versions = []
        for version in versions:
            vid = f"skill:{skill['id']}@{version['version']}"
            add(GraphNode(
                id=vid, kind="skill_version",
                label=f"{skill['id']} v{version['version']}",
                status=version.get("status", "draft"), createdAt=version.get("createdAt"),
                meta={"skillId": skill["id"], "version": version["version"],
                      "evaluationStatus": version.get("evaluationStatus"),
                      "canaryState": version.get("canaryState")},
            ))
            link(vid, f"skill:{skill['id']}", "derived_from")
            # A patch names the base version it was authored against.
            if version.get("baseVersion"):
                link(vid, f"skill:{skill['id']}@{version['baseVersion']}", "created_from")

    # ── Learning candidates → skills ────────────────────────────────────────
    try:
        candidates = store.list_candidates(limit=MAX_NODES)
    except Exception:  # noqa: BLE001
        candidates = []
    for candidate in candidates:
        cid = f"candidate:{candidate['id']}"
        add(GraphNode(
            id=cid, kind="learning_candidate",
            label=_label(candidate.get("title")), status=candidate.get("status", "detected"),
            createdAt=candidate.get("createdAt"),
            meta={"candidateType": candidate.get("candidateType"),
                  "confidence": candidate.get("confidence")},
        ))
        if candidate.get("sourceRunId"):
            link(cid, f"session:{candidate['sourceRunId']}", "created_from")
        if candidate.get("resultingSkillId"):
            link(f"skill:{candidate['resultingSkillId']}", cid, "created_from")

    # ── Corrections ─────────────────────────────────────────────────────────
    try:
        corrections = store.list_corrections(limit=MAX_NODES)
    except Exception:  # noqa: BLE001
        corrections = []
    for correction in corrections:
        cid = f"correction:{correction['id']}"
        add(GraphNode(
            id=cid, kind="correction",
            label=_label(correction.get("correction")),
            status=correction.get("status", "recorded"), scope=correction.get("scope"),
            createdAt=correction.get("createdAt"),
        ))
        if correction.get("memoryId"):
            link(correction["memoryId"], cid, "corrected_by")
        if correction.get("runId"):
            link(cid, f"session:{correction['runId']}", "created_from")

    # ── Mistakes ────────────────────────────────────────────────────────────
    try:
        mistakes = store.list_mistakes(limit=MAX_NODES)
    except Exception:  # noqa: BLE001
        mistakes = []
    for mistake in mistakes:
        mid = f"mistake:{mistake['id']}"
        add(GraphNode(
            id=mid, kind="mistake",
            label=_label(mistake.get("category")), status="recorded",
            createdAt=mistake.get("createdAt"),
            meta={"category": mistake.get("category"), "severity": mistake.get("severity")},
        ))
        if mistake.get("runId"):
            link(mid, f"session:{mistake['runId']}", "created_from")
        if mistake.get("candidateId"):
            link(f"candidate:{mistake['candidateId']}", mid, "related_to")

    # ── Promotions ──────────────────────────────────────────────────────────
    try:
        promotions = store.list_promotion_requests()
    except Exception:  # noqa: BLE001
        promotions = []
    for promotion in promotions:
        pid = f"promotion:{promotion['id']}"
        add(GraphNode(
            id=pid, kind="promotion",
            label=_label(promotion.get("skillId")),
            status=promotion.get("status", "pending"), createdAt=promotion.get("createdAt"),
            meta={"skillId": promotion.get("skillId"), "reviewer": promotion.get("reviewer")},
        ))
        if promotion.get("skillId"):
            link(f"skill:{promotion['skillId']}", pid, "promoted_from")

    # ── Skill executions (Phase 5 freshness: show activity since learning) ───
    # Each execution is a derived node linked to the version it used and the
    # session it belongs to. Bounded; never writes.
    try:
        executions = store.list_executions(limit=MAX_NODES)
    except Exception:  # noqa: BLE001
        executions = []
    for execution in executions:
        eid = f"execution:{execution.get('runId') or execution.get('id')}"
        skill_id = execution.get("skillId")
        version = execution.get("version")
        add(GraphNode(
            id=eid, kind="execution",
            label=_label(f"{skill_id or 'skill'}@{version or '?'}"),
            status=execution.get("status", "running"), createdAt=execution.get("createdAt"),
            meta={
                "skillId": skill_id, "version": version,
                "outputValidated": execution.get("outputValidated"),
            },
        ))
        if skill_id and version:
            link(eid, f"skill:{skill_id}@{version}", "used_in")
        if execution.get("parentRunId"):
            link(eid, f"session:{execution['parentRunId']}", "created_from")

    # ── Evolution candidates + attempts (Phase 10) ──────────────────────────
    # A repeated-problem candidate and its attempts, EXTENDING this journey rather
    # than a second self-improvement screen. Best-effort: a store without the
    # evolution tables simply contributes nothing.
    try:
        evolution_candidates = _evolution_candidates(store)
    except Exception:  # noqa: BLE001
        evolution_candidates = []
    for candidate in evolution_candidates:
        cid = f"evolution:{candidate['id']}"
        add(GraphNode(
            id=cid, kind="evolution_candidate",
            label=_label(candidate.get("problemStatement")),
            status=candidate.get("status", "inert"), createdAt=candidate.get("createdAt"),
            meta={"sourceCategory": candidate.get("sourceCategory"),
                  "observedCount": candidate.get("observedCount"),
                  "refusalCode": candidate.get("refusalCode")},
        ))
        if candidate.get("createdByRunId"):
            link(cid, f"session:{candidate['createdByRunId']}", "created_from")
        for attempt in _evolution_attempts(store, candidate["id"]):
            aid = f"evolution_attempt:{attempt['id']}"
            add(GraphNode(
                id=aid, kind="evolution_attempt",
                label=_label(attempt.get("outcome")),
                status=attempt.get("outcome", "failure"), createdAt=attempt.get("startedAt"),
                meta={"diffDigest": attempt.get("diffDigest"), "outcome": attempt.get("outcome")},
            ))
            link(aid, cid, "attempted_on")

    # ── Resolve edges (both endpoints must exist) + filters ──────────────────
    # A referenced session/run target that never got its own node would silently
    # drop the provenance edge. Materialise a bounded placeholder session node for
    # each referenced run so the chain stays visible (derived only; no content).
    session_targets: list[str] = []
    for source, target, _relation in pending_edges:
        if target.startswith("session:") and target not in nodes:
            session_targets.append(target)
    for target in sorted(set(session_targets)):
        if len(nodes) >= MAX_NODES:
            break
        add(GraphNode(id=target, kind="session", label=target.split(":", 1)[1][:MAX_LABEL_CHARS],
                      status="referenced"))

    for source, target, relation in pending_edges:
        if len(edges) >= MAX_EDGES:
            break
        if source in nodes and target in nodes:
            edges.append(GraphEdge(source, target, relation))
    payload_nodes = [n.to_dict() for n in nodes.values()]
    payload_edges = [e.to_dict() for e in edges if e.source in nodes and e.target in nodes]

    by_kind: dict[str, int] = {}
    for node in payload_nodes:
        by_kind[node["kind"]] = by_kind.get(node["kind"], 0) + 1
    by_relation: dict[str, int] = {}
    for edge in payload_edges:
        by_relation[edge["relation"]] = by_relation.get(edge["relation"], 0) + 1

    # Freshness: the graph is derived on demand, so `generatedAt` is the read
    # time. `watermark` is the newest source timestamp seen — a cheap token the
    # UI can compare to decide whether a refetch is warranted (no second store).
    generated_at = _now_iso()
    watermark = generated_at
    timestamps = [n.get("createdAt") for n in payload_nodes if n.get("createdAt")]
    if timestamps:
        watermark = max(timestamps)

    return {
        "nodes": payload_nodes,
        "edges": payload_edges,
        "clusters": [{"kind": k, "count": c} for k, c in sorted(by_kind.items(), key=lambda kv: -kv[1])],
        "generatedAt": generated_at,
        "watermark": watermark,
        "stats": {
            "nodeCount": len(payload_nodes),
            "edgeCount": len(payload_edges),
            "byKind": by_kind,
            "byRelation": by_relation,
            "truncated": len(nodes) >= MAX_NODES or len(edges) >= MAX_EDGES,
        },
    }

def _evolution_candidates(store: Any) -> list[dict[str, Any]]:
    """The evolution candidates, or [] when the tables are absent (additive)."""
    from .code.evolution_store import EvolutionStore  # noqa: PLC0415

    return EvolutionStore(store).list_candidates(limit=MAX_NODES)


def _evolution_attempts(store: Any, candidate_id: str) -> list[dict[str, Any]]:
    from .code.evolution_store import EvolutionStore  # noqa: PLC0415

    return EvolutionStore(store).list_attempts(candidate_id, limit=20)


__all__ = [
    "EDGE_RELATIONS",
    "MAX_EDGES",
    "MAX_NODES",
    "NODE_KINDS",
    "GraphEdge",
    "GraphNode",
    "build_learning_journey",
]
