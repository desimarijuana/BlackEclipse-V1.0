"""DecisionService — the ONE orchestrator for typed decisions.

It resolves a provider, asks the questions, applies the confidence policy, and
writes an immutable audit record. It never invents an answer: a provider failure,
a missing answer, or a type mismatch becomes an explicit `unavailable` result.

The schema is closed on purpose:

    request  → state + typed questions
    response → typed answers (+ probabilities/confidence where applicable)
    result   → answered | review | unavailable + policy verdicts + record id

Nothing here changes a portfolio, places a trade, or turns a model judgment into
a verified financial fact. A caller that needs authority still goes through the
Fiduciary Gate, the Security Floor, or a human approval.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..persistence import now_iso
from ..model_runtime.types import Usage
from .contracts import (
    DecisionRequest,
    DecisionResult,
    DecisionResponse,
    questions_hash,
    state_hash,
)
from .policy import DecisionPolicy, result_from, status_for
from .providers.base import (
    DecisionProtocolError,
    DecisionUnavailable,
)
from .providers.rules import RuleProvider
from .registry import DecisionRegistry
from .store import DecisionStore, record_id as _record_id

log = logging.getLogger("harness.decisions")


class DecisionService:
    def __init__(
        self,
        store: Optional[Any] = None,
        registry: Optional[DecisionRegistry] = None,
        policy: Optional[DecisionPolicy] = None,
    ) -> None:
        self.registry = registry or DecisionRegistry([RuleProvider()])
        self.policy = policy or DecisionPolicy()
        self.store = DecisionStore(store) if store is not None else None

    # ── The one entry point ─────────────────────────────────────────────────
    async def ask(
        self,
        request: DecisionRequest,
        *,
        provider: Optional[str] = None,
        policy: Optional[DecisionPolicy] = None,
        run_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> DecisionResult:
        effective = policy or self.policy
        q_hash = questions_hash(request.questions)
        s_hash = state_hash(request.state)
        started = time.perf_counter()

        selected, unavailable_reason = self.registry.resolve(provider)
        if selected is None:
            return self._finish(
                status="unavailable",
                response=None,
                questions=request,
                verdicts={},
                reason=unavailable_reason,
                run_id=run_id,
                owner_id=owner_id,
                conversation_id=conversation_id,
                tool=tool,
                latency_ms=_elapsed_ms(started),
                provider=provider or "",
            )

        try:
            response = await selected.ask(request)
            _validate_answer_set(request, response)
        except DecisionProtocolError as exc:
            return self._finish(
                status="unavailable",
                response=None,
                questions=request,
                verdicts={},
                reason=str(exc),
                run_id=run_id,
                owner_id=owner_id,
                conversation_id=conversation_id,
                tool=tool,
                latency_ms=_elapsed_ms(started),
                provider=selected.name,
            )
        except DecisionUnavailable as exc:
            log.info("decision provider %s unavailable: %s", selected.name, exc)
            return self._finish(
                status="unavailable",
                response=None,
                questions=request,
                verdicts={},
                reason=str(exc)[:300],
                run_id=run_id,
                owner_id=owner_id,
                conversation_id=conversation_id,
                tool=tool,
                latency_ms=_elapsed_ms(started),
                provider=selected.name,
            )
        except Exception as exc:  # noqa: BLE001 - a provider bug is not an answer
            log.warning("decision provider %s failed", selected.name, exc_info=True)
            return self._finish(
                status="unavailable",
                response=None,
                questions=request,
                verdicts={},
                reason=f"decision provider failed ({type(exc).__name__})",
                run_id=run_id,
                owner_id=owner_id,
                conversation_id=conversation_id,
                tool=tool,
                latency_ms=_elapsed_ms(started),
                provider=selected.name,
            )

        verdicts = effective.summarize(response.answers, request.questions)
        status = status_for(verdicts, request.questions)
        return self._finish(
            status=status,
            response=response,
            questions=request,
            verdicts=verdicts,
            reason=None,
            run_id=run_id,
            owner_id=owner_id,
            conversation_id=conversation_id,
            tool=tool,
            latency_ms=_elapsed_ms(started) or response.latency_ms,
            provider=response.provider or selected.name,
            question_hash=q_hash,
            state_hash_value=s_hash,
            policy_snapshot=effective.to_dict(),
        )

    # ── Audit ───────────────────────────────────────────────────────────────
    def _finish(
        self,
        *,
        status: str,
        response: Optional[DecisionResponse],
        questions: DecisionRequest,
        verdicts: dict[str, dict[str, Any]],
        reason: Optional[str],
        run_id: Optional[str],
        owner_id: Optional[str],
        conversation_id: Optional[str],
        tool: Optional[str],
        latency_ms: int,
        provider: str,
        question_hash: Optional[str] = None,
        state_hash_value: Optional[str] = None,
        policy_snapshot: Optional[dict[str, Any]] = None,
    ) -> DecisionResult:
        q_hash = question_hash or questions_hash(questions.questions)
        s_hash = state_hash_value or state_hash(questions.state)
        answers = response.answers if response is not None else {}
        usage = response.usage if response is not None else Usage()
        record = None
        if self.store is not None:
            did = _record_id(
                run_id=run_id,
                provider=provider,
                question_hash=q_hash,
                state_hash=s_hash,
                tool=tool,
            )
            record = self.store.write_record(
                {
                    "id": did,
                    "runId": run_id,
                    "ownerId": owner_id,
                    "conversationId": conversation_id,
                    "createdAt": now_iso(),
                    "provider": provider,
                    "model": response.model if response is not None else "",
                    "questionHash": q_hash,
                    "stateHash": s_hash,
                    "status": status,
                    "policy": policy_snapshot or {},
                    "answers": {
                        key: answer.model_dump(mode="json")
                        for key, answer in answers.items()
                    },
                    "usage": usage.to_dict() if usage is not None else {},
                    "latencyMs": latency_ms,
                    "tool": tool,
                    "reason": reason,
                }
            )

        return result_from(
            status=status,
            answers=answers,
            policy=verdicts,
            provider=provider,
            model=response.model if response is not None else "",
            usage=usage,
            question_hash=q_hash,
            record_id=(record or {}).get("id"),
            reason=reason,
            latency_ms=latency_ms,
        )

    # ── Read surfaces (tools) ───────────────────────────────────────────────
    def list_records(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.store.list_records(**kwargs) if self.store else []

    def scorecard(self, **kwargs: Any) -> dict[str, Any]:
        if self.store is None:
            return {
                "total": 0,
                "byStatus": {"answered": 0, "review": 0, "unavailable": 0},
                "byProvider": {},
                "evaluated": 0,
                "byOutcome": {},
                "accuracy": None,
            }
        return self.store.scorecard(**kwargs)

    def record_outcome(self, **kwargs: Any) -> dict[str, Any]:
        if self.store is None:
            raise RuntimeError("decision audit storage is not available")
        return self.store.record_outcome(**kwargs)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _validate_answer_set(request: DecisionRequest, response: DecisionResponse) -> None:
    """A partial or mistyped answer set is a protocol failure, never a guess."""
    if not isinstance(response, DecisionResponse):
        raise DecisionProtocolError("provider did not return a DecisionResponse")
    missing = sorted(set(request.questions) - set(response.answers))
    if missing:
        raise DecisionProtocolError(
            "provider returned no answer for: " + ", ".join(missing)
        )
    extra = sorted(set(response.answers) - set(request.questions))
    if extra:
        raise DecisionProtocolError(
            "provider returned answers for unknown questions: " + ", ".join(extra)
        )
    for question_id, answer in response.answers.items():
        question = request.questions[question_id]
        if answer.type != question.type:
            raise DecisionProtocolError(
                f"answer for {question_id!r} is a {answer.type} answer, "
                f"but the question is {question.type}"
            )


__all__ = ["DecisionService"]
