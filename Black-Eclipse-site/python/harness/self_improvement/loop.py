"""The RSL conductor: one bounded asyncio task beside `learning_review`.

It scans inert/proposed `EvolutionCandidate` rows, claims one atomically, runs
the approved verifier, records the experiment, and stops. It adds no worker
kind, queue, scheduler or second runtime. `HARNESS_RSL_MODE=off` (the default)
is a strict no-op.

R4 verification is honest:
* code candidates run their owning tests in a worktree, with the benchmark
  recorded as UNMEASURED;
* surface candidates use `verifier.verify_surface` (the only measured path).
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import time
from typing import Any, Optional

from ..code.evolution_store import EvolutionStore
from ..evaluation.store import EvaluationStore
from ..persistence import now_iso
from ..skills.permissions import Actor
from . import proposer, recorder, verifier
from .config import RSLConfig


def _utc_day_start() -> str:
    today = _dt.datetime.now(_dt.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return today.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


class RSLLoop:
    """The bounded conductor. Construct with a service, or inject test doubles."""

    def __init__(
        self,
        service: Any = None,
        *,
        config: Optional[RSLConfig] = None,
        run_store: Any = None,
        evolution: Optional[EvolutionStore] = None,
        eval_store: Optional[EvaluationStore] = None,
        verify_fn: Any = None,
        propose_fn: Any = None,
        recorder_fn: Any = None,
    ) -> None:
        self.service = service
        self.config = config or RSLConfig.from_env()
        self.run_store = run_store or getattr(service, "store", None)
        self.evolution = evolution or (
            service.evolution_store() if service is not None
            else EvolutionStore(self.run_store)
        )
        self.eval_store = eval_store or (
            EvaluationStore(self.run_store) if self.run_store is not None else None
        )
        self.verify_fn = verify_fn
        self.propose_fn = propose_fn
        self.recorder_fn = recorder_fn or recorder.record_code_experiment
        self._task: Optional[asyncio.Task[Any]] = None
        self._wake = asyncio.Event()
        self._busy = False
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------
    def _actor(self) -> Actor:
        return Actor(id="rsl", operator=False, autonomy="edit_verify")

    async def start(self) -> None:
        if self.config.is_off:
            return
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="rsl-loop")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    async def _run(self) -> None:
        try:
            await self.resume()
        except Exception:  # noqa: BLE001 - resume is best-effort
            pass
        try:
            # Process anything already proposed before the first periodic tick.
            await self.tick()
        except Exception:  # noqa: BLE001 - one boot tick never kills the loop
            pass
        while not self._stopping:
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.config.tick_seconds)
            except asyncio.TimeoutError:
                pass
            if self._stopping:
                return
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - one tick never kills the loop
                pass

    def wake(self) -> None:
        self._wake.set()

    def health(self) -> dict[str, Any]:
        return {
            "mode": self.config.mode,
            "running": bool(self._task is not None and not self._task.done()),
            "busy": self._busy,
            "maxCandidates": self.config.max_candidates,
            "maxExperimentsPerDay": self.config.max_experiments_per_day,
            "k": self.config.k,
        }

    def status(self) -> dict[str, Any]:
        """The operator's bounded view of mode, lifecycle and daily budget."""
        started = self.evolution.experiments_started_since(_utc_day_start())
        maximum = max(0, int(self.config.max_experiments_per_day))
        return {
            **self.health(),
            "startedToday": started,
            "remainingToday": max(0, maximum - started),
            "budgetExhausted": started >= maximum,
            "tickSeconds": self.config.tick_seconds,
            "leaseSeconds": self.config.lease_seconds,
            "trials": self.config.trials,
            "maxCostUsd": self.config.max_cost_usd,
        }

    async def run_recursive(
        self,
        candidate: dict[str, Any],
        *,
        verify_fn: Any,
        variants: Any = None,
        seed: int = 0,
        measure: Any = None,
        trajectories: Any = None,
        evidence_dir: Any = None,
        record_attempts: bool = True,
    ) -> dict[str, Any]:
        """Run ONE bounded k-candidate experiment through the R7 conductor.

        The existing loop still owns single-candidate ticks. This entry point
        uses the same configured `k`, actor, stores and daily budget, records
        the selection/composition as an `EvaluationRun`, and never activates.
        """
        if self.config.mode != "verify":
            return {
                "refused": True,
                "reason": "mode",
                "mode": self.config.mode,
                "k": 0,
                "selection": None,
                "composition": None,
            }
        if self._busy:
            return {
                "refused": True,
                "reason": "busy",
                "k": 0,
                "selection": None,
                "composition": None,
            }
        from .recursion import run_recursive  # noqa: PLC0415 - one-way dependency

        self._busy = True
        try:
            return await run_recursive(
                candidate,
                verify_fn=verify_fn,
                k=self.config.k,
                variants=variants,
                seed=seed,
                actor=self._actor(),
                measure=measure,
                trajectories=trajectories,
                evidence_dir=evidence_dir,
                started_today=self.evolution.experiments_started_since(_utc_day_start()),
                max_per_day=self.config.max_experiments_per_day,
                eval_store=self.eval_store,
                run_store=self.run_store,
                record_attempts=record_attempts,
            )
        finally:
            self._busy = False

    # -- recovery / budget -------------------------------------------------
    def resume(self) -> list[str]:
        reclaimed = self.evolution.reclaim_stale(self.config.lease_seconds)
        for candidate_id in reclaimed:
            candidate = self.evolution.get_candidate(candidate_id) or {}
            self.evolution.save_attempt({
                "candidateId": candidate_id,
                "targetPath": candidate.get("targetPath") or "",
                "baseDigest": "",
                "diffDigest": "lease-expired",
                "proposedOps": candidate.get("proposedOps") or [],
                "outcome": "failure",
                "outcomeReason": "lease expired",
                "finishedAt": now_iso(),
            })
        return reclaimed

    def budget_ok(self) -> bool:
        started = self.evolution.experiments_started_since(_utc_day_start())
        return started < max(0, int(self.config.max_experiments_per_day))

    def scan(self, *, status: str = "inert") -> list[dict[str, Any]]:
        """The bounded candidate window for one tick."""
        return self.evolution.list_candidates(
            status=status, limit=self.config.max_candidates,
        )

    # -- ticks -------------------------------------------------------------
    async def tick(self) -> dict[str, Any]:
        if self.config.is_off:
            return {"mode": "off", "processed": []}
        if self.config.mode == "observe":
            # R1's deterministic observer owns observation; the conductor does
            # not run a candidate in observe mode.
            return {"mode": "observe", "processed": []}
        if self._busy:
            return {"mode": self.config.mode, "skipped": "busy", "processed": []}
        self._busy = True
        try:
            if self.config.mode == "propose":
                return self._propose_tick()
            return await self._verify_tick()
        finally:
            self._busy = False

    def _propose_tick(self) -> dict[str, Any]:
        proposed: list[str] = []
        refused: list[dict[str, Any]] = []
        candidates = self.scan(status="inert")
        for candidate in candidates:
            if not candidate.get("targetPath") or not candidate.get("proposedOps"):
                continue
            try:
                if self.propose_fn is not None:
                    self.propose_fn(candidate)
                else:
                    proposer.propose_from_ops(
                        self.run_store, str(candidate["id"]), actor=self._actor(),
                    )
                proposed.append(str(candidate["id"]))
            except proposer.ProposalRefused as exc:
                refused.append({"candidateId": candidate["id"], **exc.to_dict()})
        return {"mode": "propose", "proposed": proposed, "refused": refused,
                "processed": proposed}

    async def _verify_tick(self) -> dict[str, Any]:
        if not self.budget_ok():
            return {"mode": "verify", "skipped": "budget", "processed": []}
        candidates = self.scan(status="proposed")
        for candidate in candidates:
            claimed = self.evolution.claim(str(candidate["id"]))
            if claimed is None:
                continue
            return await self._verify_claimed(claimed)
        return {"mode": "verify", "skipped": "none", "processed": []}

    async def _verify_claimed(self, candidate: dict[str, Any]) -> dict[str, Any]:
        candidate_id = str(candidate["id"])
        run_id = f"rsl-{candidate_id}-{int(time.time())}"
        ctx = None
        if self.service is not None:
            try:
                ctx = self.service.evolution_context(run_id=run_id)
            except Exception:  # noqa: BLE001 - the verifier will report the reason
                ctx = None
        subject_type = str(candidate.get("subjectType") or "code")
        try:
            if self.verify_fn is not None:
                verification = await asyncio.to_thread(self.verify_fn, candidate)
            elif subject_type == "surface":
                # The ONLY measured path: a validated snapshot runs on the real
                # evaluator against a baseline of the same base snapshot.
                verification = await verifier.verify_surface_candidate(
                    self.run_store, candidate,
                    config=self.config, eval_store=self.eval_store,
                )
            else:
                verification = await asyncio.to_thread(
                    verifier.verify_code, self.run_store, candidate_id,
                    ctx=ctx, actor=self._actor(),
                )
        except Exception as exc:  # noqa: BLE001 - a failed verification is a decision
            verification = {
                "ok": False, "passed": False, "refused": False,
                "benchmark": "UNMEASURED", "decision": "verification_error",
                "detail": str(exc),
            }

        if verification.get("refused"):
            self.evolution.update_candidate(
                candidate_id, status="refused",
                refusalCode=str(verification.get("code") or "RSL_REFUSED"),
            )
            decision = "refused"
        else:
            self.evolution.update_candidate(
                candidate_id,
                status="evaluated_ok" if verification.get("passed") else "evaluated_bad",
            )
            if subject_type == "surface":
                record = verification.get("decisionRecord") or {}
                decision = (
                    "benchmark_accepted" if record.get("accepted")
                    else "benchmark_rejected" if record
                    else str(verification.get("decision") or "verification_error")
                )
            else:
                decision = "tests_passed" if verification.get("passed") else "tests_failed"
        if self.eval_store is not None and self.run_store is not None:
            if subject_type == "surface":
                try:
                    recorder.record_surface_experiment(
                        self.run_store, self.evolution,
                        candidate=candidate, verification=verification,
                        decision=decision,
                    )
                except Exception:  # noqa: BLE001 - recording is best-effort
                    pass
            else:
                try:
                    self.recorder_fn(
                        self.eval_store, self.run_store,
                        run_id=run_id, candidate=candidate,
                        verification=verification, decision=decision,
                    )
                except Exception:  # noqa: BLE001 - recording is best-effort
                    pass
        return {
            "mode": "verify",
            "candidateId": candidate_id,
            "runId": verification.get("runId") or run_id,
            "decision": decision,
            "benchmark": verification.get("benchmark", "UNMEASURED"),
            "processed": [candidate_id],
        }


__all__ = ["RSLLoop", "now_iso"]
