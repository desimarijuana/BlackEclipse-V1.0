"""The plan runtime: bind one run to a goal step and record its evidence (C4).

This is deliberately opt-in through the run's context:

    input.context.c4Plan = {
        "objective": "...",
        "acceptance": ["..."],
        "steps": [{"title": "...", "objective": "...", "acceptance": ["..."]}],
    }

or `{"planId": "plan_..."}` to resume an existing plan. With no such context the
runtime returns None and the run behaves exactly as before.

The task runtime still owns execution; this object owns the GOAL view, the
current-step prompt block, and the evidence each tool result contributes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .ledger import EvidenceLedger, handles_from_tool_result
from .model import Goal, Plan, PlanStep
from .store import GoalStore
from .verifiers import (
    VerificationContext,
    default_registry,
    is_checkable_sentence,
)
from .ledger import claim_sentences


PLAN_CONTEXT_KEY = "c4Plan"
MAX_PROMPT_BLOCK = 4_000


def _context(request: Any) -> dict[str, Any]:
    value = getattr(getattr(request, "input", None), "context", None)
    return value if isinstance(value, dict) else {}


@dataclass
class PlanRuntime:
    goal: Goal
    plan: Plan
    ledger: EvidenceLedger
    store: GoalStore

    @property
    def current_step(self) -> Optional[PlanStep]:
        return self.plan.current_step

    def prompt_block(self) -> str:
        step = self.current_step
        if step is None:
            return ""
        total = len(self.plan.steps)
        lines = [
            "<goal-plan>",
            f"Goal: {self.goal.objective[:600]}",
        ]
        if self.goal.acceptance:
            lines.append("Goal acceptance:")
            lines.extend(f"- {item[:240]}" for item in self.goal.acceptance[:6])
        lines.append(f"Current step {step.index + 1}/{total}: {step.title[:200]}")
        if step.objective:
            lines.append(f"Step objective: {step.objective[:800]}")
        if step.acceptance:
            lines.append("Step acceptance:")
            lines.extend(f"- {item[:240]}" for item in step.acceptance[:6])
        lines.append(
            "Do this step now. Every factual or numeric claim in the final answer "
            "must be backed by a tool result, computation or citation from this run; "
            "if it is not, say it is unverified."
        )
        lines.append("</goal-plan>")
        block = "\n".join(lines)
        return block[:MAX_PROMPT_BLOCK]

    def record_tool_result(self, result: Any, run_id: str) -> None:
        """Record the handles a tool result contributes to the current step."""
        step = self.current_step
        if step is None:
            return
        handles = handles_from_tool_result(result, run_id)
        if not handles:
            return
        text = str(getattr(result, "text", "") or "")[:300]
        name = str(getattr(result, "name", "") or "tool")
        self.ledger.record(
            run_id=run_id,
            text=f"{name}: {text}" if text else f"{name} result",
            handles=handles,
            status="supported" if getattr(result, "ok", False) else "unverified",
            verifier="tool_result",
            step_id=step.id,
        )

    def record_answer_claims(self, run_id: str, text: str) -> None:
        """Record the checkable sentences of a draft answer against this step."""
        step = self.current_step
        if step is None:
            return
        existing = {claim.text for claim in self.ledger.claims(run_id)}
        seen: set[tuple[str, str]] = set()
        pool: list[dict[str, Any]] = []
        for claim in self.ledger.claims(run_id):
            for item in claim.handles:
                key = (item.kind, item.ref)
                if key in seen:
                    continue
                seen.add(key)
                pool.append(item.to_dict())
        for sentence in claim_sentences(text):
            if sentence in existing or not is_checkable_sentence(sentence):
                continue
            self.ledger.record(
                run_id=run_id, text=sentence, handles=pool,
                status="unverified", step_id=step.id,
            )

    def verify_current_step(self, run_id: str, checks: tuple[dict[str, Any], ...] = ()):
        """Run the verifier registry over this run's claims."""
        return default_registry().verify_run(
            self.ledger, run_id,
            VerificationContext(run_id=run_id, checks=tuple(checks)),
        )

    def finish_answer(
        self, run_id: str, text: str, *, replan_limit: int = 2,
        checks: tuple[dict[str, Any], ...] = (),
    ) -> Optional[dict[str, Any]]:
        """Record + verify the draft answer; return a replan trigger or None.

        A specific verifier rejection with replan budget left returns a typed
        trigger; otherwise the step is settled (verified only with evidence).
        """
        self.record_answer_claims(run_id, text)
        verification = self.verify_current_step(run_id, checks=checks)
        trigger = None
        if not verification.ok and self.can_replan(replan_limit):
            trigger = {
                "reason": "evidence",
                "unsupported": verification.unsupported,
                "unverified": verification.unverified,
            }
            self.settle(run_id, ok=False)
        else:
            self.settle(run_id, ok=verification.ok)
        return trigger

    def checkpoint_fields(self, step_id: Optional[str] = None) -> dict[str, Any]:
        current = self.current_step
        return {
            "planId": self.plan.id,
            "planIteration": self.plan.iteration,
            "stepId": step_id or (current.id if current is not None else None),
        }

    def evidence_replan_instruction(self) -> str:
        return self.replan_instruction(None)

    def replans_used(self) -> int:
        return self.store.count_iterations(self.plan.id)

    def can_replan(self, limit: int = 2) -> bool:
        return self.replans_used() < max(0, int(limit))

    def replan(self, *, run_id: str = "", reason: str = "evidence") -> int:
        # The step that just failed, not the next pending one.
        step = next((s for s in self.plan.steps if s.status == "failed"), None)
        step = step or self.current_step
        if step is not None:
            # Retire the failed draft's answer claims; the tool-result evidence
            # it gathered remains valid and is reused by the next attempt.
            if run_id:
                self.store.supersede_claims(run_id, step.id)
            self.store.set_step_status(step.id, "running")
        iteration = self.plan.iteration + 1
        self.store.record_iteration(self.plan.id, iteration, trigger="evidence", reason=reason)
        refreshed = self.store.get_plan(self.plan.id)
        if refreshed is not None:
            self.plan = refreshed
        return iteration

    def replan_instruction(self, verdict: Any) -> str:
        missing = []
        for item in getattr(verdict, "verdicts", [])[:5]:
            if not getattr(item, "ok", False):
                reason = getattr(item, "reason", "") or "unverified"
                missing.append(f"- {reason}")
        detail = "\n".join(missing) or "- the answer has no supporting evidence"
        return (
            "Your previous answer failed the evidence check for this step. "
            "Do the work again and gather concrete handles (a tool result, file, "
            "computation or citation) for every numeric, factual or file claim.\n"
            f"{detail}\n"
            "Do not repeat the same unsupported assertions. If evidence is genuinely "
            "unavailable, say so explicitly instead of asserting the claim."
        )

    def settle(self, run_id: str, *, ok: bool) -> str:
        """Close the current step. A step without evidence is never 'verified'."""
        step = self.current_step
        if step is None:
            return "complete" if self.plan.complete else "pending"
        supported = [
            claim for claim in self.ledger.claims(run_id)
            if claim.step_id == step.id and claim.status == "supported"
        ]
        if ok and supported:
            self.store.set_step_status(step.id, "verified", run_id=run_id)
            status = "verified"
        else:
            self.store.set_step_status(step.id, "failed", run_id=run_id)
            status = "failed"
        refreshed = self.store.get_plan(self.plan.id)
        if refreshed is not None:
            self.plan = refreshed
        return status

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "plan": self.plan.to_dict(),
            "currentStepId": self.current_step.id if self.current_step else None,
        }

    # ── Construction ─────────────────────────────────────────────────────────
    @classmethod
    def from_request(cls, store: Any, request: Any) -> Optional["PlanRuntime"]:
        context = _context(request)
        spec = context.get(PLAN_CONTEXT_KEY)
        if not isinstance(spec, dict) or not spec:
            return None
        goals = GoalStore(store)
        ledger = EvidenceLedger(goals)

        plan_id = str(spec.get("planId") or "").strip()
        if plan_id:
            plan = goals.get_plan(plan_id)
            if plan is None:
                return None
            goal = goals.get_goal(plan.goal_id)
            if goal is None:
                return None
            # A resumed run re-enters the first non-verified step.
            for step in plan.steps:
                if step.status not in ("verified", "skipped", "cancelled"):
                    goals.set_step_status(step.id, "running", run_id=str(getattr(request, "runId", "")))
                    break
            refreshed = goals.get_plan(plan.id)
            return cls(goal=goal, plan=refreshed or plan, ledger=ledger, store=goals)

        objective = str(spec.get("objective") or "").strip()
        if not objective:
            return None
        goal = goals.create_goal(
            objective,
            acceptance=list(spec.get("acceptance") or []),
            budget=dict(spec.get("budget") or {}),
        )
        steps = spec.get("steps") if isinstance(spec.get("steps"), list) else []
        if not steps:
            steps = [{"title": objective[:200], "objective": objective}]
        plan = goals.create_plan(goal.id, steps)
        if plan.steps:
            goals.set_step_status(plan.steps[0].id, "running", run_id=str(getattr(request, "runId", "")))
        plan = goals.get_plan(plan.id) or plan
        goal = goals.get_goal(goal.id) or goal
        return cls(goal=goal, plan=plan, ledger=ledger, store=goals)


__all__ = ["MAX_PROMPT_BLOCK", "PLAN_CONTEXT_KEY", "PlanRuntime"]
