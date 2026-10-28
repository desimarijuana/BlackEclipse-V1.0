"""Memory decision contract — the ONE authorization gate for durable memory.

Every path that can create or alter a durable memory, a suggestion, a
correction/forget action, or a learning candidate must obtain a
``MemoryDecision`` here before anything is written:

  * deterministic chat intent (``eclipse_memory.intent``);
  * the model-facing ``memory`` tool;
  * a direct UI save/update;
  * corrections and forget operations;
  * run analysis / automatic capture;
  * learning candidates and generated drafts.

The gate validates a proposal against the *actual* user message, identity,
scope, provenance, category, evidence, duplication, sensitivity, policy and
privacy rules. A model may propose a decision, but it cannot authorize its own
write: the tool path is re-checked here against the user turn. Tool output,
retrieved memory, attached documents and web content are never user intent.

Outcomes (exactly four):

  * ``save``        — high-value, durable information permitted by policy. Persist
                      now (explicit user intent, or automatic-selective strong
                      evidence).
  * ``suggest``     — potentially useful durable information, but intent or scope
                      is unclear. Do NOT persist; surface a quiet Save/Dismiss
                      control (inert, non-recalled).
  * ``history_only``— relevant to this task/conversation and searchable in
                      conversation/run history, but not worth recalling as durable
                      memory.
  * ``ignore``      — low-value, redundant, temporary, unsafe, unsupported or
                      irrelevant.

The system must usually choose ``history_only`` or ``ignore``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

OUTCOMES = frozenset({"save", "suggest", "history_only", "ignore"})

# Provenance of a proposed write. Only these are permitted (mirrors
# `service.VALID_SOURCES` but names the *path*, not the stored source label).
PROVENANCES = frozenset(
    {
        "explicit_user",   # deterministic "remember this" on the user turn
        "memory_tool",     # the model-facing `memory` tool
        "ui_save",         # an authorized operator saved through the UI
        "correction",      # an explicit "correct this"
        "forget",          # an explicit "forget this"
        "run_analysis",    # deterministic post-run lesson capture
        "skill_lesson",    # an execution-lesson memory from a skill run
        "system",          # an explicitly recorded system/architecture decision
    }
)

# A model-facing write may only persist when the user turn itself authorised it
# or the content is a clearly durable user preference. Everything else is a
# suggestion at most.
_MODEL_WRITE_REQUIRES_USER_INTENT = True

# ── Content guards (mirror intent.py's hard safety rules) ───────────────────
# Kept here so the gate is self-contained: any path (tool/UI/analysis) is
# subject to the same privacy rules, not just the deterministic turn path.
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
_OVERRIDE_PATTERNS = (
    r"\bignore (all |your |the )?(previous |prior |system )?(instructions|rules|policy)\b",
    r"\b(disregard|override) (your |the )?(instructions|rules|policy|guardrails)\b",
    r"\byou are now\b",
    r"\bact as (if |a |an )?\b",
    r"\bpretend (to be|you are)\b",
    r"\breveal (your|the) (system )?prompt\b",
)
_DUMP_INDICATORS = (
    r"(^|\n)\s*user\s*:",
    r"(^|\n)\s*assistant\s*:",
    r"(^|\n)\s*(human|ai)\s*:",
)
_MAX_DURABLE_CHARS = 1200

# Financial facts are NEVER durable memory. Current prices, valuation
# estimates, earnings results, predictions and unverified claims must be
# re-retrieved from JDdS/research, never recalled from memory.
_FINANCIAL_FACT_PATTERNS = (
    r"\b(share price|stock price|current price|market cap|market capitalisation|"
    r"market capitalization|valuation|enterprise value|p/?e ratio|earnings|eps|"
    r"dividend yield|revenue (is|was|of)|net income|profit margin)\b",
    r"(?:[$₹€£]|\brs\.?\b|\bpkr\b|\busd\b|\binr\b|\baed\b|\beur\b|\bgbp\b)\s?\d",
    r"\b\d+(?:\.\d+)?\s?%",
    r"\b(predict(?:ed|ion)?|forecast|target price|will (rise|fall|go up|go down)|expected to (rise|fall|reach))\b",
    # A quoted level: "trading at 190", "closed at $5", "worth 12.30".
    r"\b(trading at|trades? at|traded at|closed at|opened at|priced at|quoted at|worth|now at)\s?[$₹€£]?\d",
    # "<TICKER> is/was at <number>" (a bare ticker-plus-level statement).
    r"\b[a-zA-Z]{1,5}\b\s+(?:is|was|are|were)\s+(?:now\s+)?(?:at|trading at)\s+\d",
)
# A durable convention/rule is procedural or constraint-like and has no market
# figure. A repeated correction can qualify.
_CONVENTION_PATTERNS = (
    r"\b(always|never|from now on|by convention|convention|standard|rule|"
    r"whenever|when .*, (?:use|prefer|report|state))\b",
)
# One-off / task-scoped markers: a statement about *this* task is run-only.
_ONE_OFF_PATTERNS = (
    r"\bfor this (task|run|turn|one|request|time|analysis)\b",
    r"\b(for now|this time|today only|just this once|in this run)\b",
)

# A durable preference inside a longer prompt ("First: I prefer ..."). Only the
# preference clause is stored; the surrounding task instructions are not.
_PREFERENCE_CLAUSE_RE = re.compile(
    r"(?i)\b(?:i (?:prefer|like|always|never)|my preference is|we (?:always|never))"
    r"\b[^.!?\n]{2,300}"
)


def _preference_clause(text: str) -> str:
    match = _PREFERENCE_CLAUSE_RE.search(text or "")
    if not match:
        return ""
    return match.group(0).strip(" \t:;-")


_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|thanks|thank you|good (morning|afternoon|evening)|"
    r"cheers|ok|okay|sure|cool|nice)\b[\s!.,]*$",
    re.IGNORECASE,
)

# Explicit memory directives that save immediately (no recurrence needed),
# as opposed to a bare convention directive.
SAVE_DIRECTIVE_PHRASES = (
    r"\bremember\b",
    r"\bsave (this|that|my)\b",
    r"\bnote (this|that|down)\b",
    r"\bkeep (this )?in mind\b",
    r"\bfrom now on\b",
    r"\bfor future (reference|runs|sessions)\b",
)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def looks_like_secret(text: str) -> bool:
    return _matches(text, _SECRET_PATTERNS)


# A tighter guard for the persistence layer: matches an actual credential VALUE
# (a key-shaped token or an assignment `name: value`), not merely the word
# "secret"/"token". The broad `_SECRET_PATTERNS` remain the decision-gate guard;
# this narrower set avoids refusing a benign sentence that mentions the word.
_CREDENTIAL_VALUE_PATTERNS = (
    r"\bsk-[A-Za-z0-9]{16,}",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b(api[ _-]?key|passphrase|password|bearer|private[ _-]?key|token)\b\s*[:=]\s*\S+",
    r"\b\d{13,19}\b",  # card-like PAN
)


def looks_like_credential_value(text: str) -> bool:
    """True when text contains an actual credential value — used as
    defense-in-depth at the one persistence path, without over-blocking a
    sentence that merely mentions the word 'secret'/'token'."""
    return _matches(text, _CREDENTIAL_VALUE_PATTERNS)


def looks_like_override(text: str) -> bool:
    return _matches(text, _OVERRIDE_PATTERNS)


def looks_like_dump(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) > _MAX_DURABLE_CHARS:
        return True
    return _matches(stripped, _DUMP_INDICATORS)


def looks_like_financial_fact(text: str) -> bool:
    """True when the text carries a market/company figure that must be
    re-retrieved rather than remembered."""
    return _matches(text or "", _FINANCIAL_FACT_PATTERNS)


def content_signature(content: str) -> str:
    import hashlib

    normalized = re.sub(r"\s+", " ", (content or "").strip().lower())[:400]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


@dataclass
class MemoryDecision:
    """The deterministic, authorized outcome for one proposed memory action."""

    outcome: str  # save | suggest | history_only | ignore
    action: Optional[str] = None  # save | forget | correct | skill | None
    reason: str = ""
    content: str = ""
    memory_type: str = "semantic"
    scope: str = "general"
    scope_id: Optional[str] = None
    subject: Optional[str] = None
    confidence: float = 0.5
    importance: float = 0.5
    provenance: str = "explicit_user"
    evidence: Optional[dict[str, Any]] = None
    refused: bool = False
    requires_confirmation: bool = False
    requires_clarification: bool = False
    financial: bool = False
    matched_phrase: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def will_persist(self) -> bool:
        return self.outcome == "save" and self.action in ("save", "forget", "correct")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "action": self.action,
            "reason": self.reason,
            "content": self.content,
            "memoryType": self.memory_type,
            "scope": self.scope,
            "scopeId": self.scope_id,
            "subject": self.subject,
            "confidence": self.confidence,
            "importance": self.importance,
            "provenance": self.provenance,
            "refused": self.refused,
            "requiresConfirmation": self.requires_confirmation,
            "requiresClarification": self.requires_clarification,
            "financial": self.financial,
            "matchedPhrase": self.matched_phrase,
        }


def _ignore(reason: str, *, provenance: str = "", content: str = "", **kw: Any) -> MemoryDecision:
    return MemoryDecision(outcome="ignore", reason=reason, provenance=provenance, content=content, **kw)


def _history_only(reason: str, *, content: str = "", **kw: Any) -> MemoryDecision:
    return MemoryDecision(outcome="history_only", reason=reason, content=content, **kw)


def _classify_type(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(always|never|don'?t|must|require|constraint)\b", lowered):
        return "constraint"
    if re.search(r"\b(prefer|preference|like|favorite|favourite)\b", lowered):
        return "preference"
    if re.search(r"\b(procedure|workflow|steps|process)\b", lowered):
        return "procedural"
    return "semantic"


def _infer_scope(text: str) -> tuple[str, Optional[str]]:
    """Reuse the deterministic scope hints from intent detection."""
    from .intent import _infer_scope as _intent_scope  # noqa: PLC0415

    return _intent_scope(text)


def resolve_owner_scope(
    scope: str,
    scope_id: Optional[str],
    *,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Resolve the durable-memory owner for a write.

    A conversation-scoped run (a bot chat or a group-room member turn) has no
    signed-in user, so a personal (``user``) fact belongs to that conversation's
    PRIVATE bucket rather than an unattributable user row. An explicit
    ``conversation`` scope requires a conversation id; without one it degrades to
    the user/general owner so a stray request can never create an orphan bucket.
    Outside a conversation the behaviour is unchanged.
    """
    if scope == "conversation":
        if conversation_id:
            return "conversation", conversation_id
        return ("user", user_id) if user_id else ("general", None)
    if scope == "user":
        if conversation_id and not user_id:
            return "conversation", conversation_id
        return "user", (scope_id or user_id)
    return scope, scope_id


