"""Security — sensitive-region detection and redaction.

Before any frame or OCR text leaves the machine (to a cloud vision model, a log
or a trajectory), the security layer can detect sensitive UI (password fields,
API keys, private keys, seed phrases, 2FA, bank/financial credentials) and either
flag the frame as sensitive (so vision routing refuses the cloud) or mask the
offending regions in the image.

Detection is deliberately conservative and content-labels based; it is ADVISORY
for routing and STRICT for redaction: if a region is flagged, masking is applied
before the image is persisted to an exportable trajectory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import Bounds

# Labels that mark a control/region as sensitive.
SENSITIVE_LABELS: tuple[str, ...] = (
    "password", "passwd", "pwd", "passphrase", "api key", "apikey", "api_key",
    "secret", "token", "access token", "private key", "seed phrase", "recovery phrase",
    "mnemonic", "one-time code", "one time code", "otp", "2fa", "two-factor",
    "verification code", "security code", "cvv", "cvc", "card number",
    "account number", "routing number", "iban", "ssn", "social security",
    "pin", "credential", "sign in", "login", "tax id",
)

# Text patterns that mark a region as sensitive even without a label.
SENSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",   # a card number
    r"\b[A-Z0-9]{16,}\b",                          # an API-key-shaped token
    r"\b\d{3}-\d{2}-\d{4}\b",                      # SSN
    r"\bsk-[A-Za-z0-9]{16,}\b",                    # secret key
)

_SENSITIVE_RE = re.compile("|".join(SENSITIVE_PATTERNS))


def is_sensitive_label(text: str) -> bool:
    lowered = (text or "").lower()
    return any(label in lowered for label in SENSITIVE_LABELS)


def looks_sensitive(text: str) -> bool:
    """Whether free text contains something that looks like a secret."""
    return bool(_SENSITIVE_RE.search(text or ""))


@dataclass
class SensitiveRegion:
    label: str
    bounds: Optional[Bounds] = None
    kind: str = "field"

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "bounds": self.bounds.to_dict() if self.bounds else None, "kind": self.kind}


@dataclass
class SecurityReport:
    sensitive: bool = False
    regions: list[SensitiveRegion] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensitive": self.sensitive,
            "regions": [r.to_dict() for r in self.regions],
            "reasons": self.reasons,
        }


class SecurityLayer:
    def __init__(self, *, redaction_enabled: bool = True) -> None:
        self.redaction_enabled = redaction_enabled

    def scan_snapshot(self, elements: list[dict], *, text: str = "") -> SecurityReport:
        """Flag sensitive regions from snapshot elements + rendered text."""
        regions: list[SensitiveRegion] = []
        reasons: list[str] = []
        for element in elements:
            label = str(element.get("name") or "") + " " + str(element.get("role") or "")
            if is_sensitive_label(label):
                regions.append(SensitiveRegion(
                    label=str(element.get("name") or element.get("role") or "sensitive"),
                    bounds=Bounds.from_any(element.get("bounds")), kind="field",
                ))
                reasons.append(f"control labelled {element.get('name')!r}")
        if text and looks_sensitive(text):
            reasons.append("text matches a secret pattern")
        sensitive = bool(regions) or bool(reasons)
        return SecurityReport(sensitive=sensitive, regions=regions, reasons=reasons)

    def mask_image(self, image: Any, regions: list[SensitiveRegion]) -> Any:
        """Black out sensitive regions in a PIL image (best-effort)."""
        if not self.redaction_enabled or image is None or not regions:
            return image
        try:
            from PIL import ImageDraw  # noqa: PLC0415

            masked = image.copy()
            draw = ImageDraw.Draw(masked)
            for region in regions:
                if region.bounds is None:
                    continue
                draw.rectangle(region.bounds.to_list(), fill=(0, 0, 0))
            return masked
        except Exception:  # noqa: BLE001
            return image

    def redact_text(self, text: str) -> str:
        if not self.redaction_enabled:
            return text
        return _SENSITIVE_RE.sub("«redacted»", text or "")


__all__ = [
    "SENSITIVE_LABELS",
    "SENSITIVE_PATTERNS",
    "SecurityLayer",
    "SecurityReport",
    "SensitiveRegion",
    "is_sensitive_label",
    "looks_sensitive",
]
