"""Confidence and probability policy — the fail-closed layer.

A decision answer is a model judgment, not a fact. This module turns the answer's
own certainty into one of two outcomes:

  * `act`    — the answer clears every threshold; the caller may branch on it.
  * `review` — the answer is inside the abstain band; it is a hint for a human or
               a second check, never a decision.

There is deliberately no third "assume yes" state. A low-confidence answer is
never promoted by the policy; it only ever gets weaker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import Answer, DecisionResult, Question

ACT = "act"
REVIEW = "review"


@dataclass(frozen=True)
class DecisionPolicy:
    """Thresholds applied to every answer in a decision result.

    `min_confidence`  — the provider's own certainty must reach this.
    `min_probability` — for Choice, the selected option's probability; for Noul,
                        the answer must be at least this far from 0.5 on either
                        side (the abstain band is `1 - min_probability .. min_probability`).
    `require_confidence` — when True, an answer with no reported confidence is
                        treated as review instead of accepted. Default False, so
                        deterministic providers (which report no confidence) still
                        work.
    """

    min_confidence: float = 0.6
    min_probability: float = 0.6
    require_confidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "minConfidence": self.min_confidence,
            "minProbability": self.min_probability,
            "requireConfidence": self.require_confidence,
        }

    def assess(self, question: Question, answer: Answer) -> dict[str, Any]:
        if answer.type != question.type:
            return {"verdict": REVIEW, "reason": "answer type does not match the question"}

        if answer.type == "noul":
            confidence = answer.confidence
            if confidence is None and self.require_confidence:
                return {
                    "verdict": REVIEW,
                    "reason": "the provider reported no confidence",
                    "probability": float(answer.noul),
                }
            if confidence is not None and confidence < self.min_confidence:
                return {
                    "verdict": REVIEW,
                    "reason": "confidence is below threshold",
                    "probability": float(answer.noul),
                    "confidence": float(confidence),
                }
            probability = float(answer.noul)
            if probability >= self.min_probability or probability <= (
                1.0 - self.min_probability
            ):
                return {"verdict": ACT, "reason": None, "probability": probability}
            return {
                "verdict": REVIEW,
                "reason": "probability sits inside the abstain band",
                "probability": probability,
            }

        if answer.type == "choice":
            probability = answer.probabilities.get(answer.choice)
            if probability is not None and probability < self.min_probability:
                return {
                    "verdict": REVIEW,
                    "reason": "selected option's probability is below threshold",
                    "probability": float(probability),
                }
            confidence = answer.confidence
        else:  # score
            probability = None
            confidence = answer.confidence

        if confidence is None:
            if self.require_confidence:
                return {
                    "verdict": REVIEW,
                    "reason": "the provider reported no confidence",
                    "probability": probability,
                }
            return {"verdict": ACT, "reason": None, "probability": probability}
        if confidence < self.min_confidence:
            return {
                "verdict": REVIEW,
                "reason": "confidence is below threshold",
                "probability": probability,
                "confidence": float(confidence),
            }
        return {
            "verdict": ACT,
            "reason": None,
            "probability": probability,
            "confidence": float(confidence),
        }

    def summarize(self, answers: dict[str, Answer], questions: dict[str, Question]) -> dict[str, dict[str, Any]]:
        """Assess every answer. An answer with no question is a review, never act."""
        verdicts: dict[str, dict[str, Any]] = {}
        for question_id, answer in answers.items():
            question = questions.get(question_id)
            if question is None:
                verdicts[question_id] = {
                    "verdict": REVIEW,
                    "reason": "answer has no matching question",
                }
                continue
            verdicts[question_id] = self.assess(question, answer)
        return verdicts


def status_for(verdicts: dict[str, dict[str, Any]], questions: dict[str, Question]) -> str:
    """`answered` only when every question has an `act` verdict."""
    if not questions:
        return "unavailable"
    if any(question_id not in verdicts for question_id in questions):
        return "unavailable"
    if all(verdict.get("verdict") == ACT for verdict in verdicts.values()):
        return "answered"
    return "review"


def result_from(
    *,
    status: str,
    answers: dict[str, Answer],
    policy: dict[str, dict[str, Any]],
    **kwargs: Any,
) -> DecisionResult:
    return DecisionResult(status=status, answers=answers, policy=policy, **kwargs)


__all__ = ["ACT", "DecisionPolicy", "REVIEW", "result_from", "status_for"]
