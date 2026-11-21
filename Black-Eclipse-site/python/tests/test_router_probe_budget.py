"""Router probe budget: one half-open probe per scope, evidence-based recovery."""

from __future__ import annotations

from harness.market.router import ProbeBudget, ProviderHealth, ProviderRouter
from harness.mcp.circuit import CircuitBreaker


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_probe_budget_allows_one_claim_per_cooldown():
    clock = _Clock()
    budget = ProbeBudget(cooldown_s=60, clock=clock)
    assert budget.claim("quote:us", "p") is True
    assert budget.claim("quote:us", "p") is False
    clock.now += 61
    assert budget.claim("quote:us", "p") is True


def test_probe_budget_scopes_are_independent():
    clock = _Clock()
    budget = ProbeBudget(cooldown_s=60, clock=clock)
    assert budget.claim("quote:us", "p") is True
    assert budget.claim("quote:crypto", "p") is True


def test_evidence_elsewhere_expires_with_the_cooldown():
    clock = _Clock()
    budget = ProbeBudget(cooldown_s=60, clock=clock)
    budget.record_success("quote:us", "p")
    assert budget.evidence_elsewhere("quote:crypto", "p") is True
    clock.now += 61
    assert budget.evidence_elsewhere("quote:crypto", "p") is False


def test_evidence_does_not_count_for_the_same_scope():
    budget = ProbeBudget(cooldown_s=60)
    budget.record_success("quote:us", "p")
    assert budget.evidence_elsewhere("quote:us", "p") is False


def test_a_failure_clears_cross_scope_credit():
    budget = ProbeBudget(cooldown_s=60)
    budget.record_success("quote:us", "p")
    budget.record_failure("quote:us", "p")
    assert budget.evidence_elsewhere("quote:crypto", "p") is False


# -- attempt_order -----------------------------------------------------------


class _StubRouter(ProviderRouter):
    def __init__(self):
        super().__init__(providers=[])
        for pid in ("p", "q"):
            self._health[pid] = ProviderHealth(
                provider=pid, breaker=CircuitBreaker(threshold=1, cooldown_s=60))

    def provider_order(self, capability, instrument):
        return ("p", "q")


def _trip(router, pid):
    router._health[pid].breaker.record_failure("boom")


def test_an_open_provider_is_skipped_while_others_are_offered():
    router = _StubRouter()
    _trip(router, "p")
    assert router.attempt_order("quote", None) == ("q",)


def test_cross_scope_evidence_grants_exactly_one_probe():
    router = _StubRouter()
    _trip(router, "p")
    router._probes.record_success("quote:crypto", "p")
    first = router.attempt_order("quote", None)
    assert "p" in first
    # The single probe was spent; the next call must not keep retrying it.
    assert "p" not in router.attempt_order("quote", None)


def test_a_closed_provider_is_always_offered():
    router = _StubRouter()
    assert router.attempt_order("quote", None) == ("p", "q")
