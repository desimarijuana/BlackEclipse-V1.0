"""Automatic post-run learning review — a bounded, safe self-improvement loop.

After a run completes, a bounded review analyzes it and may produce ONE OR MORE
outcomes:

  * ``durable_memory_proposal`` — a stable user preference / project convention /
    environment fact / explicit correction, routed through the shared decision
    gate (``decision.authorize_proposal``);
  * ``memory_suggestion`` — an inert Save/Dismiss suggestion (never recalled);
  * ``correction_candidate`` — a likely correction/conflict needing review;
  * ``skill_candidate`` — an inert reusable-procedure candidate with recurrence,
    scope, evidence and limitations (never enabled);
  * ``mistake_recovery`` — a captured mistake/recovery record;
  * ``no_learning`` — nothing worth recording.

Hard safety rules (enforced here, not by the model):

  * every durable write passes the ONE decision gate; a model proposal can never
    authorize its own write;
  * a skill is NEVER activated — candidates stay inert until evaluation and
    operator approval;
  * no secrets, no current market facts, no predictions, no one-off task detail;
  * a single market/provider failure is not generalized globally;
  * failures are recorded but never affect the completed chat response.

The queue is deliberately a lightweight in-process asyncio queue: bounded
concurrency, bounded time, one retry, duplicate coalescing, and shutdown
cancellation. No Redis/Celery.

The deterministic path is authoritative and cheap. An optional bounded review
*model* may add a suggestion, but its output is inert and re-authorized by the
gate — it can never write or activate anything.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

from .persistence import now_iso

# Bounded defaults.
MAX_CONCURRENT_REVIEWS = 1
REVIEW_TIMEOUT_S = 20.0
REVIEW_MAX_ATTEMPTS = 2  # one retry
MODEL_TOKEN_BUDGET = 800
_MODEL_INPUT_CHARS = 6000

# Idle-aware scheduling: keep expensive reviews off the foreground. A review
# queued while the user is active waits for this idle window; a
# critical/manual review bypasses it.
IDLE_DELAY_S = 3.0

# Priority ordering (higher wins). `critical` (correction/security) is chosen
# first, then a failed active skill, then a repeated successful workflow, then a
# normal completed run, then profile consolidation.
PRIORITY_LEVELS = {
    "low": 0,
    "normal": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# The categories a review may return. A model may not invent a new one.
OUTCOME_CATEGORIES = frozenset(
    {
        "durable_memory_proposal",
        "memory_suggestion",
        "correction_candidate",
        "skill_candidate",
        "skill_patch",
        "mistake_recovery",
        "no_learning",
    }
)

# Market/provider-specific failure wording that must NOT be generalized globally.
_MARKET_SPECIFIC_RE = re.compile(
    r"\b(ticker|price|quote|market|exchange|symbol|[A-Z]{1,5})\b.*\b(fail|error|down|stale|missing)",
    re.IGNORECASE,
)


def _digest(run_id: str, run: dict[str, Any]) -> str:
    import hashlib

    raw = json.dumps(
        {
            "runId": run_id,
            "status": run.get("status"),
            "output": (run.get("output") or "")[:500],
            "memory": run.get("memory"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _bounded(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the persisted result JSON bounded and content-free of raw transcripts."""
    outcomes = result.get("outcomes") or []
    trimmed: list[dict[str, Any]] = []
    for outcome in outcomes[:8]:
        payload = outcome.get("payload") or {}
        # Only bounded fields travel; never a raw transcript.
        safe_payload = {
            k: (v[:400] if isinstance(v, str) else v)
            for k, v in payload.items()
            if k in ("content", "memoryType", "scope", "reason", "category", "recurrence", "limitations", "evidenceRunId", "skill", "baseVersion")
        }
        trimmed.append({
            "category": outcome.get("category"),
            "created": bool(outcome.get("created")),
            "inert": bool(outcome.get("inert", True)),
            "reason": (outcome.get("reason") or "")[:300],
            "payload": safe_payload,
        })
    return {
        "reviewId": result.get("reviewId"),
        "runId": result.get("runId"),
        "mode": result.get("mode", "deterministic"),
        "outcomes": trimmed,
        "modelUsed": bool(result.get("modelUsed")),
        "tokenBudget": result.get("tokenBudget"),
        "gateApplied": True,
        "noLearning": not any(o.get("created") for o in trimmed),
    }