# ── The gate ────────────────────────────────────────────────────────────────


def decide_turn(
    user_text: str,
    *,
    user_id: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
    has_prior_memory: bool = False,
    recently_dismissed: bool = False,
    recurring: bool = False,
    is_skill_run: bool = False,
    conversation_id: Optional[str] = None,
) -> MemoryDecision:
    """Authorize the memory disposition of one user turn.

    Explicit save/forget/correct/skill commands are always evaluated (this is
    the reliable explicit-intent path; it is not gated by the automatic learning
    mode). Non-explicit durable mentions follow the configured `memory_mode`:
    ``automatic_selective`` saves only strong, low-risk evidence, ``ask_before_saving``
    stages an inert suggestion, and ``off`` keeps the turn history-only.
    """
    settings = settings or {}
    text = (user_text or "").strip()
    if not text:
        return _ignore("empty turn")

    # Never let a skill child-run's rendered input masquerade as user intent.
    if is_skill_run:
        return _ignore("skill child-run input is not user memory intent")

    from .intent import detect_memory_intent  # noqa: PLC0415

    intent = detect_memory_intent(
        text, user_id=user_id, assistant_text=None, has_prior_memory=has_prior_memory
    )

    if intent.refused:
        return MemoryDecision(
            outcome="ignore", action=intent.action, reason=intent.reason,
            content=intent.content, refused=True, matched_phrase=intent.matched_phrase,
            provenance="explicit_user",
        )

    if intent.detected:
        # ── Explicit commands: always honoured (safe/clear ones) ────────────
        if intent.action == "forget":
            return MemoryDecision(
                outcome="save", action="forget", reason=intent.reason,
                content=intent.content, scope=intent.scope, scope_id=user_id,
                subject=intent.subject, confidence=intent.confidence,
                matched_phrase=intent.matched_phrase, provenance="forget",
                metadata=dict(intent.metadata),
            )
        if intent.action == "correct":
            return MemoryDecision(
                outcome="save", action="correct", reason=intent.reason,
                content=intent.content, memory_type="correction", scope=intent.scope,
                scope_id=user_id, subject=intent.subject, confidence=intent.confidence,
                matched_phrase=intent.matched_phrase, provenance="correction",
                metadata=dict(intent.metadata),
            )
        if intent.action == "skill":
            # An explicit learning request creates an inert skill draft through
            # the real persistence path (see graph `_apply_memory_intent`); it is
            # NEVER silently activated. The outcome is history-only here because
            # the skill itself is not a durable memory.
            return MemoryDecision(
                outcome="history_only", action="skill", reason=intent.reason,
                content=intent.content, scope="task",
                matched_phrase=intent.matched_phrase, provenance="explicit_user",
            )

        # action == "save"
        if looks_like_financial_fact(intent.content) or looks_like_financial_fact(text):
            return MemoryDecision(
                outcome="ignore", action="save", reason=(
                    "financial facts (prices, valuations, earnings, predictions) are never "
                    "durable memory — retrieve them when needed"
                ),
                content=intent.content, financial=True, matched_phrase=intent.matched_phrase,
                provenance="explicit_user",
            )
        if _matches(text, _ONE_OFF_PATTERNS):
            # "Always use X for this task" is a one-off instruction, not a
            # durable rule — it applies only to the current run.
            return MemoryDecision(
                outcome="history_only", action="save",
                reason="one-off task instruction — applies to this run only",
                content=intent.content, scope=intent.scope, subject=intent.subject,
                matched_phrase=intent.matched_phrase, provenance="explicit_user",
            )
        # A bare convention ("always use X") is project-specific and may be a
        # one-off instruction. A memory directive ("remember/from now on") is
        # an explicit, immediate save; a bare convention needs recurrence
        # evidence and otherwise flows through the incidental path.
        from .intent import BARE_CONVENTION_PHRASES  # noqa: PLC0415

        is_bare_convention = (
            _matches(intent.matched_phrase or text, BARE_CONVENTION_PHRASES)
            and not _matches(text, SAVE_DIRECTIVE_PHRASES)
        )
        if is_bare_convention:
            # A bare "always use X" convention is handled by the incidental path,
            # which saves it automatically under automatic_selective only once
            # recurrence evidence exists (and records that evidence).
            return _decide_incidental(
                text, user_id=user_id, settings=settings,
                recently_dismissed=recently_dismissed, recurring=recurring,
            )
        if intent.requires_confirmation:
            return MemoryDecision(
                outcome="suggest", action="save", reason=intent.reason,
                content=intent.content, memory_type=intent.memory_type, scope=intent.scope,
                scope_id=user_id if intent.scope == "user" else None, subject=intent.subject,
                confidence=intent.confidence, requires_confirmation=True,
                matched_phrase=intent.matched_phrase, provenance="explicit_user",
            )
        return MemoryDecision(
            outcome="save", action="save", reason=intent.reason,
            content=intent.content, memory_type=intent.memory_type, scope=intent.scope,
            scope_id=user_id if intent.scope == "user" else None, subject=intent.subject,
            confidence=intent.confidence, importance=0.7,
            matched_phrase=intent.matched_phrase, provenance="explicit_user",
        )

    # ── No explicit command: is this incidentally durable? ──────────────────
    return _decide_incidental(
        text, user_id=user_id, settings=settings,
        recently_dismissed=recently_dismissed, recurring=recurring,
        conversation_id=conversation_id,
    )


