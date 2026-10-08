"""Deterministic entity + relation extraction for the research knowledge graph.

This is NOT a general ontology and NOT a model. It extracts, from evidence that
has already been fetched:
  * entities  — resolved companies (via `resolve_entity`) and proper-noun phrases,
    each ANCHORED to the evidence item it appeared in; and
  * relations — `metric → value` edges taken from the structured enrichment the
    engine already computes, plus co-occurrence edges between entities.

Every node and edge carries the `evidenceId`/`sourceUrl` it came from, so nothing
is an ungrounded fact. Extraction is conservative: an entity with no evidence is
never emitted; a relation with no value is never emitted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .web_contracts import Evidence
from .web_sources import resolve_entity

# Capitalized proper-noun phrases (2+ words, or a single capitalized token that is
# not a sentence-starter). Deliberately strict so we do not invent entities.
_PHRASE_RE = re.compile(r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){1,4})\b")
_CAP_RE = re.compile(r"\b([A-Z][A-Za-z]{2,})\b")

# Tokens that begin sentences / are common; never treated as a standalone entity.
_GENERIC_CAPS = frozenset(
    {
        "The", "This", "That", "These", "Those", "It", "Its", "In", "On", "For",
        "And", "But", "However", "According", "While", "When", "Where", "How",
        "Also", "As", "At", "By", "To", "Of", "We", "Our", "They", "Their",
        "Company", "Quarter", "Revenue", "Figure", "Source", "Note", "Table",
    }
)


@dataclass
class EntityNode:
    entityId: str
    name: str
    kind: str
    aliases: list[str] = field(default_factory=list)
    evidenceId: Optional[str] = None
    sourceUrl: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entityId": self.entityId,
            "name": self.name,
            "kind": self.kind,
            "aliases": self.aliases,
            "evidenceId": self.evidenceId,
            "sourceUrl": self.sourceUrl,
            "confidence": self.confidence,
        }


@dataclass
class RelationEdge:
    id: str
    subjectId: str
    predicate: str
    objectId: Optional[str] = None
    objectValue: Optional[str] = None
    unit: Optional[str] = None
    period: Optional[str] = None
    evidenceId: Optional[str] = None
    sourceUrl: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subjectId": self.subjectId,
            "predicate": self.predicate,
            "objectId": self.objectId,
            "objectValue": self.objectValue,
            "unit": self.unit,
            "period": self.period,
            "evidenceId": self.evidenceId,
            "sourceUrl": self.sourceUrl,
            "confidence": self.confidence,
        }


def _entity_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"ent_{slug}"[:120]


def _relation_id(subject: str, predicate: str, obj: str) -> str:
    raw = f"{subject}|{predicate}|{obj}".lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return f"rel_{slug}"[:160]


def extract_entities(evidence: list[Evidence]) -> list[EntityNode]:
    """Entities mentioned in the evidence, each anchored to its evidence item.

    Deduped by entity id (keeping the first, highest-signal anchor). A company
    resolved by `resolve_entity` is a first-class `company` node; remaining
    proper-noun phrases are `term` nodes. No ungrounded entity is emitted.
    """
    by_id: dict[str, EntityNode] = {}
    for ev in evidence:
        text = ev.rawText or ""
        if not text.strip():
            continue
        src = ev.sourceUrl
        # 1. Resolved companies (deterministic identity, not a guess).
        for match in _PHRASE_RE.finditer(text[:40_000]):
            phrase = match.group(1).strip()
            resolved = resolve_entity(phrase)
            if resolved is not None:
                eid = resolved.entityId
                if eid not in by_id:
                    by_id[eid] = EntityNode(
                        entityId=eid, name=resolved.name, kind="company",
                        aliases=list(resolved.aliases or []),
                        evidenceId=ev.evidenceId, sourceUrl=src, confidence=0.9,
                    )
        # 2. Proper-noun terms (lower confidence).
        for match in _PHRASE_RE.finditer(text[:20_000]):
            phrase = match.group(1).strip()
            first = phrase.split(" ", 1)[0]
            if first in _GENERIC_CAPS:
                continue
            eid = _entity_id(phrase)
            if eid not in by_id:
                by_id[eid] = EntityNode(
                    entityId=eid, name=phrase, kind="term",
                    evidenceId=ev.evidenceId, sourceUrl=src, confidence=0.4,
                )
        # 3. A single strong proper noun that is a company ticker/name.
        for match in _CAP_RE.finditer(text[:20_000]):
            token = match.group(1)
            if token in _GENERIC_CAPS:
                continue
            resolved = resolve_entity(token)
            if resolved is not None and resolved.entityId not in by_id:
                by_id[resolved.entityId] = EntityNode(
                    entityId=resolved.entityId, name=resolved.name, kind="company",
                    aliases=list(resolved.aliases or []),
                    evidenceId=ev.evidenceId, sourceUrl=src, confidence=0.8,
                )
    return list(by_id.values())


def extract_relations(entities: list[EntityNode], evidence: list[Evidence]) -> list[RelationEdge]:
    """`metric → value` edges from the structured enrichment on each evidence item,
    plus company↔term co-occurrence edges. Anchored to evidence; no value ⇒ no edge."""
    edges: dict[str, RelationEdge] = {}
    company_nodes = [e for e in entities if e.kind == "company"]
    for ev in evidence:
        prov = ev.provenance if isinstance(ev.provenance, dict) else {}
        metric = prov.get("metric")
        if metric and ev.structuredValue is not None and company_nodes:
            subject = company_nodes[0]
            obj = f"{ev.structuredValue}{ev.unit or ''}"
            rid = _relation_id(subject.entityId, str(metric), obj)
            if rid not in edges:
                edges[rid] = RelationEdge(
                    id=rid, subjectId=subject.entityId, predicate=str(metric),
                    objectValue=str(ev.structuredValue), unit=ev.unit, period=ev.period,
                    evidenceId=ev.evidenceId, sourceUrl=ev.sourceUrl, confidence=0.7,
                )
    # Co-occurrence: a company and a term named in the SAME evidence item.
    term_by_evidence: dict[str, list[EntityNode]] = {}
    for e in entities:
        if e.evidenceId:
            term_by_evidence.setdefault(e.evidenceId, []).append(e)
    for eid, nodes in term_by_evidence.items():
        companies = [n for n in nodes if n.kind == "company"]
        terms = [n for n in nodes if n.kind == "term"]
        for c in companies[:2]:
            for t in terms[:5]:
                if c.entityId == t.entityId:
                    continue
                rid = _relation_id(c.entityId, "mentioned_with", t.entityId)
                if rid not in edges:
                    edges[rid] = RelationEdge(
                        id=rid, subjectId=c.entityId, predicate="mentioned_with",
                        objectId=t.entityId, evidenceId=eid, confidence=0.3,
                    )
    return list(edges.values())


def build_graph(evidence: list[Evidence]) -> tuple[list[EntityNode], list[RelationEdge]]:
    """Extract entities then their evidence-anchored relations."""
    entities = extract_entities(evidence)
    relations = extract_relations(entities, evidence)
    return entities, relations


__all__ = ["EntityNode", "RelationEdge", "extract_entities", "extract_relations", "build_graph"]