def _skill_patch_proposal(service: Any, run_store: Any, run_id: str) -> Optional[dict[str, Any]]:
    """Flag a structured skill patch opportunity for a FAILED enabled skill.

    The deterministic review does NOT invent skill content. It records that a
    reusable skill failed in this run and returns the inert patch template
    (skill, baseVersion, evidenceRuns, regressionCases) so an operator/model can
    author the operations. It never creates a version, never activates anything,
    and never mutates the active skill. A missing skill or store returns None.
    """
    store = getattr(service, "store", None)
    registry = getattr(service, "skill_registry", None)
    if store is None:
        return None
    try:
        executions = run_store.list_tool_executions(run_id) or []
    except Exception:  # noqa: BLE001
        return None
    failed_skill: Optional[str] = None
    for execution in executions:
        if execution.get("ok"):
            continue
        args = execution.get("args") or {}
        # The controlled skill sub-run records the skill id in its args.
        candidate = args.get("name") or args.get("skill_id") or args.get("skillId")
        if execution.get("name") == "skill_invoke" and candidate:
            failed_skill = str(candidate)
            break
    if not failed_skill:
        return None
    try:
        skill = store.get_skill(failed_skill)
    except Exception:  # noqa: BLE001
        skill = None
    if not skill or skill.get("status") not in ("enabled", "active"):
        return None
    base_version = skill.get("latestVersion")
    if not base_version:
        return None
    return {
        "category": "skill_patch",
        "created": False,
        "inert": True,
        "reason": (
            "an enabled skill failed in this run; a structured patch may be "
            "warranted — author operations, evaluate, then canary/activate"
        ),
        "payload": {
            "skill": failed_skill,
            "baseVersion": base_version,
            "evidenceRunId": run_id,
        },
    }


def review_run(
    service: Any,
    run_store: Any,
    run_id: str,
    *,
    model: bool = False,
    model_settings: Any = None,
) -> dict[str, Any]:
    """Run the deterministic (and optionally bounded-model) review for one run.

    Returns a bounded result dict. Never raises: this is called from a background
    worker where an exception must not propagate.
    """
    run = run_store.get_run(run_id) or {}
    outcomes: list[dict[str, Any]] = []
    try:
        outcomes.extend(_deterministic_outcomes(service, run_store, run_id))
    except Exception as exc:  # noqa: BLE001 - a failed review is recorded, not fatal
        outcomes.append({"category": "no_learning", "created": False, "reason": f"deterministic analysis error: {exc}"})

    model_used = False
    if model and model_settings is not None:
        try:
            model_outcomes = _model_outcomes(service, run, model_settings)
            if model_outcomes:
                model_used = True
                outcomes.extend(model_outcomes)
        except Exception as exc:  # noqa: BLE001 - model is best-effort and inert
            outcomes.append({"category": "no_learning", "created": False, "reason": f"model review error: {exc}"})

    if not outcomes:
        outcomes = [{"category": "no_learning", "created": False, "reason": "nothing durable detected"}]
    return _bounded({
        "runId": run_id,
        "mode": "deterministic+model" if model_used else "deterministic",
        "modelUsed": model_used,
        "tokenBudget": MODEL_TOKEN_BUDGET if model_used else None,
        "outcomes": outcomes,
    })


