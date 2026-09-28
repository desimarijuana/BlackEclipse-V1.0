"""Advisory content-injection scanner for skill/project/bundle/draft prose.

Skills are permission-gated and their prose is *data, never a security boundary*
(see `permissions.py`). But procedural prose still reaches the model, so a
malicious or careless skill can try to manipulate it. This module adds an
**advisory** defense: it detects suspicious instruction patterns, reports the
exact reason and the matched text, and can request **quarantine**.

Non-negotiable design:
  * Findings are WARNINGS, never proof of safety. A clean scan is **not** a
    guarantee — the code-level permission/execution gate remains authoritative.
  * The scanner never changes authorization, enables a skill, or grants anything.
  * Warnings cannot be suppressed by the scanned content itself: the scanner runs
    on the raw content and its result is not read from the content.
  * Findings are bounded and include a redacted snippet only — never echoed
    verbatim into a prompt where they could act as instructions.

Categories: `override_instructions`, `reveal_secrets`, `bypass_approval`,
`self_enable`, `disable_safety`, `impersonate_system`, `ignore_policy`,
`exfiltration`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Severity ordering for quarantine decisions.
SEVERITY_QUARANTINE = "quarantine"
SEVERITY_WARN = "warn"

# Each rule: (category, severity, human reason, compiled pattern).
_RULES: tuple[tuple[str, str, str, "re.Pattern[str]"], ...] = (
    (
        "override_instructions",
        SEVERITY_QUARANTINE,
        "attempts to override system/developer instructions",
        re.compile(
            r"(?i)\b(ignore|disregard|forget|override|discard)\b[^.\n]{0,40}\b"
            r"(previous|prior|earlier|above|system|developer|all)\b[^.\n]{0,20}"
            r"\b(instructions?|prompts?|rules?|messages?)\b"
        ),
    ),
    (
        "reveal_secrets",
        SEVERITY_QUARANTINE,
        "attempts to reveal hidden prompts or secrets",
        re.compile(
            r"(?i)\b(reveal|print|show|output|repeat|expose|leak|dump)\b[^.\n]{0,40}\b"
            r"(system prompt|hidden prompt|secret|credential|api[_-]?key|token|password|"
            r"environment variable|env var|instructions?)\b"
        ),
    ),
    (
        "bypass_approval",
        SEVERITY_QUARANTINE,
        "attempts to bypass approval or review controls",
        re.compile(
            r"(?i)\b(bypass|skip|avoid|ignore|circumvent)\b[^.\n]{0,30}\b"
            r"(approval|review|authorization|authorisation|operator|permission|gate|"
            r"evaluation|promotion)\b"
        ),
    ),
    (
        "self_enable",
        SEVERITY_QUARANTINE,
        "attempts to enable itself or grant permissions",
        re.compile(
            r"(?i)\b(enable|activate|grant|approve|promote)\b[^.\n]{0,30}\b"
            r"(yourself|itself|this skill|my ?self|me|without approval|automatically)\b"
        ),
    ),
    (
        "disable_safety",
        SEVERITY_QUARANTINE,
        "attempts to disable safety or verification checks",
        re.compile(
            r"(?i)\b(disable|turn off|deactivate|remove|skip)\b[^.\n]{0,30}\b"
            r"(safety|verification|validation|guardrail|restriction|permission check|"
            r"sandbox|filter|security)\b"
        ),
    ),
    (
        "impersonate_system",
        SEVERITY_QUARANTINE,
        "impersonates a system/developer message",
        re.compile(
            r"(?im)^\s*(system|developer|assistant|tool)\s*(message)?\s*:"
        ),
    ),
    (
        "ignore_policy",
        SEVERITY_QUARANTINE,
        "instructs the model to ignore repository or system policy",
        re.compile(
            r"(?i)\b(ignore|disregard|forget)\b[^.\n]{0,30}\b"
            r"(repository|repo|project|company|organization|organisation|safety)\b"
            r"[^.\n]{0,20}\b(policy|policies|rules?|guidelines?|conventions?)\b"
        ),
    ),
    (
        "exfiltration",
        SEVERITY_QUARANTINE,
        "instructs sending data to an external destination",
        re.compile(
            r"(?i)\b(send|post|upload|exfiltrate|transmit|email|forward)\b[^.\n]{0,40}\b"
            r"(secret|credential|api[_-]?key|token|password|\.env|environment|"
            r"private key|ssh key|memory|database)\b"
        ),
    ),
)

# Suspicious but not necessarily malicious — warn only.
_WARN_RULES: tuple[tuple[str, str], ...] = (
    ("role_marker", r"(?im)^\s*(user|human)\s*:"),
    ("prompt_fence", r"```\s*(system|assistant|developer)\b"),
    ("html_hidden", r"(?i)<\s*(script|iframe|style|template)\b"),
    ("zero_width", "[\u200b\u200c\u200d\u2060\ufeff]"),
)

_MAX_SNIPPET = 120


@dataclass
class ScanFinding:
    category: str
    severity: str
    reason: str
    snippet: str
    location: str = "skill"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "reason": self.reason,
            "snippet": self.snippet,
            "location": self.location,
        }


@dataclass
class ScanResult:
    ok: bool
    findings: list[ScanFinding] = field(default_factory=list)

    @property
    def should_quarantine(self) -> bool:
        return any(f.severity == SEVERITY_QUARANTINE for f in self.findings)

    @property
    def categories(self) -> list[str]:
        seen: list[str] = []
        for finding in self.findings:
            if finding.category not in seen:
                seen.append(finding.category)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "shouldQuarantine": self.should_quarantine,
            "categories": self.categories,
            "findings": [f.to_dict() for f in self.findings],
            "note": (
                "Advisory only. A clean scan is NOT proof of safety; the "
                "permission and execution gates remain authoritative."
            ),
        }


def _snippet(text: str, start: int, end: int) -> str:
    """A bounded, single-line, whitespace-collapsed excerpt around a match."""
    lo = max(0, start - 20)
    hi = min(len(text), end + 20)
    raw = " ".join(text[lo:hi].split())
    return raw[:_MAX_SNIPPET]


def scan_content(text: Optional[str], *, location: str = "skill") -> ScanResult:
    """Scan one piece of prose. Returns bounded findings; never raises."""
    if not text:
        return ScanResult(ok=True)
    findings: list[ScanFinding] = []
    for category, severity, reason, pattern in _RULES:
        match = pattern.search(text)
        if match:
            findings.append(ScanFinding(
                category=category, severity=severity, reason=reason,
                snippet=_snippet(text, match.start(), match.end()), location=location,
            ))
    for category, pattern in _WARN_RULES:
        match = re.search(pattern, text)
        if match:
            findings.append(ScanFinding(
                category=category, severity=SEVERITY_WARN,
                reason=f"suspicious content shape: {category}",
                snippet=_snippet(text, match.start(), match.end()), location=location,
            ))
    return ScanResult(ok=not findings, findings=findings)


def scan_loaded_skill(loaded: Any) -> ScanResult:
    """Scan a `LoadedSkill`'s manifest description + instruction prose.

    Location is derived from the skill's provenance tier so the operator can see
    whether the finding is in a bundled, profile, project, or generated skill.
    """
    try:
        manifest = loaded.manifest
        location = getattr(loaded, "provenance", "skill") or "skill"
        blob = "\n".join([
            str(getattr(manifest, "name", "") or ""),
            str(getattr(manifest, "description", "") or ""),
        ])
        try:
            instructions = loaded.load_instructions()
        except Exception:  # noqa: BLE001 - a read failure yields no prose to scan
            instructions = ""
        return scan_content(blob + "\n" + instructions, location=location)
    except Exception:  # noqa: BLE001 - scanning must never break loading
        return ScanResult(ok=True)


__all__ = [
    "SEVERITY_QUARANTINE",
    "SEVERITY_WARN",
    "ScanFinding",
    "ScanResult",
    "scan_content",
    "scan_loaded_skill",
]
