"""The answer seam: record what the answer claims, verify it, disclose failures (C4).

This runs AFTER the existing code/finance/research/advisory gates. It does not
replace them; it adds one cross-domain ledger and one conservative disclosure:

  * only CHECKABLE sentences are recorded (numbers, finance shapes, URLs,
    test/build claims, produced-file claims) — generic prose is left alone;
  * a sentence inherits the run's evidence handles (tool records, files,
    citations, artifacts, computations);
  * the verifier registry refines each claim; a specific rejection is
    `unsupported`, a missing handle is `unverified`;
  * UNSUPPORTED claims are disclosed only when the operator enables enforcement
    (`HARNESS_EVIDENCE_ENFORCE=1`); the ledger + outcome always record them.
    Unverified generic prose is recorded but never spammed into the answer.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .ledger import EvidenceLedger, claim_sentences, render_evidence_block
from .model import EvidenceHandle
from .verifiers import (
    VerificationContext,
    default_registry,
    is_checkable_sentence,
)

MAX_DISCLOSURE_ITEMS = 5


def enforcement_enabled() -> bool:
    """Whether an unsupported claim is disclosed in the answer text.

    DEFAULT OFF: the seam always records and verifies, but rewriting the answer
    is an operator opt-in until eval parity (`HARNESS_EVIDENCE_ENFORCE=1`). Plan
    runs still replan on a verifier rejection — that is the loop gate, not a
    text rewrite.
    """
    value = (os.environ.get("HARNESS_EVIDENCE_ENFORCE") or "").strip().lower()
    return value in ("1", "true", "yes", "on")


def _pool(ledger: EvidenceLedger, run_id: str) -> list[dict[str, Any]]:
    """Every distinct valid handle the run has already recorded."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for claim in ledger.claims(run_id):
        for handle in claim.handles:
            key = (handle.kind, handle.ref)
            if key in seen:
                continue
            if EvidenceHandle.from_dict(handle.to_dict()).valid:
                seen.add(key)
                out.append(handle.to_dict())
    return out


def _disclosure(verdicts: list[Any]) -> str:
    items = []
    for verdict in verdicts[:MAX_DISCLOSURE_ITEMS]:
        missing = verdict.missing[0] if verdict.missing else ""
        items.append(f"- {missing[:240]}" if missing else f"- {verdict.reason[:240]}")
    if not items:
        return ""
    return (
        "**Evidence check:** the following claim(s) could not be verified from "
        "this run's sources and should be treated as unverified:\n"
        + "\n".join(items)
    )


async def enforce_evidence_answer(
    output: str,
    store: Any,
    run_id: str,
    *,
    emitter: Any = None,
    enforce: Optional[bool] = None,
    checks: tuple[dict[str, Any], ...] = (),
) -> tuple[str, dict[str, Any]]:
    """Record checkable answer claims, verify them, disclose unsupported ones.

    Returns `(possibly_disclosed_output, blob)`. Never raises to the caller: a
    verification failure must not break the answer.
    """
    try:
        ledger = EvidenceLedger(store)
        pool = _pool(ledger, run_id)
        existing = {claim.text for claim in ledger.claims(run_id)}
        checkable = [
            sentence for sentence in claim_sentences(output)
            if is_checkable_sentence(sentence) and sentence not in existing
        ]
        if not pool and not checkable:
            return output, {"claims": 0, "supported": 0, "unsupported": 0,
                            "unverified": 0, "enforced": False}

        for sentence in checkable:
            ledger.record(run_id=run_id, text=sentence, handles=pool, status="unverified")

        # Finance-shaped sentences are detected by the verifier's own pattern;
        # no blanket "this run is finance" flag is needed here.
        context = VerificationContext(run_id=run_id, checks=tuple(checks))
        result = default_registry().verify_run(ledger, run_id, context)
        blob = result.to_dict()
        blob["claims"] = result.supported + result.unsupported + result.unverified
        blob["enforced"] = False

        enabled = enforcement_enabled() if enforce is None else bool(enforce)
        rejected = [v for v in result.verdicts if not v.ok and v.verifier != "evidence"]
        if enabled and rejected:
            note = _disclosure(rejected)
            if note:
                output = f"{output}\n\n{note}" if output.strip() else note
                blob["enforced"] = True
                blob["disclosure"] = note

        if emitter is not None:
            await emitter.emit("evidence.verified", {
                "supported": result.supported,
                "unsupported": result.unsupported,
                "unverified": result.unverified,
                "enforced": blob["enforced"],
            })
            for verdict in rejected:
                await emitter.emit("evidence.claim_rejected", {
                    "verifier": verdict.verifier,
                    "reason": verdict.reason,
                    "missing": list(verdict.missing),
                })
        return output, blob
    except Exception:  # noqa: BLE001 - the seam is additive, never fatal
        return output, {"claims": 0, "supported": 0, "unsupported": 0,
                        "unverified": 0, "enforced": False}


__all__ = ["MAX_DISCLOSURE_ITEMS", "enforce_evidence_answer", "enforcement_enabled"]
