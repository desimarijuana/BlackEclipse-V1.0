"""Typed operators and novelty for RSL proposals.

A proposal is not only "some ops": it is a typed mutation of one surface
(prompt, tool guidance, tool subset, context policy, a guardrail, the delegated
child prompt, ceilings, model identity, a code patch, or a composition). Naming
the operator makes the experiment readable and lets the search refuse a
near-duplicate of something it already measured.

Novelty is a Jaccard distance over normalized op/surface tokens. It is a
sampling and de-duplication signal: it never grants authority and never decides
acceptance.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Sequence

OPERATORS: tuple[str, ...] = (
    "prompt",
    "tool_guidance",
    "tool_subset",
    "ceilings",
    "context_policy",
    "guardrail",
    "subagent_prompt",
    "model_identity",
    "skill_draft",
    "code_patch",
    "composition",
    "unknown",
)

FIELD_OPERATOR: dict[str, str] = {
    "systemPrompt": "prompt",
    "toolGuidance": "tool_guidance",
    "toolNames": "tool_subset",
    "maxSteps": "ceilings",
    "maxToolCalls": "ceilings",
    "skillManifest": "context_policy",
    "memoryPolicy": "context_policy",
    "guardrails": "guardrail",
    "maxAnswerChars": "guardrail",
    "subagentPrompt": "subagent_prompt",
    "modelProvider": "model_identity",
    "modelName": "model_identity",
    "temperature": "model_identity",
    "skillDraftIds": "skill_draft",
}

_SURFACE_OP_FIELDS = tuple(FIELD_OPERATOR)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def operator_for_field(field: str) -> str:
    return FIELD_OPERATOR.get(str(field), "unknown")


def classify_ops(target: str, ops: Sequence[Mapping[str, Any]]) -> str:
    """The operator an op set mutates. Surface fields win over a code target."""
    for op in ops or ():
        if not isinstance(op, Mapping):
            continue
        for field in _SURFACE_OP_FIELDS:
            if field in op:
                return operator_for_field(field)
    if str(target or "").strip():
        return "code_patch"
    return "unknown"


def tokens_for_ops(
    target: str,
    ops: Sequence[Mapping[str, Any]],
) -> set[str]:
    """Normalized tokens for one op set: the target plus each op's identity."""
    tokens: set[str] = set()
    destination = str(target or "").strip()
    if destination:
        tokens.add(f"target:{destination}")
    for op in ops or ():
        if not isinstance(op, Mapping):
            continue
        kind = str(op.get("op") or op.get("kind") or "").strip()
        path = str(
            op.get("path") or op.get("fromPath") or op.get("field")
            or op.get("target") or ""
        ).strip()
        tokens.add(f"op:{kind}:{path}")
    return tokens


def op_signature(target: str, ops: Sequence[Mapping[str, Any]]) -> str:
    """A stable identity for one op set (used as a tabu/exclude key)."""
    raw = _canonical({
        "target": str(target or ""),
        "ops": [dict(op) for op in ops or () if isinstance(op, Mapping)],
    }).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def changed_fields(base: Any, candidate: Any) -> list[str]:
    """The surface fields that differ between two snapshots/agent configs."""
    if base is None or candidate is None:
        return []
    try:
        before = base.to_dict(include_digest=False)
        after = candidate.to_dict(include_digest=False)
    except TypeError:
        before = base.to_dict() if hasattr(base, "to_dict") else dict(base)
        after = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
    before.pop("sourceDigest", None)
    after.pop("sourceDigest", None)
    fields: list[str] = []
    for key in sorted(set(before) | set(after)):
        if _canonical(before.get(key)) != _canonical(after.get(key)):
            fields.append(key)
    return fields


def classify_snapshot(base: Any, candidate: Any) -> dict[str, Any]:
    """The typed operators and novelty tokens of a surface change."""
    fields = changed_fields(base, candidate)
    operators = sorted({operator_for_field(field) for field in fields})
    after = (
        candidate.to_dict(include_digest=False)
        if hasattr(candidate, "to_dict") else dict(candidate or {})
    )
    tokens = {f"operator:{name}" for name in operators}
    for field in fields:
        value = _canonical(after.get(field))
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        tokens.add(f"field:{field}:{digest}")
    return {
        "operators": operators,
        "fields": fields,
        "tokens": sorted(tokens),
    }


def jaccard_novelty(
    tokens: set[str],
    pool: Sequence[set[str]],
) -> float:
    """Distance from the closest pool member, in [0, 1]. Empty pool = 1.0."""
    if not pool:
        return 1.0
    closest = 1.0
    for other in pool:
        union = tokens | other
        similarity = len(tokens & other) / len(union) if union else 1.0
        closest = min(closest, 1.0 - similarity)
    return round(max(0.0, min(1.0, closest)), 6)


def is_near_duplicate(
    tokens: set[str],
    pool: Sequence[set[str]],
    min_novelty: float,
) -> bool:
    """True when the closest pool member is closer than the novelty floor."""
    threshold = max(0.0, min(1.0, float(min_novelty)))
    if threshold <= 0:
        return False
    return jaccard_novelty(tokens, pool) < threshold


def filter_novel(
    items: Sequence[tuple[Mapping[str, Any], set[str]]],
    *,
    min_novelty: float,
    exclude_signatures: Sequence[str] = (),
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    """Keep items whose tokens are novel against the kept set and the tabu list.

    Returns `(kept, rejected)` where each rejection names the reason. The
    caller decides whether an empty result is a refusal or an honest "nothing
    new to try".
    """
    excluded = {str(item) for item in exclude_signatures if str(item)}
    kept: list[Mapping[str, Any]] = []
    kept_tokens: list[set[str]] = []
    rejected: list[dict[str, Any]] = []
    for payload, tokens in items:
        signature = str(payload.get("signature") or "")
        if signature and signature in excluded:
            rejected.append({
                "signature": signature,
                "reason": "tabu",
                "novelty": 0.0,
            })
            continue
        novelty = jaccard_novelty(tokens, kept_tokens)
        if kept_tokens and is_near_duplicate(tokens, kept_tokens, min_novelty):
            rejected.append({
                "signature": signature,
                "reason": "near_duplicate",
                "novelty": novelty,
            })
            continue
        kept.append(payload)
        kept_tokens.append(tokens)
    return kept, rejected


__all__ = [
    "FIELD_OPERATOR",
    "OPERATORS",
    "changed_fields",
    "classify_ops",
    "classify_snapshot",
    "filter_novel",
    "is_near_duplicate",
    "jaccard_novelty",
    "op_signature",
    "operator_for_field",
    "tokens_for_ops",
]
