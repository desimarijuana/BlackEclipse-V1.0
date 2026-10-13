"""Learning curriculum & skill-graph engine (deterministic, no model).

This is the pure, testable core behind the learning-research capability. It
turns a set of *validated resources* plus a *skill specification* into a valid,
prerequisite-aware curriculum that the chat can render and a learner can track.

Design split (kept deliberate):

* The AGENT (model) proposes the skill list — names, objectives, prerequisites,
  exercises, projects and assessment criteria. Domain decomposition is knowledge,
  and a model is good at it.
* THIS ENGINE validates and assembles deterministically: it checks the
  prerequisite graph is a DAG (no cycles), that every prerequisite resolves,
  that every required skill has resources or an explicit evidence-backed gap,
  that milestones carry an assessment, attaches resources by relevance, and
  produces the final ordered curriculum.

Nothing here computes a "learning score" out of thin air. Every score is an
INTERNAL ordering signal with named, auditable components — never presented as a
measure of truth or of a resource's absolute quality.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .web_contracts import SourceType
from .web_sources import _RANK_TABLE  # reuse the ONE learning ordering table

_LEVELS = ("beginner", "intermediate", "advanced", "unspecified")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on", "how",
    "what", "why", "using", "use", "your", "you", "learn", "learning", "tutorial",
    "course", "guide", "intro", "introduction", "part", "from", "scratch", "full",
    "complete", "beginner", "advanced", "intermediate", "series", "official",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-") or "skill"


def _rid(prefix: str, *parts: str) -> str:
    payload = "|".join(str(p) for p in parts)
    return f"{prefix}_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9\+#]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


# ── Contracts ──────────────────────────────────────────────────────────────────


@dataclass
class LearningResource:
    """A validated educational resource (observed facts only; nothing invented)."""

    resourceId: str
    title: str
    url: str
    sourceType: SourceType = SourceType.UNKNOWN
    provider: Optional[str] = None
    author: Optional[str] = None
    description: str = ""
    publishedAt: Optional[str] = None
    retrievedAt: str = field(default_factory=_now)
    durationSeconds: Optional[int] = None
    level: str = "unspecified"
    language: Optional[str] = None
    cost: str = "unknown"  # free | paid | unknown
    verified: bool = False
    accessible: Optional[bool] = None
    thumbnail: Optional[str] = None
    topicTags: list[str] = field(default_factory=list)
    qualitySignals: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resourceId": self.resourceId,
            "title": self.title,
            "url": self.url,
            "sourceType": self.sourceType.value if isinstance(self.sourceType, SourceType) else str(self.sourceType),
            "provider": self.provider,
            "author": self.author,
            "description": self.description,
            "publishedAt": self.publishedAt,
            "retrievedAt": self.retrievedAt,
            "durationSeconds": self.durationSeconds,
            "level": self.level,
            "language": self.language,
            "cost": self.cost,
            "verified": self.verified,
            "accessible": self.accessible,
            "thumbnail": self.thumbnail,
            "topicTags": list(self.topicTags),
            "qualitySignals": dict(self.qualitySignals),
            "limitations": list(self.limitations),
        }


@dataclass
class SkillNode:
    id: str
    name: str
    description: str = ""
    level: str = "unspecified"
    objectives: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)  # skill ids this depends on
    resourceIds: list[str] = field(default_factory=list)
    exercises: list[str] = field(default_factory=list)
    project: Optional[str] = None
    assessment: Optional[str] = None
    estimatedHours: Optional[float] = None
    milestone: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "level": self.level,
            "objectives": list(self.objectives),
            "prerequisites": list(self.prerequisites),
            "resourceIds": list(self.resourceIds),
            "exercises": list(self.exercises),
            "project": self.project,
            "assessment": self.assessment,
            "estimatedHours": self.estimatedHours,
            "milestone": self.milestone,
        }


@dataclass
class SkillEdge:
    source: str  # prerequisite
    target: str  # dependent skill

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.source, "to": self.target}


@dataclass
class CurriculumGraph:
    goal: str
    startLevel: str = "unspecified"
    targetCompetency: str = ""
    nodes: list[SkillNode] = field(default_factory=list)
    edges: list[SkillEdge] = field(default_factory=list)
    version: int = 1
    researchTimestamp: str = field(default_factory=_now)
    assumptions: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "startLevel": self.startLevel,
            "targetCompetency": self.targetCompetency,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "version": self.version,
            "researchTimestamp": self.researchTimestamp,
            "assumptions": list(self.assumptions),
            "alternatives": list(self.alternatives),
            "issues": list(self.issues),
        }


# ── Graph validation (the DAG guarantee) ───────────────────────────────────────


def detect_cycles(nodes: list[SkillNode]) -> list[list[str]]:
    """Return prerequisite cycles (Kahn's algorithm). Empty list means a DAG."""
    ids = [n.id for n in nodes]
    id_set = set(ids)
    indeg = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for n in nodes:
        for p in n.prerequisites:
            if p not in id_set or p == n.id:
                continue
            adj[p].append(n.id)
            indeg[n.id] += 1
    queue = [i for i in ids if indeg[i] == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if seen == len(ids):
        return []
    # Nodes still with in-degree > 0 participate in (or are downstream of) a cycle.
    remaining = {i for i in ids if indeg[i] > 0}
    return [sorted(remaining)]


def topological_order(nodes: list[SkillNode]) -> list[str]:
    """Prerequisite-first ordering (stable). Assumes a DAG."""
    ids = [n.id for n in nodes]
    id_set = set(ids)
    indeg = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for n in nodes:
        for p in n.prerequisites:
            if p in id_set and p != n.id:
                adj[p].append(n.id)
                indeg[n.id] += 1
    queue = [i for i in ids if indeg[i] == 0]
    order: list[str] = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    return order


def _reachable(nodes: list[SkillNode]) -> set[str]:
    """Skills reachable from any root (a skill with no resolved prerequisites)."""
    id_set = {n.id for n in nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in nodes}
    roots: list[str] = []
    for n in nodes:
        resolved = [p for p in n.prerequisites if p in id_set and p != n.id]
        if not resolved:
            roots.append(n.id)
        for p in resolved:
            adj[p].append(n.id)
    reached: set[str] = set()
    stack = list(roots)
    while stack:
        cur = stack.pop()
        if cur in reached:
            continue
        reached.add(cur)
        stack.extend(adj[cur])
    return reached


def validate_curriculum(graph: CurriculumGraph) -> list[dict[str, Any]]:
    """Deterministically validate the graph. Returns a list of issues.

    Each issue: {code, severity, message, node?}. An empty list is a clean graph.
    """
    issues: list[dict[str, Any]] = []
    ids = [n.id for n in graph.nodes]
    id_set = set(ids)
    if len(ids) != len(id_set):
        issues.append({"code": "duplicate_skill_id", "severity": "error", "message": "two skills share an id"})

    # Missing prerequisite references.
    for n in graph.nodes:
        for p in n.prerequisites:
            if p not in id_set:
                issues.append({
                    "code": "missing_prerequisite", "severity": "error",
                    "message": f"skill {n.id!r} depends on unknown skill {p!r}", "node": n.id,
                })

    # Cycles.
    for cycle in detect_cycles(graph.nodes):
        issues.append({
            "code": "circular_dependency", "severity": "error",
            "message": f"prerequisite cycle among {cycle}", "node": cycle[0] if cycle else None,
        })

    # Required-skill coverage: a skill with no resources is a gap that must be stated.
    for n in graph.nodes:
        if not n.resourceIds:
            issues.append({
                "code": "skill_without_resources", "severity": "warning",
                "message": f"skill {n.id!r} ({n.name}) has no attached resource", "node": n.id,
            })
        if n.milestone and not (n.assessment or n.exercises or n.project):
            issues.append({
                "code": "milestone_without_assessment", "severity": "warning",
                "message": f"milestone {n.milestone!r} on {n.id!r} has no assessment/exercise", "node": n.id,
            })
        if not n.objectives:
            issues.append({
                "code": "skill_without_objectives", "severity": "warning",
                "message": f"skill {n.id!r} has no learning objectives", "node": n.id,
            })

    # Disconnected required skills (unreachable from any root) — only meaningful
    # on a valid DAG, where reachability is well-defined.
    if not any(i["code"] == "circular_dependency" for i in issues):
        reached = _reachable(graph.nodes)
        # Every node with resolved prerequisites should be reachable from a root;
        # a node none of whose prerequisites resolve is itself a root and counted.
        for n in graph.nodes:
            if n.id in reached:
                continue
            issues.append({
                "code": "disconnected_skill", "severity": "warning",
                "message": f"skill {n.id!r} is not reachable from the curriculum's starting skills", "node": n.id,
            })
    return issues


# ── Resource ranking (transparent, configurable) ───────────────────────────────


def _source_position(source_type: SourceType) -> int:
    table = _RANK_TABLE["learning"]
    try:
        return table.index(source_type)
    except ValueError:
        return len(table)


def rank_resource(resource: LearningResource, objective: str) -> dict[str, Any]:
    """Score one resource for a learning objective. Named, auditable components.

    Returns {score, components, notes}. `score` is an internal ordering signal in
    [0, 1] — never a claim of absolute quality or truth.
    """
    table = _RANK_TABLE["learning"]
    size = max(1, len(table))
    authority = 1.0 - (_source_position(resource.sourceType) / size)

    obj_tokens = _tokens(objective)
    res_tokens = _tokens(" ".join([resource.title, resource.description, " ".join(resource.topicTags)]))
    if obj_tokens:
        overlap = len(obj_tokens & res_tokens) / len(obj_tokens)
    else:
        overlap = 0.0

    # Completeness: longer curated material (a course/playlist) reads as more
    # complete than a snippet; a real description adds signal. Bounded, no fakes.
    duration = resource.durationSeconds or 0
    if duration >= 3600:
        depth = 1.0
    elif duration >= 1200:
        depth = 0.75
    elif duration > 0:
        depth = 0.5
    else:
        depth = 0.4
    depth = max(depth, min(0.6, len(resource.description) / 600.0))

    # Accessibility: a resource we actually probed and could reach is usable.
    if resource.accessible is True:
        accessibility = 1.0
    elif resource.accessible is None:
        accessibility = 0.6
    else:
        accessibility = 0.0

    completeness = 1.0 if resource.verified else 0.5

    components = {
        "authority": round(authority, 4),
        "relevance": round(overlap, 4),
        "depth": round(depth, 4),
        "accessibility": round(accessibility, 4),
        "verification": round(completeness, 4),
    }
    weights = {"authority": 0.30, "relevance": 0.30, "depth": 0.15, "accessibility": 0.15, "verification": 0.10}
    score = sum(weights[k] * components[k] for k in weights)

    notes: list[str] = []
    if resource.limitations:
        notes.extend(resource.limitations)
    return {
        "resourceId": resource.resourceId,
        "score": round(score, 4),
        "components": components,
        "weights": weights,
        "notes": notes,
    }


def rank_resources(resources: list[LearningResource], objective: str) -> list[dict[str, Any]]:
    """Rank resources for an objective, best first; each score is explainable."""
    scored = [rank_resource(r, objective) for r in resources]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored


def reject_weak(scored: list[dict[str, Any]], *, floor: float = 0.28) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split ranked resources into (kept, rejected) at a transparent floor."""
    kept = [s for s in scored if s["score"] >= floor]
    rejected = [s for s in scored if s["score"] < floor]
    return kept, rejected


# ── Construction: skills + resources → curriculum ──────────────────────────────


def _make_resource(spec: dict[str, Any]) -> LearningResource:
    url = str(spec.get("url") or "").strip()
    title = str(spec.get("title") or "").strip() or url or "Untitled resource"
    st = spec.get("sourceType")
    if isinstance(st, SourceType):
        source_type = st
    else:
        try:
            source_type = SourceType(str(st)) if st else SourceType.UNKNOWN
        except ValueError:
            source_type = SourceType.UNKNOWN
    tags = spec.get("topicTags") or []
    if isinstance(tags, str):
        tags = [tags]
    return LearningResource(
        resourceId=str(spec.get("resourceId") or _rid("res", url, title)),
        title=title,
        url=url,
        sourceType=source_type,
        provider=spec.get("provider"),
        author=spec.get("author") or spec.get("channel"),
        description=str(spec.get("description") or ""),
        publishedAt=spec.get("publishedAt"),
        durationSeconds=spec.get("durationSeconds"),
        level=str(spec.get("level") or "unspecified").lower(),
        language=spec.get("language"),
        cost=str(spec.get("cost") or "unknown"),
        verified=bool(spec.get("verified")),
        accessible=spec.get("accessible"),
        thumbnail=spec.get("thumbnail"),
        topicTags=[str(t) for t in tags],
        qualitySignals=spec.get("qualitySignals") or {},
        limitations=list(spec.get("limitations") or []),
    )


def resources_from_specs(specs: list[dict[str, Any]]) -> list[LearningResource]:
    out: list[LearningResource] = []
    seen: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        r = _make_resource(spec)
        if not r.url or r.url in seen:
            continue
        seen.add(r.url)
        out.append(r)
    return out


def _attach_resources(nodes: list[SkillNode], resources: list[LearningResource], *, per_skill: int = 3) -> None:
    """Attach the best-matching resources to each skill (deterministic, bounded).

    A resource may serve more than one skill (a playlist can cover several), but
    its reuse is bounded so one strong resource does not crowd out every node. A
    resource is only auto-attached when it is *relevant* to the skill (non-zero
    overlap with its name/objectives) — otherwise a skill honestly shows a gap.
    """
    usage: dict[str, int] = {}
    max_reuse = 2
    for node in nodes:
        objective = " ".join([node.name, *node.objectives])
        explicit = set(node.resourceIds)
        scored = rank_resources(resources, objective)
        picked: list[str] = []
        for s in scored:
            rid = s["resourceId"]
            if rid in explicit:
                continue
            if s["components"]["relevance"] <= 0:
                continue
            if usage.get(rid, 0) >= max_reuse:
                continue
            picked.append(rid)
            usage[rid] = usage.get(rid, 0) + 1
            if len(picked) >= per_skill:
                break
        # A skill the model gave explicit resources keeps them, ranked, first.
        node.resourceIds = list(dict.fromkeys(node.resourceIds + picked))


def build_curriculum(
    *,
    goal: str,
    skill_specs: list[dict[str, Any]],
    resources: list[dict[str, Any]] | list[LearningResource],
    start_level: str = "unspecified",
    target_competency: str = "",
    assumptions: Optional[list[str]] = None,
    alternatives: Optional[list[str]] = None,
    version: int = 1,
) -> CurriculumGraph:
    """Assemble a validated curriculum from a skill spec + discovered resources.

    The skill_specs carry the model's proposed decomposition; this function only
    validates and assembles it. It is safe to call with an empty spec (it yields
    a single, resources-only foundation skill) so a roadmap is never empty.
    """
    res_list: list[LearningResource] = []
    for r in resources:
        res_list.append(r if isinstance(r, LearningResource) else _make_resource(r))

    nodes: list[SkillNode] = []
    name_to_id: dict[str, str] = {}
    for i, spec in enumerate(skill_specs or []):
        if not isinstance(spec, dict):
            continue
        name = str(spec.get("name") or spec.get("title") or f"Skill {i + 1}").strip()
        node_id = str(spec.get("id") or _slug(name))
        nodes.append(SkillNode(
            id=node_id,
            name=name,
            description=str(spec.get("description") or ""),
            level=str(spec.get("level") or "unspecified").lower(),
            objectives=[str(o) for o in (spec.get("objectives") or [])],
            prerequisites=[str(p) for p in (spec.get("prerequisites") or [])],
            resourceIds=[str(x) for x in (spec.get("resourceIds") or [])],
            exercises=[str(o) for o in (spec.get("exercises") or [])],
            project=spec.get("project"),
            assessment=spec.get("assessment"),
            estimatedHours=spec.get("estimatedHours"),
            milestone=spec.get("milestone"),
        ))
        name_to_id[name.lower()] = node_id

    # Resolve prerequisites that were given as names rather than ids.
    for n in nodes:
        resolved: list[str] = []
        for p in n.prerequisites:
            resolved.append(name_to_id.get(p.lower(), p))
        n.prerequisites = resolved

    if not nodes:
        nodes = [SkillNode(
            id="foundations",
            name=f"Foundations of {goal}".strip(),
            objectives=[f"Build a working understanding of {goal}".strip()],
            milestone="Foundation complete",
            assessment="Explain the core concepts in your own words.",
        )]

    _attach_resources(nodes, res_list)

    edges: list[SkillEdge] = []
    seen_edges: set[tuple[str, str]] = set()
    id_set = {n.id for n in nodes}
    for n in nodes:
        for p in n.prerequisites:
            if p in id_set and (p, n.id) not in seen_edges:
                seen_edges.add((p, n.id))
                edges.append(SkillEdge(source=p, target=n.id))

    graph = CurriculumGraph(
        goal=goal,
        startLevel=start_level,
        targetCompetency=target_competency,
        nodes=nodes,
        edges=edges,
        version=version,
        assumptions=list(assumptions or []),
        alternatives=list(alternatives or []),
    )
    graph.issues = validate_curriculum(graph)
    return graph


def resource_index(resources: list[LearningResource]) -> dict[str, dict[str, Any]]:
    return {r.resourceId: r.to_dict() for r in resources}


__all__ = [
    "LearningResource",
    "SkillNode",
    "SkillEdge",
    "CurriculumGraph",
    "build_curriculum",
    "validate_curriculum",
    "detect_cycles",
    "topological_order",
    "rank_resource",
    "rank_resources",
    "reject_weak",
    "resources_from_specs",
    "resource_index",
]
