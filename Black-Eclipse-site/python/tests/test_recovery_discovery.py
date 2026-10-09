"""Capability discovery — ranked index + purely-advisory acquisition plan."""

from __future__ import annotations

from harness.recovery.discovery import (
    CapabilityDescriptor,
    CapabilityIndex,
    acquisition_plan,
)


def _index() -> CapabilityIndex:
    return CapabilityIndex([
        lambda: [
            CapabilityDescriptor(id="finance_metrics", kind="tool",
                                 description="compute financial metrics and ratios",
                                 available=True, provenance="native"),
            CapabilityDescriptor(id="scrape_web", kind="tool",
                                 description="scrape and extract web pages",
                                 available=False, provenance="native"),
        ],
        lambda: [
            CapabilityDescriptor(id="valuation", kind="skill",
                                 description="discounted cash flow valuation",
                                 available=True, provenance="skill"),
        ],
    ])


def test_search_ranks_by_id_then_description():
    matches = _index().search("financial metrics")
    assert matches
    assert matches[0].descriptor.id == "finance_metrics"


def test_search_filters_by_kind_and_availability():
    index = _index()
    assert all(m.descriptor.kind == "tool" for m in index.search("scrape", kind="tool"))
    assert index.search("scrape", available_only=True) == []
    assert index.search("scrape", available_only=False)


def test_no_capability_when_unrelated():
    assert _index().search("quantum teleportation") == []


def test_plan_uses_an_available_capability():
    plan = acquisition_plan("financial metrics", _index())
    assert plan.resolved_by == "finance_metrics"
    assert plan.steps[0].action == "use"
    assert plan.to_dict()["requiresApproval"] is False


def test_plan_offers_approval_gated_routes_when_missing():
    plan = acquisition_plan("orbital mechanic simulation", _index())
    assert plan.resolved_by is None
    assert plan.to_dict()["requiresApproval"] is True
    assert {s.action for s in plan.steps} >= {"install", "build", "alternative"}


def test_plan_enables_an_unavailable_capability_first():
    plan = acquisition_plan("scrape web", _index())
    assert plan.steps[0].action == "enable"
    assert plan.steps[0].requires_approval is True
