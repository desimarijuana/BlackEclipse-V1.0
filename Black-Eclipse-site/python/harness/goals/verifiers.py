"""The verifier registry: typed checks over evidence, not prose trust (C4).

A verifier answers one question: *does the evidence this claim carries actually
support this class of claim?* It never invents a handle and never rewrites the
answer; it returns a `Verdict` the answer seam or replan can act on.

The built-ins are deliberately deterministic and conservative:

  * `finance_number`  - a finance-shaped number with no computation/report/
                        citation handle is UNSUPPORTED (fail closed).
  * `citation`        - a URL in the claim needs a citation handle.
  * `code_check`      - a test/build/pass claim needs a passing check record.
  * `evidence`        - the fallback: no valid handle => unverified.

Adapters call the existing domain modules (code ledger, research gate, task
verification) rather than duplicating their rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Protocol

from ..goals.ledger import EvidenceLedger, digest_text, has_number
from ..goals.model import Claim, Verdict


_FINANCE_SHAPE = re.compile(
    r"(\$|%|\bP/?E\b|\bEPS\b|\bROI\b|\bROE\b|\bROA\b|\bWACC\b|\bDCF\b|"
    r"\bdrawdown\b|\bvolatility\b|\bbeta\b|\breturn\b|\bprice\b|\bmarket cap\b|"
    r"\bearnings\b|\brevenue\b|\bmargin\b|\bdebt\b|\bcash flow\b)",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_CODE_SHAPE = re.compile(
    r"\b(test|tests|pytest|build|compile|lint|typecheck|passed|failing|green)\b",
    re.IGNORECASE,
)
_ARTIFACT_SHAPE = re.compile(
    r"\.(csv|xlsx?|pdf|md|json|png|svg|html|py|ts|tsx)\b", re.IGNORECASE,
)

# Handles strong enough to support a finance number. A bare `run` handle is not:
# every tool result carries one, so it would make every number "supported".
_FINANCE_HANDLES = frozenset({"computation", "file", "citation", "record", "artifact", "tool_output"})
_CITATION_HANDLES = frozenset({"citation"})


@dataclass
class VerificationContext:
    """What the verifier may consult besides the claim's own handles."""

    run_id: str
    step_id: Optional[str] = None
    agent_id: str = ""
    finance_domain: bool = False
    checks: tuple[dict[str, Any], ...] = ()
    result: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[dict[str, Any], ...] = ()

    @property
    def passed_checks(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if c.get("status") in ("passed", "ok", "succeeded")]


class ClaimVerifier(Protocol):
    name: str

    def applies(self, claim: Claim, context: VerificationContext) -> bool: ...

    def verify(self, claim: Claim, context: VerificationContext) -> Verdict: ...


class FinanceNumberVerifier:
    name = "finance_number"

    def applies(self, claim: Claim, context: VerificationContext) -> bool:
        if not context.finance_domain and not _FINANCE_SHAPE.search(claim.text):
            return False
        return has_number(claim.text) and bool(_FINANCE_SHAPE.search(claim.text))

    def verify(self, claim: Claim, context: VerificationContext) -> Verdict:
        strong = [h for h in claim.handles if h.kind in _FINANCE_HANDLES]
        if strong:
            return Verdict(verifier=self.name, ok=True)
        return Verdict(
            verifier=self.name, ok=False,
            reason="a finance number has no computation, report, citation or record handle",
            missing=(claim.text[:160],),
        )


class CitationVerifier:
    name = "citation"

    def applies(self, claim: Claim, context: VerificationContext) -> bool:
        return bool(_URL.search(claim.text))

    def verify(self, claim: Claim, context: VerificationContext) -> Verdict:
        has_citation = any(h.kind in _CITATION_HANDLES for h in claim.handles)
        if has_citation:
            return Verdict(verifier=self.name, ok=True)
        return Verdict(
            verifier=self.name, ok=False,
            reason="a URL claim has no citation/record handle",
            missing=(claim.text[:160],),
        )


class CodeCheckVerifier:
    name = "code_check"

    def applies(self, claim: Claim, context: VerificationContext) -> bool:
        return bool(_CODE_SHAPE.search(claim.text))

    def verify(self, claim: Claim, context: VerificationContext) -> Verdict:
        has_check = any(
            h.kind in ("record", "file") for h in claim.handles
        ) or bool(context.passed_checks)
        if has_check:
            return Verdict(verifier=self.name, ok=True)
        return Verdict(
            verifier=self.name, ok=False,
            reason="a test/build claim has no passing check record",
            missing=(claim.text[:160],),
        )


