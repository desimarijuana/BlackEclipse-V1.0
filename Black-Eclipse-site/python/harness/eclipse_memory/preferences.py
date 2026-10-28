"""Learned preferences — deterministic, evidence-backed personalization.

A *preference* is different from a stated fact. A single request ("show me a
table") is a task instruction; the same request across several runs is evidence
of a stable preference. This module turns that evidence into an INERT suggestion
(never a recalled memory) and lets the existing memory gate own the write when
the user accepts it.

Design rules (deliberate):

  * Deterministic and lexical. No model, no embeddings, no network. Every
    inference has a visible trigger phrase and a bounded evidence excerpt.
  * Conservative. A dimension is only inferred when at least three observations
    across three distinct runs agree; an ambiguous turn (two opposite values in
    the same dimension) is ignored.
  * Safe. Style/format dimensions only. No sensitive traits, identity, health,
    politics, finances, or current market facts are ever inferred.
  * Inert. A suggestion is not memory. Accepting it goes through the ONE write
    gate; dismissing it suppresses the same suggestion for a cooling-off period.
  * One store. Observations live in `eclipse-memory.db` (PreferenceObservation);
    there is no second preference database and no second write pipeline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Optional

from .db import now_iso
from .decision import looks_like_secret

PREFERENCE_MODE_VALUES = ("off", "ask", "auto")

#: The closed preference vocabulary. Adding a dimension is a deliberate change:
#: the UI, policy defaults, prompt profile and tests all read this mapping.
DIMENSIONS: dict[str, dict[str, Any]] = {
    "answer_format": {
        "label": "Answer format",
        "values": {
            "tables": "User prefers answers formatted as tables.",
            "bullets": "User prefers answers formatted as bullet points.",
            "prose": "User prefers answers written as prose paragraphs.",
            "charts": "User prefers answers to include charts or graphs.",
        },
    },
    "answer_length": {
        "label": "Answer length",
        "values": {
            "concise": "User prefers concise, brief answers.",
            "detailed": "User prefers detailed, in-depth answers.",
        },
    },
    "tone": {
        "label": "Tone",
        "values": {
            "direct": "User prefers a direct, no-fluff tone.",
            "casual": "User prefers a casual, conversational tone.",
            "formal": "User prefers a formal, professional tone.",
        },
    },
    "research_depth": {
        "label": "Research depth",
        "values": {
            "quick": "User prefers quick, high-level research answers.",
            "deep": "User prefers deep, thorough research.",
        },
    },
}

DIMENSION_KEYS = tuple(DIMENSIONS)


@dataclass(frozen=True)
class PreferenceSignal:
    dimension: str
    value: str
    confidence: float
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


# (dimension, value, compiled pattern, confidence). Patterns are intentionally
# narrow: they match a REQUEST/format instruction, not a passing mention.
_PATTERNS: tuple[tuple[str, str, "re.Pattern[str]", float], ...] = (
    (
        "answer_format", "tables",
        re.compile(r"\b(?:use|show|give|format|present|put|lay out)\b[^.\n]{0,30}\btables?\b|\btabular\b", re.I),
        0.65,
    ),
    (
        "answer_format", "bullets",
        re.compile(r"\b(?:use|show|give|format|present)\b[^.\n]{0,30}\bbullets?\b|\bbullet points?\b", re.I),
        0.65,
    ),
    (
        "answer_format", "prose",
        re.compile(r"\b(?:prose|paragraph form|in paragraphs)\b", re.I),
        0.6,
    ),
    (
        "answer_format", "charts",
        re.compile(r"\b(?:use|show|give|include|add)\b[^.\n]{0,30}\b(?:charts?|graphs?|plots?)\b", re.I),
        0.6,
    ),
    (
        "answer_length", "concise",
        re.compile(r"\b(?:be|keep it|make it|stay)\s+(?:brief|concise|short|terse)\b|\bconcise\b|\bbrevi?ty\b|\bterse\b", re.I),
        0.7,
    ),
    (
        "answer_length", "detailed",
        re.compile(r"\b(?:be|make it|go|give me)\s+(?:detailed|in[- ]depth|thorough)\b|\bdetailed\b|\bin[- ]depth\b|\bthorough\b", re.I),
        0.7,
    ),
    (
        "tone", "direct",
        re.compile(r"\b(?:be|keep it)\s+direct\b|\bdirect\b|\bblunt\b|\bno fluff\b|\bget to the point\b", re.I),
        0.6,
    ),
    (
        "tone", "casual",
        re.compile(r"\b(?:be|keep it)\s+casual\b|\bcasual\b|\bconversational\b", re.I),
        0.6,
    ),
    (
        "tone", "formal",
        re.compile(r"\b(?:be|keep it)\s+formal\b|\bformal\b|\bprofessional tone\b", re.I),
        0.6,
    ),
    (
        "research_depth", "deep",
        re.compile(r"\b(?:deep research|deep dive|thorough research|research deeply|go deep)\b", re.I),
        0.65,
    ),
    (
        "research_depth", "quick",
        re.compile(r"\b(?:quick look|quick research|brief research|just a summary|high[- ]level)\b", re.I),
        0.6,
    ),
)

_MIN_EVIDENCE_CHARS = 2

# Reverse index: the exact statement text -> (dimension, value). Explicit user
# preferences are stored as prose and carry no structuredData, so this is how the
# learner avoids proposing something the user already stated.
_STATEMENT_INDEX: dict[str, tuple[str, str]] = {
    text.strip().lower(): (dimension, value)
    for dimension, spec in DIMENSIONS.items()
    for value, text in (spec.get("values") or {}).items()
}


def infer(text: str) -> list[PreferenceSignal]:
    """Infer stable-preference signals from one turn.

    Ambiguity is resolved conservatively: if one dimension yields two different
    values in the same turn ("be brief but detailed"), that dimension is dropped.
    The evidence excerpt is the matched span only, never the whole message, so a
    ticker/amount elsewhere in the turn is not copied into the observation.
    """
    source = (text or "").strip()
    if len(source) < _MIN_EVIDENCE_CHARS:
        return []
    if looks_like_secret(source):
        return []
    by_dimension: dict[str, list[PreferenceSignal]] = {}
    for dimension, value, pattern, confidence in _PATTERNS:
        match = pattern.search(source)
        if match is None:
            continue
        evidence = re.sub(r"\s+", " ", match.group(0)).strip()[:160]
        if not evidence or looks_like_secret(evidence):
            continue
        by_dimension.setdefault(dimension, []).append(
            PreferenceSignal(dimension, value, confidence, evidence)
        )
    signals: list[PreferenceSignal] = []
    for dimension, found in by_dimension.items():
        values = {item.value for item in found}
        if len(values) != 1:
            continue
        signals.append(max(found, key=lambda item: item.confidence))
    return signals


def statement(dimension: str, value: str) -> str:
    return str(((DIMENSIONS.get(dimension) or {}).get("values") or {}).get(value) or "")


def signature(user_id: Optional[str], dimension: str, value: str) -> str:
    raw = f"preference|{user_id or ''}|{dimension}|{value}".lower()
    return "pref_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def record_observations(
    store: Any,
    text: str,
    *,
    user_id: Optional[str],
    run_id: Optional[str],
    session_id: Optional[str] = None,
    source: str = "turn",
) -> list[dict[str, Any]]:
    """Infer and persist observations for one turn. Never raises."""
    out: list[dict[str, Any]] = []
    for signal in infer(text):
        recorded = store.record_preference_observation(
            user_id=user_id,
            dimension=signal.dimension,
            value=signal.value,
            confidence=signal.confidence,
            evidence_text=signal.evidence,
            run_id=run_id,
            session_id=session_id,
            source=source,
        )
        if recorded:
            out.append(recorded)
    if out:
        try:
            store.prune_preference_observations()
        except Exception:  # noqa: BLE001 - pruning is best-effort
            pass
    return out


def _num(settings: dict[str, Any], key: str, default: float) -> float:
    """Policy lookup that treats 0 as a valid explicit value (not 'unset')."""
    value = settings.get(key)
    return default if value is None else value


def _dimension_enabled(settings: dict[str, Any], dimension: str) -> bool:
    table = settings.get("preference_dimensions")
    if not isinstance(table, dict):
        return True
    return bool(table.get(dimension, True))


def _consistency(groups: list[dict[str, Any]], dimension: str, value: str) -> float:
    """Share of this dimension's observations that agree on ``value``."""
    total = sum(
        int(group.get("observationCount") or 0)
        for group in groups
        if group.get("dimension") == dimension
    )
    if total <= 0:
        return 0.0
    matching = sum(
        int(group.get("observationCount") or 0)
        for group in groups
        if group.get("dimension") == dimension and group.get("value") == value
    )
    return matching / total


