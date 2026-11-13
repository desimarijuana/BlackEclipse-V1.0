"""W8 cross-workstream signal aggregates.

The observability hub projects the existing bus into typed hooks. This module
turns the W8 hooks into the release-report sections and SLO inputs without
growing `core.py` past its budget.

Two rules govern everything here:

* **Bounded cardinality.** Counters are keyed by a closed vocabulary (outcome,
  stage, action, verdict); ids and paths are never labels.
* **Honest reporting.** An aggregate with no samples reports `samples: 0` and a
  `null` rate; it does not invent a zero that reads as healthy.
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any, Mapping, Optional

_MAX_SAMPLES = 5000


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    samples = sorted(values)
    idx = min(len(samples) - 1, max(0, int(q * (len(samples) - 1) + 0.5)))
    return round(samples[idx], 4)


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def capabilities(environ: Optional[Mapping[str, str]] = None) -> dict[str, bool]:
    """Which workstreams are actually enabled in this deployment.

    The gate uses this to turn a check from `pass` into `skipped` instead of
    treating "the feature is off" as "the feature is healthy".
    """
    try:
        from ..config import flags  # noqa: PLC0415

        def flag(name: str) -> str:
            return flags.get_flag(name, environ=environ)

        def enabled(name: str) -> bool:
            return flag(name) == "on"

        return {
            "modelGateway": flag("HARNESS_MODEL_GATEWAY") != "off",
            "contextLadder": flag("HARNESS_COMPRESSION_LADDER") != "off",
            "parallelTools": enabled("HARNESS_PARALLEL_TOOLS"),
            "autonomy": flag("HARNESS_GOAL_LOOP") != "off" and enabled("HARNESS_AUTONOMY"),
            "learningEval": enabled("HARNESS_SKILL_EXEC_EVAL"),
            "runKernelIntegrity": flag("HARNESS_EVENT_SEQ") != "off",
            "fileCheckpoints": flag("HARNESS_FILE_CHECKPOINTS") != "off",
            "asyncDelegation": enabled("HARNESS_ASYNC_DELEGATION"),
        }
    except Exception:  # noqa: BLE001 - capabilities must never break a report
        return {
            "modelGateway": True, "contextLadder": True, "parallelTools": False,
            "autonomy": False, "learningEval": True, "runKernelIntegrity": True,
            "fileCheckpoints": False, "asyncDelegation": False,
        }


class SignalAggregates:
    """Bounded aggregates for the W8 signal contract."""

    def __init__(self) -> None:
        # Model
        self.model_attempts = 0
        self.model_outcomes: Counter[str] = Counter()
        self.model_attempts_by_run: dict[str, int] = {}
        self.model_fallbacks = 0
        self.model_fallback_success = 0
        self.model_retries = 0
        self.model_ttft_timeouts = 0
        self.model_ttft_ms: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self.model_priced = 0
        self.model_attempts_priced = 0

        # Context
        self.context_usage_ratio: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self.context_overflow = 0
        self.context_recovered = 0
        self.context_compactions = 0
        self.context_compaction_failures = 0
        self.context_stages: Counter[str] = Counter()

        # Tools
        self.tool_batches = 0
        self.tool_batch_max_concurrency = 0
        self.tool_batch_ordering_violations = 0
        self.tool_batch_durations: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self.tool_guardrails: Counter[str] = Counter()
        self.tool_guardrail_rules: Counter[str] = Counter()

        # Goals
        self.goals_created = 0
        self.goal_verdicts: Counter[str] = Counter()
        self.goal_turns: deque[float] = deque(maxlen=_MAX_SAMPLES)

        # Learning
        self.skill_evals = 0
        self.skill_eval_passed = 0
        self.skill_eval_failed = 0
        self.skill_eval_needs_review = 0
        self.curator_runs = 0
        self.curator_proposals = 0
        self.curator_applied = 0
        self.curator_failed = 0

        # Integrity invariants (any occurrence is a defect)
        self.effect_unknown: Counter[str] = Counter()
        self.lease_lost = 0
        self.checkpoint_write_failures: Counter[str] = Counter()
        self.checkpoint_write_ms: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self.event_seq_retries = 0
        self.event_seq_collisions = 0
        self.hardline_blocked: Counter[str] = Counter()
        self.skill_enabled_without_eval = 0

        # W7 — file checkpoints + delegation
        self.file_checkpoint_created = 0
        self.file_checkpoint_failed = 0
        self.file_checkpoint_restored = 0
        self.file_checkpoint_pruned = 0
        self.file_checkpoint_bytes: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self.delegation_started = 0
        self.delegation_completed = 0
        self.delegation_failed = 0
        self.delegation_repairs: Counter[str] = Counter()
        self.delegation_worktrees = 0
        self.delegation_steer_chars = 0

    # ── recorders ────────────────────────────────────────────────────────────
    def record_model_attempt(self, data: Mapping[str, Any], *, run_id: str = "") -> None:
        self.model_attempts += 1
        outcome = str(data.get("outcome") or "failed")
        self.model_outcomes[outcome] += 1
        if run_id:
            self.model_attempts_by_run[run_id] = self.model_attempts_by_run.get(run_id, 0) + 1
            if len(self.model_attempts_by_run) > _MAX_SAMPLES:
                for key in list(self.model_attempts_by_run)[:1000]:
                    self.model_attempts_by_run.pop(key, None)
        if data.get("willRetry"):
            self.model_retries += 1
        if data.get("willFallback"):
            # Denominator: one fallback transition. Numerator comes from the
            # `model.fallback` event, which is emitted only when the fallback
            # attempt actually succeeded.
            self.model_fallbacks += 1
        if data.get("priced"):
            self.model_attempts_priced += 1
            self.model_priced += 1
        ttft = data.get("ttftMs")
        if isinstance(ttft, (int, float)) and ttft >= 0:
            self.model_ttft_ms.append(float(ttft))

    def record_model_fallback(self, data: Mapping[str, Any]) -> None:
        # Emitted once when a run completed on a fallback candidate.
        self.model_fallback_success += 1

    def record_first_token(self, data: Mapping[str, Any]) -> None:
        value = data.get("ttftMs")
        if isinstance(value, (int, float)) and value >= 0:
            self.model_ttft_ms.append(float(value))

    def record_ttft_timeout(self) -> None:
        self.model_ttft_timeouts += 1

    def record_context_pressure(self, data: Mapping[str, Any]) -> None:
        ratio = data.get("usageRatio")
        if isinstance(ratio, (int, float)) and ratio >= 0:
            self.context_usage_ratio.append(float(ratio))
        if data.get("overflow") or data.get("exhausted"):
            self.context_overflow += 1
        if data.get("recovered"):
            self.context_recovered += 1

    def record_context_compaction(self, data: Mapping[str, Any]) -> None:
        stage = str(data.get("stage") or "none")
        self.context_stages[stage] += 1
        ok = bool(data.get("ok"))
        if stage != "none":
            self.context_compactions += 1
        if not ok and stage != "none":
            self.context_compaction_failures += 1

    def record_tool_batch(self, data: Mapping[str, Any]) -> None:
        if data.get("planOnly"):
            return
        self.tool_batches += 1
        concurrency = data.get("maxConcurrency")
        if isinstance(concurrency, (int, float)):
            self.tool_batch_max_concurrency = max(self.tool_batch_max_concurrency, int(concurrency))
        violations = data.get("orderingViolations")
        if isinstance(violations, (int, float)):
            self.tool_batch_ordering_violations += max(0, int(violations))
        duration = data.get("durationMs")
        if isinstance(duration, (int, float)) and duration >= 0:
            self.tool_batch_durations.append(float(duration))

    def record_guardrail(self, data: Mapping[str, Any]) -> None:
        action = str(data.get("action") or "warn")
        self.tool_guardrails[action] += 1
        rule = str(data.get("rule") or "unknown")
        self.tool_guardrail_rules[rule] += 1

    def record_goal_created(self) -> None:
        self.goals_created += 1

    def record_goal_verdict(self, data: Mapping[str, Any]) -> None:
        verdict = str(data.get("verdict") or "continue")
        self.goal_verdicts[verdict] += 1
        turn = data.get("turn")
        if isinstance(turn, (int, float)) and turn >= 0:
            self.goal_turns.append(float(turn))

    def record_skill_eval(self, data: Mapping[str, Any]) -> None:
        self.skill_evals += 1
        if data.get("ok"):
            self.skill_eval_passed += 1
        elif str(data.get("status") or "") == "needs_review":
            self.skill_eval_needs_review += 1
        else:
            self.skill_eval_failed += 1

    def record_curator(self, data: Mapping[str, Any]) -> None:
        self.curator_runs += 1
        proposals = data.get("proposals")
        if isinstance(proposals, (int, float)):
            self.curator_proposals += max(0, int(proposals))
        applied = data.get("applied")
        if isinstance(applied, (int, float)):
            self.curator_applied += max(0, int(applied))
        if data.get("ok") is False or data.get("status") == "failed":
            self.curator_failed += 1

    def record_integrity(self, data: Mapping[str, Any]) -> None:
        kind = str(data.get("kind") or "")
        if kind == "effect_unknown":
            self.effect_unknown[str(data.get("tool") or "unknown")] += 1
        elif kind == "lease_lost":
            self.lease_lost += 1
        elif kind == "checkpoint_write_failed":
            self.checkpoint_write_failures[str(data.get("checkpoint") or "unknown")] += 1
        elif kind == "event_seq_retry":
            self.event_seq_retries += 1
        elif kind == "event_seq_collision":
            self.event_seq_collisions += 1
        elif kind == "hardline_blocked":
            self.hardline_blocked[str(data.get("pattern") or "unknown")] += 1
        elif kind == "skill_enabled_without_eval":
            self.skill_enabled_without_eval += 1
        duration = data.get("durationMs")
        if kind == "checkpoint_write" and isinstance(duration, (int, float)) and duration >= 0:
            self.checkpoint_write_ms.append(float(duration))

    def record_checkpoint_write(self, data: Mapping[str, Any]) -> None:
        duration = data.get("durationMs")
        if isinstance(duration, (int, float)) and duration >= 0:
            self.checkpoint_write_ms.append(float(duration))
        if data.get("ok") is False:
            self.checkpoint_write_failures[str(data.get("kind") or "boundary")] += 1

    def record_file_checkpoint(self, data: Mapping[str, Any], *, event_type: str = "") -> None:
        op = str(data.get("op") or event_type.rsplit(".", 1)[-1] or "created")
        if op == "created":
            self.file_checkpoint_created += 1
        elif op == "failed":
            self.file_checkpoint_failed += 1
        elif op == "restored":
            self.file_checkpoint_restored += 1
        elif op == "pruned":
            self.file_checkpoint_pruned += 1
        files = data.get("bytes")
        if isinstance(files, (int, float)) and files >= 0:
            self.file_checkpoint_bytes.append(float(files))

    def record_delegation(self, data: Mapping[str, Any], *, event_type: str = "") -> None:
        if event_type.endswith("started") or data.get("op") == "started":
            self.delegation_started += 1
        elif event_type.endswith(("failed", "cancelled")) or data.get("op") == "failed":
            self.delegation_failed += 1
        elif event_type.endswith("completed") or data.get("op") == "completed":
            self.delegation_completed += 1
        if event_type.startswith("delegation.repair"):
            self.delegation_repairs[event_type.rsplit(".", 1)[-1]] += 1
        if event_type.startswith("delegation.worktree"):
            self.delegation_worktrees += 1
        chars = data.get("chars")
        if isinstance(chars, (int, float)) and chars >= 0:
            self.delegation_steer_chars += int(chars)

    # ── report sections ──────────────────────────────────────────────────────
    def model_report(self) -> dict[str, Any]:
        per_run = list(self.model_attempts_by_run.values())
        return {
            "attempts": self.model_attempts,
            "attemptsPerRun": {
                "samples": len(per_run),
                "p50": _pct([float(v) for v in per_run], 0.50),
                "p95": _pct([float(v) for v in per_run], 0.95),
            },
            "fallbacks": self.model_fallbacks,
            "fallbackSuccessRate": _ratio(self.model_fallback_success, self.model_fallbacks),
            "retries": self.model_retries,
            "ttftTimeouts": self.model_ttft_timeouts,
            "pricedCoverage": _ratio(self.model_attempts_priced, self.model_attempts),
            "byOutcome": dict(sorted(self.model_outcomes.items())),
        }

    def ttft_report(self) -> dict[str, Any]:
        values = list(self.model_ttft_ms)
        return {
            "samples": len(values),
            "p50": _pct(values, 0.50),
            "p95": _pct(values, 0.95),
            "p99": _pct(values, 0.99),
        }

    def context_report(self) -> dict[str, Any]:
        usage = list(self.context_usage_ratio)
        samples = max(len(usage), self.context_overflow + self.context_recovered)
        return {
            "usageRatio": {
                "samples": len(usage),
                "p50": _pct(usage, 0.50),
                "p95": _pct(usage, 0.95),
            },
            "samples": samples,
            "overflow": self.context_overflow,
            "overflowRate": _ratio(self.context_overflow, samples),
            "recovered": self.context_recovered,
            "compactions": {
                "samples": self.context_compactions,
                "byStage": dict(sorted(self.context_stages.items())),
                "failures": self.context_compaction_failures,
                "failureRate": _ratio(self.context_compaction_failures, self.context_compactions),
            },
        }

    def tool_report(self) -> dict[str, Any]:
        return {
            "batches": {
                "count": self.tool_batches,
                "maxConcurrency": self.tool_batch_max_concurrency,
                "orderingViolations": self.tool_batch_ordering_violations,
                "p95DurationMs": _pct(list(self.tool_batch_durations), 0.95),
            },
            "guardrails": {
                "allow": self.tool_guardrails.get("allow", 0),
                "warn": self.tool_guardrails.get("warn", 0),
                "halt": self.tool_guardrails.get("halt", 0),
                "byRule": dict(sorted(self.tool_guardrail_rules.items())),
            },
        }

    def goals_report(self) -> dict[str, Any]:
        total = sum(self.goal_verdicts.values())
        done = self.goal_verdicts.get("done", 0)
        blocked = self.goal_verdicts.get("blocked", 0)
        return {
            "created": self.goals_created,
            "samples": total,
            "verdicts": dict(sorted(self.goal_verdicts.items())),
            "completionRate": _ratio(done, total),
            "blockedRate": _ratio(blocked, total),
            "turns": {
                "samples": len(self.goal_turns),
                "p50": _pct(list(self.goal_turns), 0.50),
                "p95": _pct(list(self.goal_turns), 0.95),
            },
        }

    def learning_report(self) -> dict[str, Any]:
        return {
            "executionEvals": {
                "total": self.skill_evals,
                "passed": self.skill_eval_passed,
                "failed": self.skill_eval_failed,
                "needsReview": self.skill_eval_needs_review,
            },
            "curator": {
                "runs": self.curator_runs,
                "proposals": self.curator_proposals,
                "applied": self.curator_applied,
                "failed": self.curator_failed,
            },
        }

    def integrity_report(self) -> dict[str, Any]:
        return {
            "effectUnknown": sum(self.effect_unknown.values()),
            "effectUnknownByTool": dict(sorted(self.effect_unknown.items())),
            "leaseLost": self.lease_lost,
            "checkpointWriteFailures": sum(self.checkpoint_write_failures.values()),
            "checkpointWriteFailuresByKind": dict(sorted(self.checkpoint_write_failures.items())),
            "checkpointWriteP95Ms": _pct(list(self.checkpoint_write_ms), 0.95),
            "eventSeqRetries": self.event_seq_retries,
            "eventSeqCollisions": self.event_seq_collisions,
            "toolBatchOrderingViolations": self.tool_batch_ordering_violations,
            "skillEnabledWithoutEval": self.skill_enabled_without_eval,
            "hardlineBlocked": sum(self.hardline_blocked.values()),
            "hardlineBlockedByPattern": dict(sorted(self.hardline_blocked.items())),
        }

    def file_checkpoint_report(self) -> dict[str, Any]:
        total = self.file_checkpoint_created + self.file_checkpoint_failed
        return {
            "created": self.file_checkpoint_created,
            "failed": self.file_checkpoint_failed,
            "restored": self.file_checkpoint_restored,
            "pruned": self.file_checkpoint_pruned,
            "samples": total,
            "failureRate": _ratio(self.file_checkpoint_failed, total),
            "bytes": {
                "samples": len(self.file_checkpoint_bytes),
                "p50": _pct(list(self.file_checkpoint_bytes), 0.50),
                "p95": _pct(list(self.file_checkpoint_bytes), 0.95),
            },
        }

    def delegation_report(self) -> dict[str, Any]:
        total = self.delegation_started
        return {
            "started": self.delegation_started,
            "completed": self.delegation_completed,
            "failed": self.delegation_failed,
            "repairs": dict(sorted(self.delegation_repairs.items())),
            "worktrees": self.delegation_worktrees,
            "steerChars": self.delegation_steer_chars,
            "completionRate": _ratio(self.delegation_completed, total),
        }


def record_metrics(metrics: Any, hook: str, event: Any) -> None:
    """Map the W8 hooks onto stable Prometheus names.

    Labels are drawn only from the closed vocabularies in the plan. A missing
    or unexpected value becomes `unknown`, never a user-supplied string.
    """
    attrs = dict(getattr(event, "attributes", None) or {})
    provider = str(getattr(event, "provider", None) or attrs.get("provider") or "unknown")

    def label(name: str, default: str = "unknown") -> str:
        value = attrs.get(name)
        return str(value) if value not in (None, "") else default

    if hook == "onModelAttempt":
        outcome = label("outcome")
        metrics.inc_counter(
            "eclipse_model_attempts_total", labels={"provider": provider, "outcome": outcome},
            help_text="Physical model attempts by outcome",
        )
        duration = attrs.get("latencyMs")
        if isinstance(duration, (int, float)) and duration >= 0:
            metrics.observe_histogram(
                "eclipse_model_attempt_duration_ms", float(duration), labels={"provider": provider},
                help_text="Model attempt latency",
            )
    elif hook == "onModelFirstToken":
        value = attrs.get("ttftMs")
        if isinstance(value, (int, float)) and value >= 0:
            metrics.observe_histogram(
                "eclipse_model_ttft_ms", float(value), labels={"provider": provider},
                help_text="Time to first token",
            )
    elif hook == "onModelFallback":
        metrics.inc_counter("eclipse_model_fallbacks_total", help_text="Runs completed on a fallback candidate")
    elif hook == "onContextPressure":
        ratio = attrs.get("usageRatio")
        if isinstance(ratio, (int, float)) and ratio >= 0:
            metrics.observe_histogram(
                "eclipse_context_usage_ratio", float(ratio),
                help_text="Measured context usage as a share of the window",
            )
        if attrs.get("overflow") or attrs.get("exhausted"):
            metrics.inc_counter(
                "eclipse_context_overflow_total", labels={"recovered": str(bool(attrs.get("recovered"))).lower()},
                help_text="Context pressure that refused or recovered a call",
            )
    elif hook == "onContextCompaction":
        stage = label("stage", "none")
        outcome = "ok" if attrs.get("ok") else "failed"
        metrics.inc_counter(
            "eclipse_context_compactions_total", labels={"stage": stage, "outcome": outcome},
            help_text="Context compression ladder outcomes",
        )
    elif hook == "onToolBatch":
        if attrs.get("planOnly"):
            metrics.inc_counter("eclipse_tool_batch_plans_total", help_text="Shadow tool batch plans")
        else:
            metrics.inc_counter("eclipse_tool_batches_total", help_text="Executed tool batches")
            size = attrs.get("calls")
            if isinstance(size, (int, float)) and size >= 0:
                metrics.observe_histogram("eclipse_tool_batch_size", float(size), help_text="Calls per batch")
            violations = attrs.get("orderingViolations")
            if isinstance(violations, (int, float)) and violations > 0:
                metrics.inc_counter(
                    "eclipse_tool_batch_ordering_violations_total", amount=violations,
                    help_text="Tool results returned out of order (must stay zero)",
                )
    elif hook == "onToolGuardrail":
        metrics.inc_counter(
            "eclipse_tool_guardrail_total",
            labels={"rule": label("rule"), "action": label("action")},
            help_text="Tool loop guardrail decisions",
        )
    elif hook == "onGoalCreated":
        metrics.inc_counter("eclipse_goals_total", help_text="Goals created")
    elif hook == "onGoalVerdict":
        metrics.inc_counter(
            "eclipse_goal_verdicts_total", labels={"verdict": label("verdict")},
            help_text="Goal verdicts by kind",
        )
    elif hook == "onSkillEvaluation":
        outcome = "passed" if attrs.get("ok") else ("needs_review" if attrs.get("status") == "needs_review" else "failed")
        metrics.inc_counter(
            "eclipse_skill_exec_eval_total", labels={"outcome": outcome},
            help_text="Behavioural skill-evaluation results",
        )
    elif hook == "onCuratorRun":
        mode = label("mode", "dry_run")
        outcome = "failed" if attrs.get("ok") is False else "completed"
        metrics.inc_counter(
            "eclipse_curator_runs_total", labels={"mode": mode, "outcome": outcome},
            help_text="Skill curator runs by mode and outcome",
        )
    elif hook == "onIntegrityEvent":
        kind = label("kind")
        if kind == "effect_unknown":
            metrics.inc_counter(
                "eclipse_effect_unknown_total", labels={"tool": label("tool")},
                help_text="Effect outcomes that could not be proven (must stay zero)",
            )
        elif kind == "lease_lost":
            metrics.inc_counter("eclipse_lease_lost_total", help_text="Runs stopped because the lease was lost")
        elif kind == "checkpoint_write_failed":
            metrics.inc_counter(
                "eclipse_checkpoint_write_failures_total", labels={"kind": label("checkpoint", "boundary")},
                help_text="Durable checkpoint boundary failures",
            )
        elif kind == "checkpoint_write":
            duration = attrs.get("durationMs")
            if isinstance(duration, (int, float)) and duration >= 0:
                metrics.observe_histogram(
                    "eclipse_checkpoint_write_ms", float(duration),
                    help_text="Durable checkpoint boundary latency",
                )
        elif kind == "event_seq_retry":
            metrics.inc_counter("eclipse_event_seq_retries_total", help_text="Event sequence allocation retries")
        elif kind == "event_seq_collision":
            metrics.inc_counter("eclipse_event_seq_collisions_total", help_text="Unresolved event sequence collisions")
        elif kind == "hardline_blocked":
            metrics.inc_counter(
                "eclipse_hardline_blocked_total", labels={"pattern": label("pattern")},
                help_text="Commands denied by the always-on hardline (security signal)",
            )
        elif kind == "skill_enabled_without_eval":
            metrics.inc_counter(
                "eclipse_skill_enabled_without_eval_total",
                help_text="Skills enabled without a passing behavioural evaluation (must stay zero)",
            )
    elif hook == "onFileCheckpoint":
        event_name = label("op", "created")
        metrics.inc_counter(
            "eclipse_file_checkpoint_total", labels={"event": event_name},
            help_text="File checkpoint store operations",
        )
        if event_name == "failed":
            metrics.inc_counter(
                "eclipse_file_checkpoint_failures_total", labels={"reason": label("reason")},
                help_text="File checkpoint failures",
            )
        size = attrs.get("bytes")
        if isinstance(size, (int, float)) and size >= 0:
            metrics.observe_histogram(
                "eclipse_file_checkpoint_bytes", float(size),
                help_text="Bytes captured per file checkpoint",
            )
    elif hook == "onDelegation":
        event_name = label("op", "started")
        metrics.inc_counter(
            "eclipse_delegations_total", labels={"event": event_name},
            help_text="Async delegation lifecycle",
        )
        if str(attrs.get("eventType") or "").startswith("delegation.worktree"):
            metrics.inc_counter("eclipse_delegation_worktrees_total", help_text="Delegation worktrees allocated")


__all__ = ["SignalAggregates", "capabilities", "record_metrics"]
