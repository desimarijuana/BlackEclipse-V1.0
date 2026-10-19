"""Root-cause diagnosis — structured, evidence-ranked hypotheses.

The failure layer classifies and signs a failure; this module answers *why*. It
is deterministic-first (spec §7.1): a bounded catalog of plausible causes per
`FailureKind`, ranked by the evidence actually collected — never a model
inventing an environmental fact.

A `Diagnosis` names its hypotheses, the evidence that supports and contradicts
each, the smallest safe test that would distinguish them, the selected cause when
the evidence is decisive, and (crucially) what is still MISSING. When the
evidence cannot separate the hypotheses the selected cause stays `None` and the
diagnosis says so, rather than presenting a guess as fact.

External facts are supplied by `Probe`s (dependency state, git diff, provider
health, …). The engine runs only the probes whose `applies(kind)` is true; a
probe raising is recorded as missing information, never allowed to abort the
diagnosis. Callers may also pass already-collected evidence keyed by probe name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .taxonomy import FailureKind, NormalizedFailure


@dataclass(frozen=True)
class Hypothesis:
    cause: str
    confidence: float
    supporting: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()
    test: str = ""
    repair_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause": self.cause,
            "confidence": round(self.confidence, 3),
            "supporting": list(self.supporting),
            "contradicting": list(self.contradicting),
            "test": self.test,
            "repairHint": self.repair_hint,
        }


@dataclass
class Diagnosis:
    kind: FailureKind
    hypotheses: list[Hypothesis] = field(default_factory=list)
    selected: Optional[str] = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    missing_information: list[str] = field(default_factory=list)

    @property
    def decisive(self) -> bool:
        return self.selected is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "selected": self.selected,
            "confidence": round(self.confidence, 3),
            "decisive": self.decisive,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "evidence": dict(self.evidence),
            "missingInformation": list(self.missing_information),
        }


# A bounded catalog: for each failure kind, the plausible causes with the evidence
# key that would confirm each. `evidence` maps a key to a truthy/falsey observed
# fact. Confidence starts at a prior and is raised when confirming evidence is
# present, lowered when contradicting evidence is present.
@dataclass(frozen=True)
class _Cause:
    cause: str
    kind: FailureKind
    confirms: str = ""
    refutes: str = ""
    test: str = ""
    repair_hint: str = ""


_CATALOG: tuple[_Cause, ...] = (
    _Cause("the upstream service is unreachable or refused the connection", FailureKind.NETWORK,
           confirms="network_unreachable", test="probe the endpoint/DNS from the runtime host",
           repair_hint="retry with backoff, then substitute a reachable endpoint"),
    _Cause("the operation exceeded its time budget", FailureKind.TIMEOUT,
           confirms="exceeded_timeout", test="re-run with a larger timeout and record the elapsed time",
           repair_hint="retry with backoff or a larger timeout; reduce the workload"),
    _Cause("a credential or authorization is missing/insufficient", FailureKind.AUTHENTICATION,
           confirms="credential_missing", test="inspect the configured credential presence (never its value)",
           repair_hint="request authorized consent; do not retry or substitute"),
    _Cause("a credential or authorization is missing/insufficient", FailureKind.AUTHORIZATION,
           confirms="permission_denied", test="evaluate the request against the security gateway",
           repair_hint="request authorized consent; use a permitted alternative"),
    _Cause("a required package or tool is not installed or is the wrong version", FailureKind.DEPENDENCY,
           confirms="dependency_missing", test="query the package manager for the package + version",
           repair_hint="install/align the dependency (approval-gated) or use an alternative"),
    _Cause("the source does not parse/compile (syntax)", FailureKind.SYNTAX,
           confirms="parse_error", test="run the compiler/parser on the exact file",
           repair_hint="repair the input at the reported location"),
    _Cause("a required assertion/check failed", FailureKind.ASSERTION,
           confirms="check_failed", test="run the failing test and capture its assertion",
           repair_hint="correct the code/input the assertion points at"),
    _Cause("the request did not match the API contract", FailureKind.INVALID_REQUEST,
           confirms="schema_mismatch", test="validate the request against the API schema",
           repair_hint="repair the input to match the contract"),
    _Cause("the page/element could not be resolved", FailureKind.BROWSER,
           confirms="element_missing", test="take a fresh accessibility snapshot",
           repair_hint="re-observe and retry with a fresh locator"),
    _Cause("the provider is rate limiting or degraded", FailureKind.RATE_LIMIT,
           confirms="rate_limited", test="read the Retry-After / health of the provider",
           repair_hint="honor the server-directed delay, then retry; or substitute provider"),
    _Cause("the provider is down or overloaded", FailureKind.PROVIDER_OUTAGE,
           confirms="provider_unhealthy", test="probe provider health and the circuit breaker",
           repair_hint="substitute a capability-compatible provider"),
    _Cause("the data is missing, stale or self-contradictory", FailureKind.DATA_QUALITY,
           confirms="data_stale", test="check source freshness and cross-source agreement",
           repair_hint="use a fresher source or collect more evidence"),
    _Cause("the plan/decomposition is invalid for the objective", FailureKind.PLANNING,
           confirms="plan_invalid", test="re-derive acceptance criteria from the objective",
           repair_hint="replan against the original objective"),
    _Cause("the current strategy is repeating without progress", FailureKind.NO_PROGRESS,
           confirms="no_progress", test="compare the last N step outcomes for change",
           repair_hint="change strategy or stop and report"),
    # Round 4: the capability-routing causes. The evidence keys are supplied by
    # the incident payload (a UI gap) or by the routing repair proposer.
    _Cause("the component catalog has no implementation for the requested capability", FailureKind.CAPABILITY,
           confirms="capability_gap", test="run the capability-fit check against the component catalog",
           repair_hint="escalate to engineering and register the component"),
    _Cause("the request vocabulary does not match any capability the classifier knows", FailureKind.CAPABILITY,
           confirms="vocabulary_gap", test="classify the request and inspect its content tokens",
           repair_hint="add the missing additive/engineer signal and a regression fixture"),
    _Cause("the required capability needs a tool or integration that is not available", FailureKind.CAPABILITY,
           confirms="capability_absent", test="search the capability index for an available equivalent",
           repair_hint="run the acquisition plan (enable/install/build/alternative)"),
    _Cause("policy refuses the route to the requested capability", FailureKind.CAPABILITY,
           confirms="policy_denied", test="authorize the action against the policy gateway",
           repair_hint="request operator authorization or use a permitted route"),
)


# A probe gathers one deterministic environmental fact. It returns whether the
# fact is *present* (True), absent (False), or unknown (None). It must never
# raise; a raising probe becomes missing information.
Probe = Callable[[NormalizedFailure], Optional[bool]]


@dataclass(frozen=True)
class _ProbeSpec:
    name: str
    applies: Callable[[FailureKind], bool]
    run: Probe


class DiagnosisEngine:
    """Produces an evidence-ranked `Diagnosis` for a normalized failure."""

    def __init__(self, probes: Optional[list[_ProbeSpec]] = None) -> None:
        self._probes: list[_ProbeSpec] = list(probes or [])

    def register(self, name: str, applies: Callable[[FailureKind], bool], run: Probe) -> None:
        self._probes.append(_ProbeSpec(name, applies, run))

    def diagnose(
        self,
        failure: NormalizedFailure,
        *,
        evidence: Optional[dict[str, Any]] = None,
    ) -> Diagnosis:
        observed: dict[str, Any] = dict(evidence or {})
        missing: list[str] = []

        for spec in self._probes:
            if not spec.applies(failure.kind) or spec.name in observed:
                continue
            try:
                observed[spec.name] = spec.run(failure)
            except Exception:  # noqa: BLE001 - a probe failure is missing info
                observed[spec.name] = None
                missing.append(f"probe '{spec.name}' could not run")

        causes = [c for c in _CATALOG if c.kind == failure.kind]
        hypotheses: list[Hypothesis] = []
        for cause in causes:
            confidence = 0.5
            supporting: list[str] = []
            contradicting: list[str] = []
            if cause.confirms:
                value = observed.get(cause.confirms)
                if value is True:
                    confidence = 0.85
                    supporting.append(cause.confirms)
                elif value is False:
                    confidence = 0.15
                    contradicting.append(cause.confirms)
                else:
                    missing.append(cause.confirms)
            if cause.refutes:
                value = observed.get(cause.refutes)
                if value is True:
                    confidence = min(confidence, 0.1)
                    contradicting.append(cause.refutes)
            hypotheses.append(Hypothesis(
                cause=cause.cause, confidence=confidence,
                supporting=tuple(supporting), contradicting=tuple(contradicting),
                test=cause.test, repair_hint=cause.repair_hint,
            ))

        if not hypotheses:
            hypotheses.append(Hypothesis(
                cause="an unrecognized failure with no catalogued cause",
                confidence=0.2, test="collect a bounded reproduction and its logs",
                repair_hint="gather more evidence before acting",
            ))

        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        selected: Optional[str] = None
        confidence = hypotheses[0].confidence
        margin = confidence - (hypotheses[1].confidence if len(hypotheses) > 1 else 0.0)
        # A successful reproduction proves the failure is deterministic and real, so
        # the leading cause may be selected on a slightly weaker margin.
        reproduced = observed.get("reproduced") is True
        if confidence >= 0.8 and (len(hypotheses) == 1 or margin >= 0.3):
            selected = hypotheses[0].cause
        elif reproduced and confidence >= 0.5 and (len(hypotheses) == 1 or margin >= 0.2):
            selected = hypotheses[0].cause
        else:
            missing.append("evidence that distinguishes the leading hypotheses")

        return Diagnosis(
            kind=failure.kind, hypotheses=hypotheses, selected=selected,
            confidence=confidence, evidence=observed,
            missing_information=list(dict.fromkeys(missing)),
        )


__all__ = ["Diagnosis", "DiagnosisEngine", "Hypothesis", "Probe"]
