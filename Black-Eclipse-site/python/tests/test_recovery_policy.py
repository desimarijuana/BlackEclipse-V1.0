"""Recovery policy + controller — bounded, deterministic, safety-first (pure)."""

from __future__ import annotations

import random

from harness.recovery.controller import RecoveryAction, RecoveryController
from harness.recovery.policy import (
    RecoveryBudget,
    RecoveryStrategy,
    reject_reason,
    select_strategies,
)
from harness.recovery.taxonomy import FailureKind, normalize_failure


def _failure(code, message="", **kw):
    return normalize_failure(code=code, message=message, **kw)


def test_timeout_offers_retry_first():
    failure = _failure("TOOL_TIMEOUT")
    strategies = [c.strategy for c in select_strategies(failure)]
    assert strategies[0] == RecoveryStrategy.RETRY
    assert RecoveryStrategy.STOP_AND_REPORT in strategies


def test_auth_failure_never_offers_retry_or_provider_substitution():
    failure = _failure("authentication_error", "401 invalid api key", source="provider")
    strategies = [c.strategy for c in select_strategies(failure)]
    assert RecoveryStrategy.RETRY not in strategies
    assert RecoveryStrategy.SUBSTITUTE_PROVIDER not in strategies
    assert RecoveryStrategy.SUSPEND in strategies
    assert reject_reason(failure, RecoveryStrategy.SUBSTITUTE_PROVIDER) is not None


def test_non_retryable_kind_rejects_retry():
    failure = _failure("tool_validation_failed")
    assert reject_reason(failure, RecoveryStrategy.RETRY) is not None
    assert RecoveryStrategy.RETRY not in [c.strategy for c in select_strategies(failure)]


def test_rate_limit_offers_backoff_only_for_rate_limit():
    rate = _failure("rate_limit")
    other = _failure("TOOL_TIMEOUT")
    assert RecoveryStrategy.RATE_LIMIT_BACKOFF in [c.strategy for c in select_strategies(rate)]
    assert RecoveryStrategy.RATE_LIMIT_BACKOFF not in [c.strategy for c in select_strategies(other)]
    assert reject_reason(other, RecoveryStrategy.RATE_LIMIT_BACKOFF) is not None


def test_dependency_repair_requires_approval():
    failure = _failure("missing dependency", message="ModuleNotFoundError: no module named 'x'")
    assert failure.kind == FailureKind.DEPENDENCY
    chosen = select_strategies(failure)[0]
    assert chosen.strategy == RecoveryStrategy.FIX_DEPENDENCY
    assert chosen.requires_approval is True


def test_recurrent_demotes_retry_to_last():
    failure = _failure("TOOL_TIMEOUT")
    strategies = [c.strategy for c in select_strategies(failure, recurrent=True)]
    assert strategies[-1] == RecoveryStrategy.RETRY


def test_controller_recover_for_transient():
    controller = RecoveryController(rng=random.Random(0))
    decision = controller.decide(_failure("TOOL_TIMEOUT"))
    assert decision.action == RecoveryAction.RECOVER
    assert decision.strategy == RecoveryStrategy.RETRY
    assert 0 < decision.backoff_ms <= 30_000


def test_controller_stops_at_attempt_budget():
    controller = RecoveryController(budget=RecoveryBudget(max_attempts=2))
    decision = controller.decide(_failure("TOOL_TIMEOUT"), attempts=2)
    assert decision.action == RecoveryAction.STOP
    assert decision.exhausted is True


def test_controller_stops_at_signature_budget():
    controller = RecoveryController(budget=RecoveryBudget(max_per_signature=1))
    decision = controller.decide(_failure("TOOL_TIMEOUT"), signature_attempts=1)
    assert decision.action == RecoveryAction.STOP
    assert decision.exhausted is True


def test_controller_suspends_on_auth():
    controller = RecoveryController()
    decision = controller.decide(_failure("authentication_error", "401"))
    assert decision.action == RecoveryAction.SUSPEND
    assert decision.requires_approval is True


def test_backoff_is_bounded_and_monotonic_in_base():
    controller = RecoveryController(rng=random.Random(1))
    values = [controller.backoff_ms(n) for n in range(1, 8)]
    assert all(0 <= v <= 30_000 for v in values)
    assert values[-1] >= values[0]
