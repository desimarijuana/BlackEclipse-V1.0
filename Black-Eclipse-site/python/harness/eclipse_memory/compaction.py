"""Conservative memory compaction (Phase 5).

Detects likely near-duplicate ACTIVE memories using the SAME deterministic
normalization the retriever uses (`normalize.canonical_tokens`) plus existing
signals, and produces an **inert** proposal. Nothing is merged until an operator
accepts the proposal, and acceptance:

  * creates one new memory (the merged content),
  * supersedes the originals (linked + retained — never hard-deleted),
  * preserves provenance/evidence/timestamps by keeping the originals,
  * never compacts across scopes,
  * never compacts contradictory records (those go to conflict review instead).

This module only *detects and proposes*. It cannot write durable memory on its
own — `EclipseMemoryService.accept_compaction` performs the gated merge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Overlap above which two same-dimension records are considered near-duplicates.
# Deliberately high: a wrong merge is worse than a missed one.
NEAR_DUPLICATE_THRESHOLD = 0.8

# Bounded scan: a proposal never aggregates more than this many members.
MAX_MEMBERS = 5

# Record types that are safe to compact (standing/durable declarative facts).
# `correction` is excluded (it is a historical event), as is `observation`.
_COMPACTABLE_TYPES = frozenset(
    {"semantic", "preference", "constraint", "summary"}
)


@dataclass
class CompactionProposal:
    members: list[str]
    scope: str
    scope_id: Optional[str]
    subject: Optional[str]
    merged_content: str
    rationale: str
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memberIds": self.members,
            "scope": self.scope,
            "scopeId": self.scope_id,
            "subject": self.subject,
            "mergedContent": self.merged_content,
            "rationale": self.rationale,
            "evidence": self.evidence,
        }


def _tokens(text: str) -> set[str]:
    import re  # noqa: PLC0415

    from .normalize import canonical_tokens  # noqa: PLC0415

    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in canonical_tokens(raw) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _looks_contradictory(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when the two records must NOT be auto-merged (defer to review)."""
    from .conflicts import opposing, same_dimension  # noqa: PLC0415

    try:
        if opposing(a.get("content", ""), b.get("content", "")) and same_dimension(
            a.get("memoryType", ""), a.get("content", ""), b.get("content", "")
        ):
            return True
    except Exception:  # noqa: BLE001 - a detector failure must not risk a merge
        return True
    return False


def detect_proposals(
    memories: list[dict[str, Any]], *, limit: int = 50,
) -> list[CompactionProposal]:
    """Group near-duplicate active memories into inert proposals.

    Deterministic: memories are grouped by (scope, scopeId, memoryType, subject)
    and compared by canonical-token Jaccard overlap. Contradictory pairs are
    skipped. Never crosses scope.
    """
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for memory in memories:
        if memory.get("status") != "active":
            continue
        if memory.get("memoryType") not in _COMPACTABLE_TYPES:
            continue
        key = (
            memory.get("scope"), memory.get("scopeId"),
            memory.get("memoryType"), (memory.get("subject") or "").lower(),
        )
        groups.setdefault(key, []).append(memory)

    proposals: list[CompactionProposal] = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        used: set[str] = set()
        for i in range(len(members)):
            if members[i]["id"] in used:
                continue
            cluster = [members[i]]
            tokens_i = _tokens(members[i].get("content", ""))
            for j in range(i + 1, len(members)):
                if members[j]["id"] in used:
                    continue
                if _looks_contradictory(members[i], members[j]):
                    continue
                tokens_j = _tokens(members[j].get("content", ""))
                # Near-duplicate when the token sets overlap heavily OR one is a
                # subset of the other (the "same statement with extra words"
                # case). Contradiction is already excluded above, and scope/
                # subject/type must all match, so this stays conservative.
                overlap = _jaccard(tokens_i, tokens_j)
                contained = bool(tokens_i) and bool(tokens_j) and (
                    tokens_i <= tokens_j or tokens_j <= tokens_i
                )
                if overlap >= NEAR_DUPLICATE_THRESHOLD or contained:
                    cluster.append(members[j])
                    if len(cluster) >= MAX_MEMBERS:
                        break
            if len(cluster) < 2:
                continue
            for member in cluster:
                used.add(member["id"])
            # The merged content is the LONGEST member's content — never invented.
            chosen = max(cluster, key=lambda m: len(m.get("content", "")))
            proposals.append(CompactionProposal(
                members=[m["id"] for m in cluster],
                scope=str(key[0]), scope_id=key[1], subject=key[3] or None,
                merged_content=str(chosen.get("content") or ""),
                rationale=(
                    f"{len(cluster)} memories overlap on the same scope/subject/dimension; "
                    "merging keeps the fullest statement and supersedes the rest (retained)."
                ),
                evidence=[
                    {"id": m["id"], "content": m.get("content"), "confidence": m.get("confidence")}
                    for m in cluster
                ],
            ))
            if len(proposals) >= limit:
                return proposals
    return proposals


def preservation_report(
    members: list[dict[str, Any]], merged_content: str,
) -> dict[str, Any]:
    """Prove that a merge preserves the material content of its members.

    A member is "preserved" when its canonical token set is a subset of the
    merged content's token set OR its content is retained verbatim by the
    original row (which is never deleted). Reports any material tokens that
    would be lost so a caller can refuse a lossy merge.
    """
    merged_tokens = _tokens(merged_content)
    lost: list[str] = []
    for member in members:
        member_tokens = _tokens(member.get("content", ""))
        missing = member_tokens - merged_tokens
        if missing:
            lost.extend(sorted(missing))
    # De-duplicate, bounded.
    unique_lost = sorted(set(lost))[:20]
    return {
        "members": len(members),
        "lostTokens": unique_lost,
        "preserved": not unique_lost,
    }


__all__ = [
    "MAX_MEMBERS",
    "NEAR_DUPLICATE_THRESHOLD",
    "CompactionProposal",
    "detect_proposals",
    "preservation_report",
]
