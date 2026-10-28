"""Scam / coercion signals.

Deterministic and explainable. This is deliberately conservative: a signal only
ever ADDS friction. The classifier never grants permission and never invents a
fact. When several high-severity markers appear together the intent is denied.

The signals are the well-documented shapes of authorized-push-payment fraud and
investment coercion: manufactured urgency, secrecy, impersonated authority,
guaranteed returns, remote-access requests, and irreversible payment rails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import CONFIRM, DENY, GuardrailVerdict, MoneyIntent


@dataclass(frozen=True)
class Marker:
    rule: str
    pattern: str
    reason: str
    severity: str  # "high" | "medium"


_MARKERS: tuple[Marker, ...] = (
    Marker("scam.secrecy", r"\b(don'?t|do not|never)\s+(tell|mention|inform|say)\b", "the request asks you to keep it secret", "high"),
    Marker("scam.secrecy", r"\bkeep (this|it) (between|private|secret)\b", "the request asks you to keep it secret", "high"),
    Marker("scam.urgency", r"\b(act now|right now|immediately|urgent|emergency|last chance|before it'?s too late)\b", "the request manufactures urgency", "high"),
    Marker("scam.authority", r"\b(irs|hmrc|tax office|police|government|social security|bank security|fraud department|security department)\b", "the request impersonates an authority", "high"),
    Marker("scam.support", r"\b(microsoft|apple|google)\s+(support|security)\b|\btech support\b", "the request impersonates technical support", "high"),
    Marker("scam.account-locked", r"\b(account|card|wallet)\s+(is\s+)?(locked|suspended|frozen|compromised)\b", "the request claims an account is compromised", "high"),
    Marker("scam.remote-access", r"\b(anydesk|teamviewer|remote access|screen shar(e|ing)|give me access)\b", "the request asks for remote access to your device", "high"),
    Marker("scam.guaranteed", r"\b(guaranteed|risk[-\s]?free)\s+(return|profit|income|gain|money)\b", "the request promises a guaranteed return", "high"),
    Marker("scam.double-money", r"\bdouble\s+your\s+(money|investment|capital)\b", "the request promises to double your money", "high"),
    Marker("scam.release-fee", r"\b(release|unlock|unfreeze)\s+(your\s+)?(funds|money|profits?|account)\b", "the request conditions your own funds on a payment", "high"),
    Marker("scam.processing-fee", r"\b(processing|clearance|release|transfer)\s+fee\b", "the request asks for an advance fee", "high"),
    Marker("scam.gift-card", r"\b(gift\s?card|itunes card|amazon card|steam card)\b", "the request asks for an irreversible gift-card payment", "high"),
    Marker("scam.wire-only", r"\b(wire transfer|western union|moneygram)\b", "the request asks for an irreversible money-transfer rail", "high"),
    Marker("scam.off-platform", r"\b(whatsapp|telegram|signal)\b|\boff (the )?(app|platform)\b", "the request moves the conversation off-platform", "medium"),
    Marker("scam.crypto-rail", r"\b(bitcoin|btc|usdt|tether|crypto wallet|coinbase wallet)\b", "the request uses an irreversible crypto rail", "medium"),
    Marker("scam.secrecy-medium", r"\bconfidential\b", "the request asks for confidentiality", "medium"),
    Marker("scam.authority-medium", r"\b(verify|confirm)\s+your\s+(identity|account|details)\b", "the request asks you to re-verify credentials", "medium"),
)

_COMPILED = tuple((m, re.compile(m.pattern, re.IGNORECASE)) for m in _MARKERS)


def scan(text: str) -> list[Marker]:
    blob = str(text or "")
    if not blob.strip():
        return []
    hits: list[Marker] = []
    seen: set[str] = set()
    for marker, pattern in _COMPILED:
        if marker.rule in seen:
            continue
        if pattern.search(blob):
            hits.append(marker)
            seen.add(marker.rule)
    return hits


def evaluate(intent: MoneyIntent) -> GuardrailVerdict:
    """Signal-only verdict. Counterparty novelty is added by the service."""
    text = " ".join(
        str(v) for k, v in (intent.args or {}).items()
        if isinstance(v, (str, int, float)) and k not in ("quantity", "price", "amount")
    )
    hits = scan(f"{intent.source_text} {text}")
    if not hits:
        return GuardrailVerdict(intent=intent)

    high = [h for h in hits if h.severity == "high"]
    medium = [h for h in hits if h.severity == "medium"]
    verdict = GuardrailVerdict(
        intent=intent,
        rules=[h.rule for h in hits],
        reasons=[h.reason for h in hits],
        risk="critical" if high else "high",
    )
    if len(high) >= 2:
        verdict.decision = DENY
        verdict.reasons.append(
            "Several independent scam signals appear together; Eclipse stopped instead of paying."
        )
        return verdict
    if high:
        verdict.decision = CONFIRM
        verdict.cooling_off_seconds = 900
        verdict.requires_typed_confirmation = True
        return verdict
    if medium:
        verdict.decision = CONFIRM
        verdict.cooling_off_seconds = 300
        verdict.requires_typed_confirmation = True
    return verdict


__all__ = ["Marker", "evaluate", "scan"]