def _eligible(
    group: dict[str, Any],
    groups: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[bool, float, str]:
    dimension = str(group.get("dimension") or "")
    value = str(group.get("value") or "")
    if dimension not in DIMENSIONS or value not in (DIMENSIONS[dimension].get("values") or {}):
        return False, 0.0, "unknown dimension/value"
    if not _dimension_enabled(settings, dimension):
        return False, 0.0, "dimension disabled"
    observations = int(group.get("observationCount") or 0)
    distinct = int(group.get("distinctRuns") or 0)
    min_obs = int(_num(settings, "preference_min_observations", 3))
    min_runs = int(_num(settings, "preference_min_distinct_runs", 3))
    if observations < min_obs:
        return False, 0.0, f"needs {min_obs} observations (has {observations})"
    if distinct < min_runs:
        return False, 0.0, f"needs {min_runs} distinct runs (has {distinct})"
    consistency = _consistency(groups, dimension, value)
    if consistency < float(_num(settings, "preference_min_consistency", 0.6)):
        return False, 0.0, f"consistency {consistency:.2f} below threshold"
    base = float(group.get("confidence") or 0.6)
    confidence = min(
        0.95,
        base
        + min(0.15, 0.03 * max(0, distinct - min_runs))
        + min(0.1, 0.05 * max(0, observations - min_obs)),
    )
    if confidence < float(_num(settings, "preference_confidence_threshold", 0.6)):
        return False, confidence, "confidence below threshold"
    return True, round(confidence, 3), "sufficient repeated evidence"


def _active_preference_keys(service: Any, user_id: Optional[str]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    try:
        rows = service.store.list_memories(
            memory_type="preference", scope="user",
            scope_id=user_id, include_inactive=False, limit=500,
        )
    except Exception:  # noqa: BLE001
        return keys
    for row in rows:
        subject = str(row.get("subject") or "")
        structured = row.get("structuredData") or {}
        value = str((structured or {}).get("value") or "")
        if subject and value:
            keys.add((subject, value))
        content = str(row.get("content") or "").strip().lower()
        known = _STATEMENT_INDEX.get(content)
        if known:
            keys.add(known)
    return keys


def _suppressed(
    service: Any, *, user_id: Optional[str], suggestion_signature: str, settings: dict[str, Any],
) -> bool:
    """A dismissed/accepted suggestion suppresses the same inference.

    A dismissal cools off for `preference_suppression_days` (default 30); after
    that, genuinely new evidence may ask again. An accepted suggestion is a
    durable preference and is skipped by the active-key check instead.
    """
    try:
        existing = service.store.find_suggestion_by_signature(
            suggestion_signature, scope_id=user_id,
        )
    except Exception:  # noqa: BLE001
        return False
    if not existing:
        return False
    status = str(existing.get("status") or "")
    if status in ("pending", "accepted"):
        # Already asked, or already an active preference: do not ask twice.
        return True
    if status != "dismissed":
        return False
    days = int(_num(settings, "preference_suppression_days", 30))
    if days <= 0:
        return False
    decided = str(existing.get("decidedAt") or existing.get("createdAt") or "")
    if not decided:
        return False
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    try:
        stamp = decided.replace("Z", "+00:00")
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - when < timedelta(days=days)


def learn(
    service: Any,
    *,
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run the preference-learning pass and create inert suggestions.

    Returns a bounded, honest summary. Never raises: a preference pass is
    personalization, not control flow.
    """
    try:
        settings_alive = service.policy.get_all()
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": "policy unavailable", "created": [], "saved": []}
    if settings_alive.get("memory_enabled") is False:
        return {"ok": True, "mode": "off", "reason": "memory disabled", "created": [], "saved": []}
    mode = str(settings_alive.get("preference_learning_mode") or "ask")
    if mode == "off":
        return {"ok": True, "mode": "off", "reason": "preference learning disabled", "created": [], "saved": []}
    if mode not in PREFERENCE_MODE_VALUES:
        mode = "ask"
    # `memory_mode=off` is the user's statement that automatic memory should not
    # produce anything. Even an inert preference prompt would contradict that;
    # an explicit "remember this" still works through the turn gate.
    if str(settings_alive.get("memory_mode") or "") == "off":
        return {"ok": True, "mode": mode, "reason": "memory_mode is off", "created": [], "saved": []}

    groups = service.store.preference_observation_groups(user_id=user_id)
    active = _active_preference_keys(service, user_id)
    active_dimensions = {dimension for dimension, _value in active}
    created: list[dict[str, Any]] = []
    saved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_dimensions: set[str] = set()

    for group in groups:
        dimension = str(group.get("dimension") or "")
        value = str(group.get("value") or "")
        if dimension in seen_dimensions:
            skipped.append({"dimension": dimension, "value": value, "reason": "dimension already decided"})
            continue
        ok, confidence, reason = _eligible(group, groups, settings_alive)
        if not ok:
            if "unknown" not in reason:
                skipped.append({"dimension": dimension, "value": value, "reason": reason})
            continue
        if dimension in active_dimensions:
            seen_dimensions.add(dimension)
            skipped.append({
                "dimension": dimension, "value": value,
                "reason": "the dimension already has an active preference",
            })
            continue
        suggestion_signature = signature(user_id, dimension, value)
        if _suppressed(service, user_id=user_id, suggestion_signature=suggestion_signature, settings=settings_alive):
            seen_dimensions.add(dimension)
            skipped.append({"dimension": dimension, "value": value, "reason": "recently dismissed"})
            continue
        content = statement(dimension, value)
        if not content:
            continue
        structured = {
            "dimension": dimension,
            "value": value,
            "observationCount": int(group.get("observationCount") or 0),
            "distinctRuns": int(group.get("distinctRuns") or 0),
            "confidence": confidence,
            "evidenceText": group.get("evidenceText"),
            "firstSeenAt": group.get("firstSeenAt"),
            "lastSeenAt": group.get("lastSeenAt"),
        }
        if mode == "auto":
            from dataclasses import replace  # noqa: PLC0415

            from .decision import authorize_proposal  # noqa: PLC0415

            decision = authorize_proposal(
                content=content,
                provenance="run_analysis",
                user_id=user_id,
                memory_type="preference",
                scope="user",
                scope_id=user_id,
                subject=dimension,
                confidence=confidence,
                settings=settings_alive,
                evidence={"kind": "preference_observations", **structured},
            )
            # Carry the evidence counts through the gate so a saved memory (or a
            # gate-staged suggestion) can explain WHY it exists.
            decision = replace(
                decision,
                metadata={**dict(getattr(decision, "metadata", {}) or {}), "structuredData": structured},
            )
            outcome = service.commit_decision(
                decision, run_id=run_id, user_id=user_id,
            )
            if outcome.get("ok"):
                saved.append({"dimension": dimension, "value": value, "memoryId": (outcome.get("memory") or {}).get("id")})
                seen_dimensions.add(dimension)
                continue
            if outcome.get("action") == "suggested":
                # The gate itself staged the suggestion (memory_mode=ask). Do not
                # create a second one below.
                staged = outcome.get("suggestion") or {}
                created.append({
                    "dimension": dimension, "value": value,
                    "suggestionId": staged.get("id"),
                })
                seen_dimensions.add(dimension)
                continue
            # A refusal (full / disabled / conflict) falls through to an inert
            # suggestion so the user still sees the evidence instead of silence.
        suggestion_id = service.store.save_suggestion({
            "runId": run_id,
            "scope": "user",
            "scopeId": user_id,
            "subject": dimension,
            "memoryType": "preference",
            "content": content,
            "reason": (
                f"Learned from {structured['observationCount']} observations across "
                f"{structured['distinctRuns']} runs ({int(confidence * 100)}% confidence). "
                "Accept to remember, dismiss to stop asking."
            ),
            "provenance": "preference_learning",
            "confidence": confidence,
            "signature": suggestion_signature,
            "status": "pending",
            "structuredData": structured,
        })
        service.store.append_memory_event(
            "memory.preference_suggested",
            run_id=run_id,
            data={"suggestionId": suggestion_id, **structured},
        )
        created.append({"dimension": dimension, "value": value, "suggestionId": suggestion_id})
        seen_dimensions.add(dimension)

    return {
        "ok": True,
        "mode": mode,
        "created": created,
        "saved": saved,
        "skipped": skipped,
        "observationCount": service.store.preference_observation_count(user_id=user_id),
    }


def summary(service: Any, *, user_id: Optional[str] = None) -> dict[str, Any]:
    """The read model for the Personal Memory → Preferences surface."""
    try:
        settings = service.policy.get_all()
    except Exception:  # noqa: BLE001
        settings = {}
    active = service.store.list_memories(
        memory_type="preference", scope="user", scope_id=user_id,
        include_inactive=False, limit=200,
    )
    suggestions = [
        item for item in service.store.list_suggestions(status="pending", scope_id=user_id, limit=200)
        if str(item.get("provenance") or "") == "preference_learning"
    ]
    groups = service.store.preference_observation_groups(user_id=user_id)
    return {
        "success": True,
        "mode": settings.get("preference_learning_mode") or "ask",
        "enabled": settings.get("memory_enabled") is not False,
        "dimensions": [
            {
                "id": key,
                "label": (DIMENSIONS[key].get("label") or key),
                "enabled": _dimension_enabled(settings, key),
                "values": list((DIMENSIONS[key].get("values") or {}).keys()),
            }
            for key in DIMENSION_KEYS
        ],
        "active": active,
        "suggestions": suggestions,
        "observations": groups,
        "observationCount": service.store.preference_observation_count(user_id=user_id),
        "thresholds": {
            "minObservations": int(_num(settings, "preference_min_observations", 3)),
            "minDistinctRuns": int(_num(settings, "preference_min_distinct_runs", 3)),
            "minConsistency": float(_num(settings, "preference_min_consistency", 0.6)),
            "confidence": float(_num(settings, "preference_confidence_threshold", 0.6)),
            "suppressionDays": int(_num(settings, "preference_suppression_days", 30)),
        },
        "readOnly": False,
        "generatedAt": now_iso(),
    }


__all__ = [
    "DIMENSIONS",
    "DIMENSION_KEYS",
    "PREFERENCE_MODE_VALUES",
    "PreferenceSignal",
    "infer",
    "learn",
    "record_observations",
    "signature",
    "statement",
    "summary",
]