def _decide_incidental(
    text: str, *, user_id: Optional[str], settings: dict[str, Any],
    recently_dismissed: bool, recurring: bool,
    conversation_id: Optional[str] = None,
) -> MemoryDecision:
    """A casual statement: usually history-only or ignore; under
    ``automatic_selective`` a strong, low-risk fact may save without asking."""
    if _GREETING_RE.match(text):
        return _ignore("greeting — no durable content")
    if looks_like_secret(text):
        return MemoryDecision(
            outcome="ignore", reason="content looks like a secret/credential — not stored",
            content="", refused=True, provenance="explicit_user",
        )
    # A direct user preference ("I prefer …", "my preference is …") is about the
    # user and low-risk; only that clause is considered, not the surrounding
    # task instructions. A project convention ("always / from now on / rule")
    # is a project-specific assertion that needs stronger evidence. A question
    # ("why do I prefer …?") is not a durable statement.
    preference_text = _preference_clause(text)
    if looks_like_financial_fact(preference_text or text):
        return _ignore("financial/market figure belongs to the run, not durable memory")
    if preference_text and looks_like_secret(preference_text):
        return _ignore(
            "the preference clause contains a secret/credential — not stored",
            content="", refused=True,
        )
    # A task-scoped marker anywhere in a long prompt must not suppress a clear,
    # standalone preference clause. Only the clause is stored.
    if not preference_text and _matches(text, _ONE_OFF_PATTERNS):
        return _history_only("task-scoped one-off — searchable history only", content=text)

    is_question = text.rstrip().endswith("?") or bool(re.match(
        r"^\s*(why|what|how|when|where|which|who|do|does|did|can|could|should|"
        r"would|is|are|was|were|will)\b",
        text, re.IGNORECASE,
    ))
    if is_question:
        lead = text
        if preference_text:
            index = text.find(preference_text)
            lead = re.split(r"[.!?\n]", text[:index])[-1].strip() if index > 0 else ""
        starts_as_question = bool(re.match(
            r"(why|what|how|when|where|which|who|do|does|did|can|could|should|"
            r"would|is|are|was|were|will)\b",
            lead, re.IGNORECASE,
        ))
        if starts_as_question or not preference_text:
            return _history_only(
                "question, not a durable statement — searchable history only",
                content=text,
            )
    convention = _matches(text, _CONVENTION_PATTERNS)
    durable = bool(preference_text) or convention
    if not durable:
        return _history_only("not durable information — searchable history only", content=text)

    if recently_dismissed:
        return _history_only("a similar suggestion was recently dismissed", content=text)

    mode = str(settings.get("memory_mode") or "automatic_selective")

    # `off`: never learn automatically; explicit requests are the only path.
    if mode == "off":
        return _history_only("automatic memory learning is off — explicit request required", content=text)

    content = preference_text or text
    scope, subject = _infer_scope(content)
    memory_type = "preference" if preference_text else _classify_type(content)
    if memory_type == "preference" and scope == "general":
        scope = "user"
    scope, scope_id = resolve_owner_scope(
        scope, user_id if scope == "user" else None,
        user_id=user_id, conversation_id=conversation_id,
    )

    if mode == "ask_before_saving":
        return MemoryDecision(
            outcome="suggest", action="save",
            reason="possible durable preference/convention — confirm to remember",
            content=content, memory_type=memory_type, scope=scope, scope_id=scope_id,
            subject=subject, confidence=0.5, importance=0.5, provenance="explicit_user",
        )

    # automatic_selective: strong, low-risk, durable evidence saves without a
    # prompt. A direct user preference qualifies on first statement; a
    # project-specific convention additionally requires recurrence.
    if preference_text:
        pref_scope, pref_sid = resolve_owner_scope(
            "user", user_id, user_id=user_id, conversation_id=conversation_id,
        )
        return MemoryDecision(
            outcome="save", action="save",
            reason="high-confidence, low-risk user preference — saved automatically",
            content=preference_text, memory_type="preference", scope=pref_scope,
            scope_id=pref_sid, subject=subject, confidence=0.75, importance=0.6,
            provenance="explicit_user",
            metadata={"automatic": True, "evidence": "direct user preference"},
        )
    if convention and recurring:
        return MemoryDecision(
            outcome="save", action="save",
            reason="recurring project convention — saved automatically",
            content=content, memory_type=memory_type, scope=scope, scope_id=scope_id,
            subject=subject, confidence=0.6, importance=0.55, provenance="explicit_user",
            metadata={"automatic": True, "evidence": "recurrence"},
        )
    # Not enough evidence yet: keep it as searchable history, do NOT prompt.
    return _history_only(
        "durable-sounding but not yet strong enough evidence — searchable history only",
        content=text,
    )


