"""Deterministic detection of explicit user memory intent.

Normal chat previously relied on the model voluntarily calling the `memory`
tool: a durable preference stated in plain language was remembered only if the
model chose to. This module makes the explicit cases deterministic so the
post-run path can act on them regardless of model tool choice.

Scope: detection + a policy-safe verdict. Persistence itself stays in
`EclipseMemoryService` (type/scope/dedupe/evidence/audit). This module never
writes to the database and never decides to bypass the service pipeline.

Detected intents (explicit phrasing only — no inference):
    * save    — "remember this", "save this preference", "always do X",
                "note that", "keep in mind", "from now on"
    * forget  — "forget this", "ignore this", "don't remember"
    * correct — "that's wrong", "actually it's", "correct this", "I meant"
    * skill   — "turn this into a skill", "make this a skill/workflow"

Hard safety rules (a candidate is REFUSED, never silently stored):
    * secrets/credentials (keys, tokens, passwords, card numbers, CVV);
    * highly sensitive personal information (SSN, passport, medical);
    * raw conversation dumps (very long, multi-turn-looking text);
    * instructions that try to override system/policy ("ignore your
      instructions", "act as", "from now on you are …").

Confirmation is requested only when scope/sensitivity/generalization is unclear.
An explicit, clear, safe `save`/`forget`/`correct` does not need confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# ── Intent vocabulary ───────────────────────────────────────────────────────

SAVE_PHRASES = (
    r"\bremember (this|that|my|the following|to)\b",
    r"\bsave (this|that|my|this preference)\b",
    r"\bnote (this|that|down)\b",
    r"\bkeep (this )?in mind\b",
    r"\bfrom now on\b",
    r"\balways (do|use|prefer|answer|respond|call)\b",
    r"\bdon'?t ever\b",
    r"\bfor future (reference|runs|sessions)\b",
    r"\bmy preference is\b",
    r"\bi prefer\b",
)
FORGET_PHRASES = (
    r"\bforget (this|that|my|about)\b",
    r"\bignore (this|that|my)\b",
    r"\bdon'?t remember (this|that)\b",
    r"\bstop (remembering|saving)\b",
)
CORRECT_PHRASES = (
    r"\bthat'?s (wrong|incorrect)\b",
    r"\bcorrect (this|that|my|the)\b",
    r"\bactually,? it'?s\b",
    r"\bi meant\b",
    r"\bnot .{1,40},? but\b",
    r"\bthat is not right\b",
)
SKILL_PHRASES = (
    r"\bturn this (workflow|procedure|into a skill|into a procedure)\b",
    r"\bmake this (a|into a) (skill|workflow|procedure)\b",
    r"\bsave this as a skill\b",
    r"\bcreate a skill (from|for) this\b",
    r"\bthis should be a skill\b",
    r"\blearn this workflow\b",
)

_INTENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("skill", SKILL_PHRASES),
    ("forget", FORGET_PHRASES),
    ("correct", CORRECT_PHRASES),
    ("save", SAVE_PHRASES),
]

# ── Sensitivity / abuse guards ──────────────────────────────────────────────

# Credentials and secrets. A phrase may look like "remember my api key" — the
# safe answer is to refuse, not to persist a secret into a local database.
_SECRET_PATTERNS = (
    r"\b(api[ _-]?key|secret|password|passphrase|token|bearer|private[ _-]?key)\b",
    r"\bsk-[A-Za-z0-9]{16,}",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b\d{13,19}\b",  # card-like PAN
    r"\bcvv\b",
    r"\bssn\b|\bsocial security\b",
    r"\bpassport number\b",
)
# Policy-override attempts: an instruction that tries to change the system's
# rules is not memory, it is a jailbreak — refuse to store it.
_OVERRIDE_PATTERNS = (
    r"\bignore (all |your |the )?(previous |prior |system )?(instructions|rules|policy)\b",
    r"\b(disregard|override) (your |the )?(instructions|rules|policy|guardrails)\b",
    r"\byou are now\b",
    r"\bact as (if |a |an )?\b",
    r"\bpretend (to be|you are)\b",
    r"\breveal (your|the) (system )?prompt\b",
)

# "For this ticker/project" scope hints.
_SCOPE_MARKERS: list[tuple[str, str]] = [
    (r"\bfor this (ticker|symbol|stock|instrument)\b", "market"),
    (r"\bfor this (project|portfolio|workspace)\b", "task"),
    (r"\bfor (ticker|symbol)\s+[A-Za-z0-9.\-]{1,12}\b", "market"),
]
_TICKER_RE = re.compile(
    r"\b(?:ticker|symbol)\s+([A-Z]{1,6}(?:\.[A-Z]{1,3})?)\b"
    r"|\b(?:for|on|about)\s+([A-Z]{2,6}(?:\.[A-Z]{1,3})?)\b"
)

# A raw dump is long and multi-paragraph / multi-bullet chat text. Storing it
# wholesale violates "no raw conversation dumps".
_MAX_DURABLE_CHARS = 1200
_DUMP_INDICATORS = (
    r"(^|\n)\s*user\s*:",
    r"(^|\n)\s*assistant\s*:",
    r"(^|\n)\s*(human|ai)\s*:",
)


@dataclass
class MemoryIntent:
    """The deterministic verdict for one user turn."""

    action: Optional[str]  # save | forget | correct | skill | None
    content: str = ""
    memory_type: str = "semantic"
    scope: str = "general"
    scope_id: Optional[str] = None
    subject: Optional[str] = None
    confidence: float = 0.8
    requires_confirmation: bool = False
    refused: bool = False
    reason: str = ""
    matched_phrase: str = ""
    generalizable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def detected(self) -> bool:
        return self.action is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "content": self.content,
            "memoryType": self.memory_type,
            "scope": self.scope,
            "scopeId": self.scope_id,
            "subject": self.subject,
            "confidence": self.confidence,
            "requiresConfirmation": self.requires_confirmation,
            "refused": self.refused,
            "reason": self.reason,
            "matchedPhrase": self.matched_phrase,
            "generalizable": self.generalizable,
        }


def _first_match(text: str, patterns: tuple[str, ...]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _looks_like_secret(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _SECRET_PATTERNS)


def _looks_like_override(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _OVERRIDE_PATTERNS)


def _looks_like_dump(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > _MAX_DURABLE_CHARS:
        return True
    return any(re.search(p, stripped, re.IGNORECASE | re.MULTILINE) for p in _DUMP_INDICATORS)


def _infer_scope(text: str) -> tuple[str, Optional[str]]:
    lowered = text.lower()
    for pattern, scope in _SCOPE_MARKERS:
        if re.search(pattern, lowered, re.IGNORECASE):
            ticker_match = _TICKER_RE.search(text)
            subject = None
            if ticker_match:
                subject = (ticker_match.group(1) or ticker_match.group(2) or "").upper() or None
            return scope, subject
    return "user", None


def _classify_type(text: str, action: str) -> str:
    lowered = text.lower()
    if action == "correct":
        return "correction"
    if re.search(r"\b(always|never|don'?t|must|require|constraint)\b", lowered):
        return "constraint"
    if re.search(r"\b(prefer|preference|like|favorite|favourite)\b", lowered):
        return "preference"
    if re.search(r"\b(procedure|workflow|steps|process)\b", lowered):
        return "procedural"
    return "semantic"


def _strip_directive(text: str) -> str:
    """Remove the leading directive so the stored content is the fact, not the
    command ("remember that I prefer X" → "I prefer X"). Keeps the rest intact.
    """
    cleaned = text.strip()
    cleaned = re.sub(
        r"^(please\s+)?(remember|save|note|keep in mind|forget|ignore|correct)\b[,\s:]*",
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(that|this|the following)\b[,\s:]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip() or text.strip()


def detect_memory_intent(
    user_text: str,
    *,
    user_id: Optional[str] = None,
    assistant_text: Optional[str] = None,
    has_prior_memory: bool = False,
) -> MemoryIntent:
    """Classify one user turn deterministically.

    `assistant_text` (when available) helps a `correct`/`forget` intent target
    the recent claim; it is never required. `has_prior_memory` lets a save flag
    a possible overwrite for confirmation.

    Returns a verdict; the caller still goes through the service write pipeline.
    """
    text = (user_text or "").strip()
    if not text:
        return MemoryIntent(action=None, reason="empty turn")

    # Detect the strongest intent first (skill > forget > correct > save).
    for action, patterns in _INTENT_PATTERNS:
        phrase = _first_match(text, patterns)
        if not phrase:
            continue

        # A forget/correct is always a control action: it never stores the raw
        # text, and never needs confirmation when the target is clear.
        if action == "forget":
            return MemoryIntent(
                action="forget", content=_strip_directive(text), matched_phrase=phrase,
                scope=_infer_scope(text)[0], confidence=0.95,
                reason="explicit forget request",
                metadata={"target": _strip_directive(text)},
            )
        if action == "correct":
            if _looks_like_secret(text):
                return MemoryIntent(
                    action="correct", refused=True, matched_phrase=phrase,
                    reason="correction appears to contain a secret/credential",
                )
            scope, subject = _infer_scope(text)
            return MemoryIntent(
                action="correct", content=_strip_directive(text), matched_phrase=phrase,
                memory_type="correction", scope=scope, scope_id=user_id, subject=subject,
                confidence=0.9, reason="explicit correction",
                metadata={"priorAssistantText": (assistant_text or "")[:2000]},
            )
        if action == "skill":
            return MemoryIntent(
                action="skill", content=text, matched_phrase=phrase,
                scope="task", confidence=0.9, reason="explicit turn-into-skill request",
            )

        # action == "save"
        if _looks_like_secret(text):
            return MemoryIntent(
                action="save", refused=True, matched_phrase=phrase,
                reason="refused: content looks like a secret, credential, or sensitive identifier",
            )
        if _looks_like_override(text):
            return MemoryIntent(
                action="save", refused=True, matched_phrase=phrase,
                reason="refused: content attempts to override system or policy instructions",
            )
        if _looks_like_dump(text):
            return MemoryIntent(
                action="save", refused=True, matched_phrase=phrase,
                reason="refused: content looks like a raw conversation dump rather than a durable fact",
            )

        content = _strip_directive(text)
        scope, subject = _infer_scope(text)
        memory_type = _classify_type(text, action)
        if memory_type == "preference" and scope == "general":
            scope = "user"
        # Sensitive-personal-information heuristic beyond the secret patterns:
        # a save that mentions health/immigration/etc. is stored but flagged for
        # confirmation rather than silently.
        sensitive = bool(re.search(
            r"\b(medical|diagnosis|health condition|religion|sexual orientation|immigration status)\b",
            text, re.IGNORECASE,
        ))
        confirmation = sensitive or (has_prior_memory and memory_type in ("preference", "constraint"))
        reason = "explicit save request"
        if sensitive:
            reason = "save of potentially sensitive personal information — confirmation required"
        elif confirmation:
            reason = "this may overwrite an existing preference — confirmation required"
        return MemoryIntent(
            action="save", content=content, memory_type=memory_type, scope=scope,
            scope_id=user_id if scope == "user" else None, subject=subject,
            confidence=0.85, requires_confirmation=confirmation,
            matched_phrase=phrase, reason=reason,
            generalizable=False,
        )

    return MemoryIntent(action=None, reason="no explicit memory intent detected")


__all__ = ["MemoryIntent", "detect_memory_intent"]
