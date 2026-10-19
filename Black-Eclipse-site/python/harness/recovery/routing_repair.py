"""Round 4 (W2) — routing repair: incident → typed root cause → minimal proposal.

The self-repair loop may PROPOSE a change, but it must never guess one. This
module turns a routing failure into one of four typed causes:

* ``VOCABULARY_GAP`` — the classifier missed an additive phrase; the minimal
  repair is a signal addition, with a regression fixture.
* ``CATALOG_GAP`` — the catalog genuinely lacks the capability; the correct
  route is the existing engineering escalation, not a classifier edit.
* ``CAPABILITY_ABSENT`` — no tool/integration can do it; the acquisition plan is
  the route.
* ``POLICY_GAP`` — policy refuses the route; a person decides.

Only ``VOCABULARY_GAP`` yields a code patch. The patch is emitted as a
``code.patch.PatchOp`` (a workspace-relative replace) and verified by activating
the exact rule in memory and running the fixture through the REAL classifier.
Landing stays with the operator-gated promotion path (W4); this module never
writes the tree.

The verification is expressed as the existing
``evaluation.improvement.ImprovementProposal`` contract, so the anti-regression
suite can accept or reject it with evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

_MODE_FILE = Path(__file__).resolve().parents[1] / "ui" / "mode.py"
#: The one exact line the classifier's additive verbs must be extended from.
_ADDITIVE_ANCHOR = '    "show", "display", "need", "want",'
#: Only phrases whose absence is a MEASURED additive miss. Deliberately short:
#: a broad synonym ("like", "love") would turn ordinary conversation into an
#: engineering escalation.
_KNOWN_MISSED_ADDITIVE = ("missing", "lacks")
_INCIDENT_PREFIXES = ("no registered component matches: ", "capability gap: ")


class RoutingCause(str, Enum):
    NO_ACTION = "no_action"
    VOCABULARY_GAP = "vocabulary_gap"
    CATALOG_GAP = "catalog_gap"
    CAPABILITY_ABSENT = "capability_absent"
    POLICY_GAP = "policy_gap"


@dataclass
class RoutingRepairProposal:
    id: str
    cause: RoutingCause
    #: "classifier_rule" | "engineering" | "acquisition" | "none"
    kind: str
    summary: str
    target_file: Optional[str] = None
    patch: Optional[dict[str, str]] = None
    added_phrases: tuple[str, ...] = ()
    fixture: dict[str, Any] = field(default_factory=dict)
    target_dimension: str = "misroute_rate"
    incident_id: Optional[str] = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cause": self.cause.value,
            "kind": self.kind,
            "summary": self.summary,
            "targetFile": self.target_file,
            "patch": dict(self.patch) if self.patch else None,
            "addedPhrases": list(self.added_phrases),
            "fixture": dict(self.fixture),
            "targetDimension": self.target_dimension,
            "incidentId": self.incident_id,
            "evidence": dict(self.evidence),
        }

    def as_patch_op(self) -> Any:
        """The proposal as a workspace-relative `code.patch.PatchOp` (or None)."""
        if not self.patch or not self.target_file:
            return None
        from ..code.patch import PatchOp  # noqa: PLC0415

        return PatchOp(
            op="replace",
            path=self.target_file,
            reason=self.summary,
            old=self.patch["old"],
            new=self.patch["new"],
        )

    def to_improvement(self) -> Any:
        """The proposal as the existing `ImprovementProposal` contract.

        `apply` activates the exact rule in memory (the same tuple the classifier
        reads), and `revert` restores it. No file is written here.
        """
        if self.kind != "classifier_rule":
            raise ValueError(f"kind {self.kind!r} has no verifiable improvement")
        from ..evaluation.improvement import ImprovementProposal  # noqa: PLC0415
        from ..ui import mode as mode_module  # noqa: PLC0415

        original = mode_module._ADDITIVE_VERBS  # noqa: SLF001 - the rule under test

        def apply() -> dict[str, Any]:
            mode_module._ADDITIVE_VERBS = (*original, *self.added_phrases)  # noqa: SLF001
            return {"rule": "additive_verbs", "added": list(self.added_phrases)}

        def revert() -> None:
            mode_module._ADDITIVE_VERBS = original  # noqa: SLF001

        return ImprovementProposal(
            id=self.id,
            description=self.summary,
            target_dimension=self.target_dimension,
            apply=apply,
            revert=revert,
        )


def _proposal_id(text: str, expected_mode: str, cause: RoutingCause) -> str:
    digest = hashlib.sha256(
        f"{text}|{expected_mode}|{cause.value}".encode("utf-8"),
    ).hexdigest()[:12]
    return f"routing-repair-{digest}"


def _missed_phrases(text: str) -> tuple[str, ...]:
    lowered = (text or "").lower()
    return tuple(
        phrase for phrase in _KNOWN_MISSED_ADDITIVE
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", lowered)
    )


def _anchor_line() -> Optional[str]:
    """The exact additive-verb line, only when it occurs exactly once."""
    try:
        text = _MODE_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    return _ADDITIVE_ANCHOR if text.count(_ADDITIVE_ANCHOR) == 1 else None


def diagnose(
    text: str,
    *,
    expected_mode: str = "engineer",
    expected_gap: bool = True,
    catalog: Any = None,
) -> tuple[RoutingCause, dict[str, Any]]:
    """The typed cause for a routing mismatch (never a guess)."""
    from ..ui.catalog import UiCatalog  # noqa: PLC0415
    from ..ui.mode import assess_capability, classify_request  # noqa: PLC0415

    catalog = catalog or UiCatalog()
    decision = classify_request(text, catalog=catalog)
    # The DIAGNOSTIC fit looks past additive phrasing: a request can name a
    # capability ("missing a world clock") that the classifier's additive rule
    # did not see. This is what separates a vocabulary miss from a catalog gap.
    fit = assess_capability(text, catalog=catalog, additive_only=False)
    evidence: dict[str, Any] = {
        "mode": decision.mode.value,
        "capabilityGap": decision.capability_gap,
        "expectedMode": expected_mode,
        "expectedGap": expected_gap,
        "witness": list(decision.matched_components),
        "fitReason": fit.reason,
    }
    if decision.mode.value == expected_mode and decision.capability_gap is expected_gap:
        return RoutingCause.NO_ACTION, evidence

    if fit.capability_gap and not decision.capability_gap:
        missed = _missed_phrases(text)
        if missed:
            evidence["missedPhrases"] = list(missed)
            return RoutingCause.VOCABULARY_GAP, evidence
        return RoutingCause.CATALOG_GAP, evidence

    evidence["note"] = "the catalog has a witness; the expected route is not a gap"
    return RoutingCause.NO_ACTION, evidence


def propose(
    text: str,
    *,
    expected_mode: str = "engineer",
    expected_gap: bool = True,
    incident_id: Optional[str] = None,
    catalog: Any = None,
) -> RoutingRepairProposal:
    """Build the minimal, typed proposal for one routing failure."""
    cause, evidence = diagnose(
        text, expected_mode=expected_mode, expected_gap=expected_gap, catalog=catalog,
    )
    fixture = {"text": text, "expectedMode": expected_mode, "expectedGap": expected_gap}
    base = {
        "id": _proposal_id(text, expected_mode, cause),
        "cause": cause,
        "fixture": fixture,
        "incident_id": incident_id,
        "evidence": evidence,
    }
    if cause is RoutingCause.NO_ACTION:
        return RoutingRepairProposal(
            kind="none",
            summary="the routing already matches the expected outcome",
            **base,
        )
    if cause is RoutingCause.VOCABULARY_GAP:
        missed = _missed_phrases(text)
        anchor = _anchor_line()
        if not anchor:
            return RoutingRepairProposal(
                kind="none",
                summary="no safe classifier anchor was found; a person must author the change",
                **base,
            )
        additions = ", ".join(f'"{phrase}"' for phrase in missed)
        new_line = f'{anchor[:-1]}, {additions},'
        return RoutingRepairProposal(
            kind="classifier_rule",
            summary=f"add the missed additive phrase(s) {', '.join(missed)} to the classifier",
            target_file="python/harness/ui/mode.py",
            patch={"old": anchor, "new": new_line},
            added_phrases=missed,
            **base,
        )
    if cause is RoutingCause.CATALOG_GAP:
        return RoutingRepairProposal(
            kind="engineering",
            summary=(
                "the catalog has no component for this capability; the engineering "
                "escalation is the correct route, not a classifier edit"
            ),
            **base,
        )
    if cause is RoutingCause.CAPABILITY_ABSENT:
        return RoutingRepairProposal(
            kind="acquisition",
            summary=(
                "the capability needs a tool or integration that is not available; "
                "run the acquisition plan (enable/install/build/alternative)"
            ),
            **base,
        )
    return RoutingRepairProposal(
        kind="none",
        summary="policy refuses the route; an operator decision is required",
        **base,
    )


def proposal_from_incident(incident: dict[str, Any], *, catalog: Any = None) -> RoutingRepairProposal:
    """Build a proposal from a durable incident (the `ui.capability_gap` path)."""
    message = str(incident.get("message") or "").strip()
    for prefix in _INCIDENT_PREFIXES:
        if message.startswith(prefix):
            message = message[len(prefix):].strip()
            break
    if not message:
        return RoutingRepairProposal(
            id="routing-repair-no-request",
            cause=RoutingCause.NO_ACTION,
            kind="none",
            summary="the incident carries no request text; collect a reproduction first",
            incident_id=incident.get("id"),
        )
    return propose(
        message,
        expected_mode="engineer",
        expected_gap=True,
        incident_id=incident.get("id"),
        catalog=catalog,
    )


def verify(proposal: RoutingRepairProposal, *, catalog: Any = None) -> bool:
    """Apply the RULE in memory and prove the fixture flips. Restores always."""
    if proposal.kind != "classifier_rule" or not proposal.added_phrases:
        return False
    from ..ui.catalog import UiCatalog  # noqa: PLC0415
    from ..ui import mode as mode_module  # noqa: PLC0415

    catalog = catalog or UiCatalog()
    original = mode_module._ADDITIVE_VERBS  # noqa: SLF001 - the rule under test
    try:
        mode_module._ADDITIVE_VERBS = (*original, *proposal.added_phrases)  # noqa: SLF001
        decision = mode_module.classify_request(proposal.fixture["text"], catalog=catalog)
        return (
            decision.mode.value == proposal.fixture["expectedMode"]
            and decision.capability_gap is proposal.fixture["expectedGap"]
        )
    finally:
        mode_module._ADDITIVE_VERBS = original  # noqa: SLF001


__all__ = [
    "RoutingCause",
    "RoutingRepairProposal",
    "diagnose",
    "proposal_from_incident",
    "propose",
    "verify",
]
