"""Centralized redaction — the ONE place secrets are stripped before telemetry.

Every exporter, logger and observer routes payloads through `Redactor`. The
engine is conservative: it redacts by KEY NAME (authorization, api_key, password,
cookie, …) wherever a mapping is scanned, and by VALUE PATTERN (bearer tokens,
JWTs, private-key blocks, common provider key shapes, connection-string
credentials) wherever a string is scanned. PII (email/phone/card) is redacted
only when the operator opts in (`ECLIPSE_REDACT_PII`).

`redact(value)` never raises and never returns the original secret by accident:
on any internal error it returns the fixed sentinel `[REDACTED]`.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

REDACTED = "[REDACTED]"
_MAX_DEPTH = 8

# Key names whose VALUE is always secret, matched case-insensitively as a
# substring but with a small allowlist so `token_count` is not redacted.
_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|apikey|secret|password|passwd|pwd|token|authorization|auth|"
    r"bearer|cookie|set-cookie|private[_-]?key|client[_-]?secret|access[_-]?key|"
    r"refresh[_-]?token|session[_-]?id|credential|dsn|connection[_-]?string|passphrase|"
    r"otp|pin|signature|signing[_-]?key|smtp[_-]?pass|db[_-]?pass)",
    re.IGNORECASE,
)
_SAFE_KEY_ALLOWLIST = {
    "token_count", "token_count_total", "input_tokens", "output_tokens",
    "cached_tokens", "reasoning_tokens", "total_tokens", "token_budget",
    "max_tokens", "tokens", "token_estimate", "idempotencykey",
}

# Value patterns that are secret in ANY string.
_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"), r"\1 " + REDACTED),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|pwd|token|authorization)\b\s*[:=]\s*[^\s,;\"'}]+"),
     lambda m: f"{m.group(1)}={REDACTED}"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), REDACTED),  # JWT
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), REDACTED),
    (re.compile(r"\b(sk|rk|pk|ghp|gho|ghu|ghs|glpat|xox[baprs])-[A-Za-z0-9_\-]{12,}"), REDACTED),  # provider keys
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:@\s]+:[^@\s]+@"),
     lambda m: f"{m.group(1)}://[user]:{REDACTED}@"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),  # AWS access key id
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), REDACTED),  # Google API key
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+"), REDACTED),  # Slack
)

# PII — only applied when redact_pii is enabled.
_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CARD]"),
)

_WRAPPER_KEYS = ("value", "text", "content", "message", "body", "detail", "summary", "data")


class Redactor:
    def __init__(self, *, enabled: bool = True, redact_pii: bool = False) -> None:
        self.enabled = enabled
        self.redact_pii = redact_pii

    # ── public API ──────────────────────────────────────────────────────────
    def redact(self, value: Any) -> Any:
        if not self.enabled:
            return value
        try:
            return self._walk(value, 0, key=None)
        except Exception:  # noqa: BLE001 - a redaction bug must fail closed
            return REDACTED

    def redact_text(self, text: Any) -> str:
        if not self.enabled:
            return str(text)
        return self._scrub_string(str(text))

    def redact_mapping(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return dict(data)
        return {k: self._walk(v, 1, key=str(k)) for k, v in data.items()}

    def is_secret_key(self, key: str) -> bool:
        if key.lower() in _SAFE_KEY_ALLOWLIST:
            return False
        return bool(_SECRET_KEY_PATTERN.search(key))

    # ── internals ───────────────────────────────────────────────────────────
    def _walk(self, value: Any, depth: int, key: str | None) -> Any:
        if depth > _MAX_DEPTH:
            return "[TRUNCATED]"
        if key is not None and self.is_secret_key(key):
            if value in (None, ""):
                return value
            return REDACTED
        if isinstance(value, str):
            return self._scrub_string(value)
        if isinstance(value, Mapping):
            return {str(k): self._walk(v, depth + 1, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            scrubbed = [self._walk(v, depth + 1, key) for v in value]
            return type(value)(scrubbed) if not isinstance(value, (set, tuple)) else list(scrubbed)
        return value

    def _scrub_string(self, text: str) -> str:
        result = text
        for pattern, repl in _VALUE_PATTERNS:
            try:
                result = pattern.sub(repl, result)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                result = REDACTED
                break
        if self.redact_pii:
            for pattern, repl in _PII_PATTERNS:
                result = pattern.sub(repl, result)
        return result


# A process-wide default used by exporters/log setup before a hub exists.
_DEFAULT = Redactor()


def set_default_redactor(redactor: Redactor) -> None:
    global _DEFAULT
    _DEFAULT = redactor


def get_default_redactor() -> Redactor:
    return _DEFAULT


def redact(value: Any) -> Any:
    return _DEFAULT.redact(value)


__all__ = ["Redactor", "REDACTED", "redact", "set_default_redactor", "get_default_redactor"]
