"""Evidence supersession / restatement chains (Phase 4, Workstream 5).

A restatement relationship is NEVER inferred because a later number differs. A
link exists only when a source exposes reliable revision metadata (a document
id, version id, or an explicit `supersedesEvidenceId` + relationship kind).

This module:

  * builds a chain from evidence that already carries such metadata,
  * rejects cycles and dangling links (a bad chain is reported, not applied),
  * resolves, for an `asOf` cutoff, the revision that was available by then,
  * resolves, for current research, the latest source-backed version while
    retaining the history,
  * reports restatement coverage as `unavailable` when the sources supply no
    revision metadata — never manufacturing a link.

Audit finding (2026-09-23): the vault `financial_statements` payload exposes a
filing `form` and `filed` date but no accession number, amendment indicator, or
explicit restatement relationship, and it persists only the latest snapshot. So
in practice restatement coverage is currently `unavailable`; this module is the
safe, source-grounded seam for when a provider adds the metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

RelationshipKind = Literal["amends", "restates", "corrects", "withdraws"]

# Evidence kinds that may carry a revision relationship.
_CHAIN_KINDS = {"structured", "filing", "derived", "cached", "unknown"}


@dataclass
class SupersessionLink:
    evidenceId: str
    supersedesEvidenceId: str
    relationshipKind: str
    documentId: Optional[str] = None
    versionId: Optional[str] = None
    publishedAt: Optional[str] = None


@dataclass
class SupersessionChain:
    coverage: str  # available | unavailable
    links: list[SupersessionLink] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    # Latest source-backed revision per (metric, period, identity) key.
    currentByKey: dict[str, str] = field(default_factory=dict)
    historyByKey: dict[str, list[str]] = field(default_factory=dict)

    def resolve_as_of(self, key: str, asof: str) -> Optional[str]:
        """The id of the newest revision in `key`'s chain available by `asof`.

        A revision with an UNKNOWN publication time cannot be claimed available
        by the cutoff, so it is skipped (never assumed available).
        """
        candidates = [
            link.evidenceId
            for link in self.links
            if _link_key(link) == key and link.publishedAt and str(link.publishedAt) <= str(asof)
        ]
        return candidates[-1] if candidates else None


def _link_key(link: SupersessionLink) -> str:
    return link.evidenceId


def build_chain(evidence: list[Any]) -> SupersessionChain:
    """Build a source-grounded supersession chain from evidence metadata.

    Coverage is `unavailable` when no evidence carries revision metadata — the
    honest default, since most current providers do not.
    """
    by_id = {getattr(item, "id", ""): item for item in evidence}
    links: list[SupersessionLink] = []
    issues: list[str] = []

    for item in evidence:
        if getattr(item, "kind", None) not in _CHAIN_KINDS:
            continue
        supersedes = getattr(item, "supersedesEvidenceId", None) or _obj_attr(item, "supersedesEvidenceId")
        if not supersedes:
            continue
        kind = getattr(item, "relationshipKind", None) or _obj_attr(item, "relationshipKind")
        if kind not in ("amends", "restates", "corrects", "withdraws"):
            issues.append(f"{getattr(item, 'id', '?')}: supersedes link has an unknown relationship kind {kind!r}")
            continue
        published = getattr(item, "publishedAt", None) or _obj_attr(item, "publishedAt")
        links.append(
            SupersessionLink(
                evidenceId=getattr(item, "id", ""),
                supersedesEvidenceId=str(supersedes),
                relationshipKind=str(kind),
                documentId=getattr(item, "documentId", None) or _obj_attr(item, "documentId"),
                versionId=getattr(item, "versionId", None) or _obj_attr(item, "versionId"),
                publishedAt=str(published) if published else None,
            )
        )

    if not links:
        return SupersessionChain(coverage="unavailable", issues=issues)

    # Validate: no dangling target, no cycle.
    for link in links:
        if link.supersedesEvidenceId not in by_id:
            issues.append(f"{link.evidenceId}: supersedes unknown evidence {link.supersedesEvidenceId!r}")

    if _has_cycle(links):
        return SupersessionChain(
            coverage="unavailable",
            issues=issues + ["supersession chain contains a cycle and was rejected"],
        )

    # Order each chain oldest→newest and group by the superseded item's
    # (metric, period, identity) key so a consumer can resolve the current
    # revision of one fact. A revision with an unknown publication time is still
    # recorded in history but never becomes the "current" head.
    ordered = sorted(links, key=lambda l: (l.publishedAt or "9999", l.evidenceId))
    history: dict[str, list[str]] = {}
    current: dict[str, str] = {}
    for link in ordered:
        target = by_id.get(link.supersedesEvidenceId)
        key = _fact_key(target) if target is not None else link.supersedesEvidenceId
        history.setdefault(key, []).append(link.supersedesEvidenceId)
        history[key].append(link.evidenceId)
        if link.publishedAt is not None and key:
            current[key] = link.evidenceId

    return SupersessionChain(
        coverage="available",
        links=ordered,
        issues=issues,
        currentByKey=current,
        historyByKey={k: sorted(set(v)) for k, v in history.items()},
    )


def _fact_key(item: Any) -> str:
    """A (metric, period, instrument) key for grouping revisions of one fact."""
    obj = None
    for candidate in getattr(item, "objects", []) or []:
        obj = candidate
        break
    if obj is None:
        return getattr(item, "id", "")
    return f"{getattr(obj, 'name', '')}|{getattr(obj, 'period', '')}|{getattr(obj, 'instrument', '')}"


def _obj_attr(item: Any, name: str) -> Optional[Any]:
    """Look for a field on the item's first normalized object (fallback)."""
    for obj in getattr(item, "objects", []) or []:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _has_cycle(links: list[SupersessionLink]) -> bool:
    graph: dict[str, str] = {l.evidenceId: l.supersedesEvidenceId for l in links}
    for start in graph:
        seen: set[str] = set()
        node = start
        while node in graph:
            if node in seen:
                return True
            seen.add(node)
            node = graph[node]
    return False


__all__ = [
    "RelationshipKind",
    "SupersessionLink",
    "SupersessionChain",
    "build_chain",
]