class ArtifactVerifier:
    name = "artifact"

    def applies(self, claim: Claim, context: VerificationContext) -> bool:
        return bool(_ARTIFACT_SHAPE.search(claim.text))

    def verify(self, claim: Claim, context: VerificationContext) -> Verdict:
        if any(h.kind in ("artifact", "file") for h in claim.handles):
            return Verdict(verifier=self.name, ok=True)
        return Verdict(
            verifier=self.name, ok=False,
            reason="a produced-file claim has no artifact/file handle",
            missing=(claim.text[:160],),
        )


class EvidenceVerifier:
    name = "evidence"

    def applies(self, claim: Claim, context: VerificationContext) -> bool:
        return True

    def verify(self, claim: Claim, context: VerificationContext) -> Verdict:
        if claim.handles:
            return Verdict(verifier=self.name, ok=True)
        return Verdict(
            verifier=self.name, ok=False, reason="no handle",
            missing=(claim.text[:160],),
        )


@dataclass
class RunVerification:
    ok: bool
    verdicts: list[Verdict]
    supported: int = 0
    unsupported: int = 0
    unverified: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "supported": self.supported,
            "unsupported": self.unsupported,
            "unverified": self.unverified,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


class VerifierRegistry:
    """Ordered, deterministic verifier selection (most specific first)."""

    def __init__(self, verifiers: Optional[Iterable[ClaimVerifier]] = None) -> None:
        self._verifiers = list(verifiers or [])
        self._fallback = EvidenceVerifier()

    def register(self, verifier: ClaimVerifier) -> None:
        self._verifiers.append(verifier)

    def pick(self, claim: Claim, context: VerificationContext) -> ClaimVerifier:
        for verifier in self._verifiers:
            if verifier.applies(claim, context):
                return verifier
        return self._fallback

    def verify_claim(self, claim: Claim, context: VerificationContext) -> Verdict:
        return self.pick(claim, context).verify(claim, context)

    def verify_run(
        self, ledger: EvidenceLedger, run_id: str, context: VerificationContext,
    ) -> RunVerification:
        claims = [c for c in ledger.claims(run_id) if c.status != "superseded"]
        verdicts: list[Verdict] = []
        supported = unsupported = unverified = 0
        for claim in claims:
            verdict = self.verify_claim(claim, context)
            if not verdict.ok:
                # A rejected claim is UNSUPPORTED when a specific verifier
                # rejected it; the generic missing-handle case is UNVERIFIED.
                status = "unverified" if verdict.verifier == "evidence" else "unsupported"
            else:
                status = "supported"
            ledger.store.set_claim_status(claim.id, status, verdict.verifier)
            if status == "supported":
                supported += 1
            elif status == "unsupported":
                unsupported += 1
            else:
                unverified += 1
            verdicts.append(verdict)
        return RunVerification(
            ok=unsupported == 0 and unverified == 0,
            verdicts=verdicts, supported=supported,
            unsupported=unsupported, unverified=unverified,
        )


def checks_from_ledger(ledger: Any) -> tuple[dict[str, Any], ...]:
    """Adapt the code verification ledger's records into verifier checks."""
    if ledger is None:
        return ()
    try:
        records = ledger.records()
    except Exception:  # noqa: BLE001 - a missing ledger is no checks
        return ()
    out = []
    for record in records[:24]:
        exit_code = getattr(record, "exit_code", None)
        out.append({
            "id": str(getattr(record, "command_execution_id", "") or ""),
            "kind": str(getattr(record, "command_class", "") or ""),
            "status": "passed" if exit_code == 0 else "failed",
        })
    return tuple(out)


def is_checkable_sentence(text: str) -> bool:
    """True when a sentence asserts something a verifier can actually check.

    Generic prose is deliberately excluded: labelling every sentence would be
    noise, not evidence. Numbers, finance shapes, URLs, code/test claims and
    produced-file claims are the classes where a missing handle matters.
    """
    value = str(text or "")
    return bool(
        has_number(value)
        or _FINANCE_SHAPE.search(value)
        or _URL.search(value)
        or _CODE_SHAPE.search(value)
        or _ARTIFACT_SHAPE.search(value)
    )


def default_registry() -> VerifierRegistry:
    """The production order: specific domain checks before the generic fallback."""
    return VerifierRegistry([
        FinanceNumberVerifier(),
        CitationVerifier(),
        CodeCheckVerifier(),
        ArtifactVerifier(),
    ])


__all__ = [
    "ArtifactVerifier",
    "CitationVerifier",
    "ClaimVerifier",
    "CodeCheckVerifier",
    "EvidenceVerifier",
    "FinanceNumberVerifier",
    "RunVerification",
    "VerificationContext",
    "VerifierRegistry",
    "checks_from_ledger",
    "default_registry",
    "is_checkable_sentence",
]