def _deterministic_outcomes(service: Any, run_store: Any, run_id: str) -> list[dict[str, Any]]:
    """The safe, cheap, deterministic review. Reuses the existing pipelines."""
    outcomes: list[dict[str, Any]] = []

    # 1) Reuse existing analysis: mistakes + inert skill candidates. It is
    #    deduplicated and never enables anything.
    try:
        analysis = service.analyze_run(run_id, run_store, skill_store=service.store)
    except Exception:  # noqa: BLE001
        analysis = {}
    if analysis.get("mistakesCreated"):
        outcomes.append({
            "category": "mistake_recovery", "created": True, "inert": True,
            "reason": "a failure/recovery was captured deterministically",
            "payload": {"category": "mistake", "evidenceRunId": run_id},
        })
    if analysis.get("candidatesCreated"):
        outcomes.append({
            "category": "skill_candidate", "created": True, "inert": True,
            "reason": "an inert reusable-procedure candidate was created (recurrence-gated)",
            "payload": {"category": "skill", "evidenceRunId": run_id},
        })

    # 1b) A structured skill patch may be PROPOSED for an enabled skill that the
    #     run failed against. It is inert (a draft version) and an operator must
    #     evaluate + activate it; the active version is never touched here.
    patch_proposal = _skill_patch_proposal(service, run_store, run_id)
    if patch_proposal:
        outcomes.append(patch_proposal)

    # 2) Durable-memory proposal from the run's captured memory outcome. This
    #    only inspects what the run's own gate already surfaced; it re-runs the
    #    gate so a model sentence can never self-authorize.
    blob = (run_store.get_run(run_id) or {}).get("memory") or {}
    if isinstance(blob, dict):
        action = blob.get("action")
        content = blob.get("contentPreview")
        if action in ("remember", "save") and content:
            outcomes.append({
                "category": "durable_memory_proposal", "created": False, "inert": True,
                "reason": "already written through the decision gate during the run",
                "payload": {"content": content, "memoryType": blob.get("memoryType", "semantic")},
            })
        if action in ("correct", "corrected") and content:
            outcomes.append({
                "category": "correction_candidate", "created": False, "inert": True,
                "reason": "correction already recorded during the run",
                "payload": {"content": content},
            })
    return outcomes


