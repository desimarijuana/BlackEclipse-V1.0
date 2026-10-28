"""Memory consolidation on the active set.

Active memory may not contain two truths for the same dimension. This sweep:

* supersedes an exact duplicate, keeping the most recent statement;
* supersedes an older contradictory statement on the same dimension, resolving
  to the later statement;
* leaves genuinely unrelated or differently-scoped records untouched;
* retains every row (supersede, never delete) so the history is auditable.

It is deterministic and content-free in its report. It does not run a model and
does not invent a resolution when no contradiction is detected.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .conflicts import opposing, same_dimension


_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "and", "or",
    "i", "my", "me", "we", "you", "it", "that", "this", "be", "with", "for",
    "in", "on", "at", "as", "by", "user", "users", "prefer", "prefers",
})

_CONCISE_HINTS = ("straight", "to the facts", "no opinion", "concise", "brief", "short")
_DETAILED_HINTS = ("detailed", "sources", "in-depth", "comprehensive", "thorough")


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokens(text: Any) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", _normalize(text))
        if token not in _STOPWORDS and len(token) > 1
    }


def _overlap(a: Any, b: Any) -> float:
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _containment(a: Any, b: Any) -> float:
    """How much of the smaller statement is contained in the larger one."""
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _subject_links(subject: Any, other_content: Any) -> bool:
    subject_tokens = _tokens(subject)
    return bool(subject_tokens) and subject_tokens <= _tokens(other_content)


def _verbosity_conflict(a: Any, b: Any) -> bool:
    left, right = _normalize(a), _normalize(b)
    left_concise = any(hint in left for hint in _CONCISE_HINTS)
    right_concise = any(hint in right for hint in _CONCISE_HINTS)
    left_detailed = any(hint in left for hint in _DETAILED_HINTS)
    right_detailed = any(hint in right for hint in _DETAILED_HINTS)
    return (left_concise and right_detailed) or (right_concise and left_detailed)


def _stamp(row: dict[str, Any]) -> str:
    return str(row.get("updatedAt") or row.get("createdAt") or "")


def _eligible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("memoryType") == b.get("memoryType")
        and (a.get("scope") or "") == (b.get("scope") or "")
        and (a.get("scopeId") or None) == (b.get("scopeId") or None)
    )


def consolidate_active(
    store: Any,
    *,
    limit: int = 200,
    dry_run: bool = False,
    resolve_conflicts: bool = True,
) -> dict[str, Any]:
    """Resolve duplicates and contradictions among active memories.

    ``resolve_conflicts=False`` keeps the automatic sweep conservative: exact and
    near duplicates are superseded, but a contradiction is reported for review
    and both statements stay active. This is what the startup maintenance pass
    uses; an operator can still run the full resolver explicitly.
    """
    rows = store.list_memories(status="active", limit=limit)
    ordered = sorted(rows, key=_stamp)
    superseded: list[dict[str, Any]] = []
    duplicates: list[str] = []
    conflicts: list[str] = []
    kept: list[dict[str, Any]] = []
    active_ids = {row["id"] for row in ordered}

    for row in ordered:
        if row["id"] not in active_ids:
            continue
        replacement: Optional[dict[str, Any]] = None
        reason: Optional[str] = None
        for index in range(len(kept) - 1, -1, -1):
            other = kept[index]
            if not _eligible(row, other):
                continue
            same_dim = same_dimension(row.get("subject"), other.get("subject"))
            overlap = _overlap(row.get("content"), other.get("content"))
            containment = _containment(row.get("content"), other.get("content"))
            subject_link = (
                _subject_links(row.get("subject"), other.get("content"))
                or _subject_links(other.get("subject"), row.get("content"))
            )
            if _normalize(row.get("content")) == _normalize(other.get("content")):
                replacement, reason = other, "duplicate"
                break
            if (
                overlap >= 0.5 or containment >= 0.8 or subject_link
            ) and not opposing(
                str(row.get("content") or ""), str(other.get("content") or "")
            ):
                replacement, reason = other, "near_duplicate"
                break
            verbosity = _verbosity_conflict(
                row.get("content"), other.get("content")
            )
            if (
                same_dim or overlap >= 0.2 or verbosity or subject_link
            ) and (
                opposing(str(row.get("content") or ""), str(other.get("content") or ""))
                or verbosity
            ):
                replacement, reason = other, "contradiction"
                break
        if replacement is None:
            kept.append(row)
            continue

        if reason == "contradiction" and not resolve_conflicts:
            conflicts.append(replacement["id"])
            kept.append(row)
            continue

        old = replacement
        # The later statement wins; the older one is retained and linked.
        if dry_run:
            superseded.append({"id": old["id"], "supersededBy": row["id"], "reason": reason})
        else:
            store.supersede_memory(
                old["id"], row["id"],
                reason=f"consolidation: {reason} on the same dimension",
            )
            superseded.append({"id": old["id"], "supersededBy": row["id"], "reason": reason})
        if reason in ("duplicate", "near_duplicate"):
            duplicates.append(old["id"])
        else:
            conflicts.append(old["id"])
        kept.remove(old)
        kept.append(row)

    known_residue = {"loopback can save"}
    residue = [
        {"id": row["id"], "reason": "fragment: <=2 tokens or known test residue"}
        for row in kept
        if not row.get("subject")
        and (
            len(_tokens(row.get("content"))) <= 2
            or _normalize(row.get("content")) in known_residue
        )
    ]
    related: list[dict[str, Any]] = []
    for index, left in enumerate(kept):
        for right in kept[index + 1 :]:
            if _eligible(left, right):
                continue
            if _containment(left.get("content"), right.get("content")) >= 0.8:
                related.append({
                    "a": left["id"], "b": right["id"],
                    "reason": "near-duplicate across type/scope; review, do not auto-merge",
                })
    return {
        "ok": True,
        "dryRun": bool(dry_run),
        "resolveConflicts": bool(resolve_conflicts),
        "scanned": len(ordered),
        "superseded": superseded,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "residue": residue,
        "related": related,
        "duplicateCount": len(duplicates),
        "conflictCount": len(conflicts),
        "residueCount": len(residue),
        "relatedCount": len(related),
    }


__all__ = ["consolidate_active"]