def authorize_proposal(
    *,
    content: str,
    provenance: str,
    user_message: str = "",
    user_id: Optional[str] = None,
    memory_type: str = "semantic",
    scope: str = "general",
    scope_id: Optional[str] = None,
    subject: Optional[str] = None,
    confidence: float = 0.5,
    settings: Optional[dict[str, Any]] = None,
    evidence: Optional[dict[str, Any]] = None,
    verified: bool = False,
    conversation_id: Optional[str] = None,
) -> MemoryDecision:
    """Validate a proposed write (the model `memory` tool, a UI save, analysis).

    The proposal is checked against the actual user message, identity, scope,
    provenance, category, evidence, privacy rules and policy. A model-facing
    proposal can only ``save`` when the user turn itself carried explicit save
    intent (or for a clearly durable user preference the user just stated);
    otherwise it is downgraded to ``suggest``, ``history_only`` or ``ignore``.
    """
    settings = settings or {}
    text_value = (content or "").strip()
    content = text_value
    provenance = provenance or "memory_tool"

    if provenance not in PROVENANCES:
        return _ignore(f"unsupported provenance {provenance!r}", provenance=provenance, content=text_value)
    if not text_value:
        return _ignore("empty content", provenance=provenance)
    if looks_like_secret(text_value):
        return MemoryDecision(
            outcome="ignore", reason="refused: content looks like a secret, credential, or sensitive identifier",
            content="", refused=True, provenance=provenance,
        )
    if looks_like_override(text_value):
        return MemoryDecision(
            outcome="ignore", reason="refused: content attempts to override system or policy instructions",
            content="", refused=True, provenance=provenance,
        )
    if looks_like_dump(text_value):
        return MemoryDecision(
            outcome="ignore", reason="refused: content looks like a raw conversation dump rather than a durable fact",
            content="", refused=True, provenance=provenance,
        )
    if looks_like_financial_fact(text_value):
        return MemoryDecision(
            outcome="ignore", reason=(
                "financial facts are never durable memory — retrieve them from JDdS/research at answer time"
            ),
            content="", financial=True, provenance=provenance,
        )

    if memory_type not in (
        "episodic", "semantic", "procedural", "preference", "constraint",
        "correction", "observation", "summary",
    ):
        memory_type = "semantic"
    if memory_type == "preference" and scope == "general":
        scope = "user"
    if scope not in ("general", "user", "market", "task", "conversation"):
        scope = "general"
    if scope == "user":
        scope_id = scope_id or user_id
    scope, scope_id = resolve_owner_scope(
        scope, scope_id, user_id=user_id, conversation_id=conversation_id,
    )

    # Operator/UI saves are an explicit human action: authorize as save once the
    # content passed the safety guards above. A correction recorded through the
    # operator/UI path is also an explicit human action (the caller has already
    # captured the wrong→right pair through `record_correction`).
    if provenance in ("ui_save", "system", "correction"):
        return MemoryDecision(
            outcome="save", action="save", reason=f"authorized {provenance} write",
            content=text_value, memory_type=memory_type, scope=scope, scope_id=scope_id,
            subject=subject, confidence=confidence, importance=0.7, provenance=provenance,
            evidence=evidence,
        )

    # Deterministic explicit command already validated by decide_turn; here we
    # only see model/analysis proposals. Validate against the user turn.
    if provenance == "memory_tool":
        from .intent import detect_memory_intent  # noqa: PLC0415

        turn = detect_memory_intent(user_message or "", user_id=user_id)
        explicit_save = turn.detected and turn.action == "save" and not turn.refused
        if explicit_save:
            return MemoryDecision(
                outcome="save", action="save", reason="model save authorized by the explicit user request",
                content=text_value, memory_type=memory_type, scope=scope, scope_id=scope_id,
                subject=subject, confidence=confidence, importance=0.7,
                provenance="memory_tool", evidence=evidence,
            )
        # A clearly durable user preference stated this turn may be saved under
        # automatic_selective (or staged as a suggestion under ask_before_saving).
        # A bare project convention still requires recurrence, so it is not
        # auto-saved from a model proposal.
        user_text = user_message or ""
        direct_preference = bool(re.search(
            r"\b(i (?:prefer|like|always|never)|my preference|we (?:always|never))\b",
            user_text, re.IGNORECASE,
        ))
        durable = direct_preference
        mode = str(settings.get("memory_mode") or "automatic_selective")
        if durable and mode == "automatic_selective":
            return MemoryDecision(
                outcome="save", action="save",
                reason="the user stated a durable preference — saved automatically",
                content=text_value, memory_type=memory_type, scope=scope, scope_id=scope_id,
                subject=subject, confidence=max(confidence, 0.6), importance=0.6,
                provenance="memory_tool", evidence=evidence,
            )
        if durable and mode == "ask_before_saving":
            return MemoryDecision(
                outcome="suggest", action="save",
                reason="the model proposed a durable fact, but the user did not explicitly ask to remember it",
                content=text_value, memory_type=memory_type, scope=scope, scope_id=scope_id,
                subject=subject, confidence=confidence, importance=0.5,
                provenance="memory_tool", evidence=evidence,
            )
        return MemoryDecision(
            outcome="ignore", action="save",
            reason="model memory write is not authorized by the user turn",
            content="", provenance="memory_tool",
        )

    if provenance == "run_analysis":
        # Automatic lesson capture may only save under automatic_selective; under
        # ask_before_saving it stages a suggestion; otherwise it never persists.
        mode = str(settings.get("memory_mode") or "automatic_selective")
        if mode == "automatic_selective":
            return MemoryDecision(
                outcome="save", action="save",
                reason="automatic analysis captured a durable lesson",
                content=text_value, memory_type=memory_type, scope=scope, scope_id=scope_id,
                subject=subject, confidence=max(confidence, 0.6), importance=0.55,
                provenance="run_analysis", evidence=evidence,
            )
        if mode == "ask_before_saving":
            return MemoryDecision(
                outcome="suggest", action="save",
                reason="automatic analysis proposed a durable lesson — confirm to remember",
                content=text_value, memory_type=memory_type, scope=scope, scope_id=scope_id,
                subject=subject, confidence=confidence, importance=0.5,
                provenance="run_analysis", evidence=evidence,
            )
        return _history_only("automatic memory learning is off", content=text_value, provenance=provenance)

    if provenance == "skill_lesson":
        # A validated execution lesson from a skill run carries execution
        # provenance; it is evidence-bearing and may be stored as procedural
        # memory, but still never a financial fact and never auto-promoted.
        if not evidence:
            return MemoryDecision(
                outcome="suggest", action="save",
                reason="execution lesson without evidence — confirm to remember",
                content=text_value, memory_type="procedural", scope=scope, scope_id=scope_id,
                subject=subject, confidence=confidence, provenance=provenance,
            )
        return MemoryDecision(
            outcome="save", action="save", reason="validated execution lesson with evidence",
            content=text_value, memory_type="procedural", scope=scope, scope_id=scope_id,
            subject=subject, confidence=max(confidence, 0.6), importance=0.6,
            provenance=provenance, evidence=evidence,
        )

    # explicit_user / correction / forget should have arrived via decide_turn.
    return _ignore("proposal must be authorized through the deterministic turn gate", provenance=provenance)


__all__ = [
    "MemoryDecision",
    "OUTCOMES",
    "PROVENANCES",
    "authorize_proposal",
    "content_signature",
    "decide_turn",
    "looks_like_dump",
    "looks_like_financial_fact",
    "looks_like_override",
    "looks_like_secret",
]