def _model_outcomes(service: Any, run: dict[str, Any], model_settings: Any) -> list[dict[str, Any]]:
    """A bounded, optional model review. Its output is INERT and gate-checked.

    The model may only return a strict JSON object; unknown categories and any
    content that fails the gate are dropped. It can never write or activate.
    """
    from .model_runtime import get_runtime  # local import: keep the module light
    from .models import build_chat_model

    prompt = (
        "You review a completed assistant run to decide whether anything is worth "
        "learning. Return STRICT JSON: {\"outcomes\":[{\"category\":\"durable_memory_proposal\"|"
        "\"memory_suggestion\"|\"correction_candidate\"|\"no_learning\",\"content\":\"...\","
        "\"memoryType\":\"preference|semantic|procedural|constraint|correction\",\"reason\":\"...\"}]}. "
        "Only durable, stable user preferences, project conventions, environment facts or explicit "
        "corrections qualify. NEVER include current prices/market facts, predictions, secrets, raw "
        "transcripts or one-off task details. If nothing qualifies return {\"outcomes\":[]}.\n\n"
        f"USER TURN:\n{(run.get('input', {}) or {}).get('query', '')[:1500]}\n\n"
        f"FINAL ANSWER:\n{(run.get('output') or '')[:3000]}"
    )
    _runtime = get_runtime()
    _resolution = _runtime.resolve_for_run(model_settings, task="classification")
    model = _runtime.build(
        _resolution.settings, builder=build_chat_model, adapter=_resolution.adapter
    )
    result = model.invoke(prompt)
    text = getattr(result, "content", "") or ""
    if isinstance(text, list):
        text = " ".join(str(part) for part in text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return []

    outcomes: list[dict[str, Any]] = []
    settings = service.policy.get_all()
    for item in (parsed.get("outcomes") or [])[:4]:
        category = item.get("category")
        content = str(item.get("content") or "").strip()
        if category not in ("durable_memory_proposal", "memory_suggestion", "correction_candidate"):
            continue
        if not content:
            continue
        # The model only PROPOSES. The gate re-authorizes against the user turn.
        from .eclipse_memory.decision import authorize_proposal

        decision = authorize_proposal(
            content=content, provenance="run_analysis",
            user_message=(run.get("input", {}) or {}).get("query", ""),
            memory_type=str(item.get("memoryType") or "semantic"),
            scope="general", confidence=0.6, settings=settings,
        )
        created = False
        if category == "durable_memory_proposal" and decision.outcome == "save":
            # Even a gate-approved model proposal is surfaced as a review item,
            # never silently written from the background.
            created = False
        elif category == "memory_suggestion" and decision.outcome in ("save", "suggest"):
            created = False
        outcomes.append({
            "category": category,
            "created": created,
            "inert": True,
            "reason": f"model proposal re-checked by the gate ({decision.outcome}); requires operator review",
            "payload": {"content": content, "memoryType": decision.memory_type, "reason": decision.reason},
        })
    return outcomes


class _QueuedReview:
    """One queued review with scheduling metadata."""

    __slots__ = ("run_id", "priority", "session_id", "profile_id", "mode", "model", "manual")

    def __init__(
        self, run_id: str, *, priority: str = "normal", session_id: Optional[str] = None,
        profile_id: Optional[str] = None, mode: str = "automatic_selective",
        model: bool = False, manual: bool = False,
    ) -> None:
        self.run_id = run_id
        self.priority = priority if priority in PRIORITY_LEVELS else "normal"
        self.session_id = session_id
        self.profile_id = profile_id
        self.mode = mode
        self.model = model
        self.manual = manual


class LearningReviewQueue:
    """A bounded in-process review queue with priority, idle deferral, coalescing
    and shutdown safety.

    Scheduling improves on a plain FIFO queue:

      * priorities are chosen highest-first (`critical` → `low`);
      * multiple reviews for the same session coalesce (the newest snapshot wins,
        obsolete ones are discarded);
      * while the user is active, a normal review waits for a short idle window;
        a `critical` or manual review bypasses the wait;
      * one review can never kill a worker.
    """

    def __init__(
        self,
        service: Any,
        run_store: Any,
        *,
        max_concurrent: int = MAX_CONCURRENT_REVIEWS,
        timeout_s: float = REVIEW_TIMEOUT_S,
        idle_delay_s: float = IDLE_DELAY_S,
    ) -> None:
        self.service = service
        self.run_store = run_store
        self.max_concurrent = max(1, int(max_concurrent))
        self.timeout_s = float(timeout_s)
        self.idle_delay_s = float(idle_delay_s)
        self._heap: list[tuple[int, int, _QueuedReview]] = []
        self._counter = 0
        self._wake = asyncio.Event()
        self._workers: list[asyncio.Task[Any]] = []
        self._pending: dict[str, _QueuedReview] = {}
        self._by_session: dict[str, str] = {}
        self._running: set[str] = set()
        self._stopping = False
        self._active_until = 0.0  # monotonic time user activity is expected until
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def start(self) -> None:
        if self._workers:
            return
        self._stopping = False
        for index in range(self.max_concurrent):
            self._workers.append(asyncio.create_task(self._worker(index), name=f"learning-review-{index}"))

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._workers = []
        self._heap.clear()
        self._pending.clear()
        self._by_session.clear()

    def mark_user_active(self) -> None:
        """Record foreground activity so normal reviews defer to a short idle."""
        self._active_until = asyncio.get_event_loop().time() + self.idle_delay_s
        self._wake.set()

    def _idle_ready(self) -> bool:
        try:
            return asyncio.get_event_loop().time() >= self._active_until
        except RuntimeError:
            return True

    async def enqueue(
        self, run_id: str, *, priority: str = "normal",
        session_id: Optional[str] = None, profile_id: Optional[str] = None,
        model: bool = False, manual: bool = False,
    ) -> bool:
        """Queue a review, coalescing duplicates. Returns True if added.

        A review for the same session replaces the older queued snapshot (the
        obsolete one is discarded), so a burst of runs for one session does not
        produce N stale reviews.
        """
        async with self._get_lock():
            if run_id in self._pending or run_id in self._running:
                return False
            review = _QueuedReview(
                run_id, priority=priority, session_id=session_id,
                profile_id=profile_id, model=model, manual=manual,
            )
            if session_id:
                previous = self._by_session.get(session_id)
                if previous and previous != run_id:
                    # Coalesce: drop the older queued snapshot for this session.
                    self._pending.pop(previous, None)
                    self._rebuild_heap()
            self._pending[run_id] = review
            if session_id:
                self._by_session[session_id] = run_id
            self._counter += 1
            # heapq is a min-heap; negate priority so the highest wins.
            self._heap.append((-PRIORITY_LEVELS[review.priority], self._counter, review))
            import heapq

            heapq.heapify(self._heap)
        self._wake.set()
        return True

    def _rebuild_heap(self) -> None:
        self._heap = [item for item in self._heap if item[2].run_id in self._pending]

    async def _next_review(self) -> Optional[_QueuedReview]:
        while not self._stopping:
            import heapq

            if self._heap:
                _, _, review = heapq.heappop(self._heap)
                if review.run_id not in self._pending:
                    continue  # coalesced away
                # Idle-aware: a normal review waits; critical/manual bypasses.
                if not review.manual and PRIORITY_LEVELS[review.priority] < PRIORITY_LEVELS["critical"]:
                    if not self._idle_ready():
                        # Put it back and wait for the idle timer / new work.
                        heapq.heappush(self._heap, (-PRIORITY_LEVELS[review.priority], self._counter, review))
                        self._wake.clear()
                        try:
                            await asyncio.wait_for(self._wake.wait(), timeout=self.idle_delay_s)
                        except asyncio.TimeoutError:
                            pass
                        continue
                return review
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
        return None

    async def _worker(self, index: int) -> None:
        while not self._stopping:
            review = await self._next_review()
            if review is None:
                return
            self._pending.pop(review.run_id, None)
            if review.session_id:
                self._by_session.pop(review.session_id, None)
            self._running.add(review.run_id)
            try:
                await self._process(review)
            except asyncio.CancelledError:
                self._running.discard(review.run_id)
                return
            except Exception:  # noqa: BLE001 - worker must never die on one run
                pass
            finally:
                self._running.discard(review.run_id)

    async def _process(self, review: _QueuedReview) -> None:
        run_id = review.run_id
        # Persist a queued row so the queue is observable even mid-flight.
        record = self.run_store.save_learning_review({
            "runId": run_id, "status": "queued", "mode": "deterministic",
            "priority": review.priority, "sessionId": review.session_id,
            "profileId": review.profile_id, "createdAt": now_iso(),
        })
        review_id = record["id"]
        self.run_store.update_learning_review(review_id, status="running", startedAt=now_iso())
        run = self.run_store.get_run(run_id) or {}
        digest = _digest(run_id, run)

        last_error: Optional[str] = None
        for attempt in range(1, REVIEW_MAX_ATTEMPTS + 1):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        review_run, self.service, self.run_store, run_id,
                        model=review.model, model_settings=run.get("_model_settings"),
                    ),
                    timeout=self.timeout_s,
                )
                result["reviewId"] = review_id
                self.run_store.update_learning_review(
                    review_id, status="completed", finishedAt=now_iso(),
                    inputDigest=digest, attempts=attempt, result=result, error=None,
                )
                return
            except asyncio.TimeoutError:
                last_error = "review timed out"
            except asyncio.CancelledError:
                self.run_store.update_learning_review(
                    review_id, status="cancelled", finishedAt=now_iso(), error="cancelled"
                )
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
        self.run_store.update_learning_review(
            review_id, status="failed", finishedAt=now_iso(),
            inputDigest=digest, attempts=REVIEW_MAX_ATTEMPTS, error=last_error,
        )

    def health(self) -> dict[str, Any]:
        base = self.run_store.learning_review_health()
        idle = True
        try:
            now = asyncio.get_running_loop().time()
            idle = now >= self._active_until
        except RuntimeError:
            idle = True
        return {
            **base,
            "queue": {
                "queued": len(self._pending),
                "running": len(self._running),
                "maxConcurrent": self.max_concurrent,
                "timeoutMs": int(self.timeout_s * 1000),
                "idleDelayMs": int(self.idle_delay_s * 1000),
                "idle": idle,
                "priorities": {
                    review.priority: sum(1 for r in self._pending.values() if r.priority == review.priority)
                    for review in list(self._pending.values())
                },
            },
        }


__all__ = [
    "LearningReviewQueue",
    "OUTCOME_CATEGORIES",
    "review_run",
]
