"""The deterministic rule provider — the honest zero-model path.

It answers ONLY questions that carry an explicit, closed `rule` against one fact
in the request state. This is not a model judgment and it never guesses: a
missing fact, a type mismatch, or an undeclared operation raises
`DecisionUnavailable`. Anything the rules cannot prove is left to a real
decision provider.

The point is not to imitate Jev. It is to give deterministic workflows (and the
test suite) a fully offline, reproducible decision path that is still exercised
through the SAME request/answer/policy/audit pipeline.
"""

from __future__ import annotations

from typing import Any

from ..contracts import (
    ChoiceAnswer,
    DecisionRequest,
    DecisionResponse,
    NoulAnswer,
    RuleSpec,
)
from .base import DecisionProvider, DecisionUnavailable, DecisionUnsupported

_MISSING = object()


def _lookup(state: Any, path: str) -> Any:
    """Resolve a dotted path into the state; `_MISSING` when absent."""
    current: Any = state
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _compare(fact: Any, rule: RuleSpec) -> bool:
    if rule.op == "exists":
        return fact is not _MISSING and fact is not None
    if fact is _MISSING:
        raise DecisionUnavailable(f"fact {rule.fact!r} is not present in the state")

    expected = rule.value
    if rule.op == "eq":
        return fact == expected
    if rule.op == "ne":
        return fact != expected
    if rule.op == "contains":
        try:
            return expected in fact
        except TypeError as exc:
            raise DecisionUnavailable(
                f"fact {rule.fact!r} does not support `contains`"
            ) from exc

    # Ordered comparisons are the only ones that could silently coerce, so they
    # are strictly numeric. A string "10" is NOT greater than 9 in this engine.
    if isinstance(fact, bool) or isinstance(expected, bool):
        raise DecisionUnavailable(f"fact {rule.fact!r} is not numeric")
    if not isinstance(fact, (int, float)) or not isinstance(expected, (int, float)):
        raise DecisionUnavailable(
            f"fact {rule.fact!r} and the rule value must both be numbers"
        )
    if rule.op == "gt":
        return fact > expected
    if rule.op == "gte":
        return fact >= expected
    if rule.op == "lt":
        return fact < expected
    if rule.op == "lte":
        return fact <= expected
    raise DecisionUnsupported(f"unknown rule operation {rule.op!r}")


class RuleProvider(DecisionProvider):
    """Answers `noul` (and equality `choice`) questions from declared rules."""

    name = "rules"
    local = True
    models = ("rules-v1",)

    async def ask(self, request: DecisionRequest) -> DecisionResponse:
        answers: dict[str, Any] = {}
        for question_id, question in request.questions.items():
            rule = getattr(question, "rule", None)
            if rule is None:
                raise DecisionUnsupported(
                    f"question {question_id!r} ({question.type}) has no declared rule"
                )
            fact = _lookup(request.state, rule.fact)

            if question.type == "noul":
                answers[question_id] = NoulAnswer(
                    noul=1.0 if _compare(fact, rule) else 0.0
                )
                continue

            if question.type == "choice":
                if rule.op != "eq":
                    raise DecisionUnsupported(
                        f"choice rule for {question_id!r} must use `eq`"
                    )
                chosen = str(fact) if fact is not _MISSING and fact is not None else ""
                if chosen not in question.criteria:
                    raise DecisionUnavailable(
                        f"fact {rule.fact!r} is not one of the declared options"
                    )
                answers[question_id] = ChoiceAnswer(
                    choice=chosen,
                    probabilities={
                        option: (1.0 if option == chosen else 0.0)
                        for option in question.criteria
                    },
                    confidence=1.0,
                )
                continue

            raise DecisionUnsupported(
                f"the rule provider cannot answer a {question.type} question"
            )

        return DecisionResponse(
            answers=answers,
            provider=self.name,
            model="rules-v1",
        )


__all__ = ["RuleProvider"]
