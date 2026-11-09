"""Pure Skills Library query semantics (filter/sort/page)."""

from __future__ import annotations

from harness.skills.listing import filter_summaries, page_summaries, sort_summaries


SKILLS = [
    {
        "id": "finance.market-data",
        "name": "Market data",
        "description": "Quotes for an instrument",
        "category": "finance",
        "status": "enabled",
        "riskLevel": "low",
        "tags": ["quotes", "ohlcv"],
        "updatedAt": "2026-11-01T00:00:00",
    },
    {
        "id": "system.report",
        "name": "Report",
        "description": "Write a source-cited report",
        "category": "system",
        "status": "draft",
        "riskLevel": "high",
        "tags": ["report"],
        "updatedAt": "2026-11-03T00:00:00",
    },
    {
        "id": "research.deep",
        "name": "Deep research",
        "description": "Multi-step research plan",
        "category": "research",
        "status": "enabled",
        "riskLevel": "critical",
        "tags": ["research", "plan"],
        "updatedAt": None,
    },
]


def test_filter_by_each_facet_and_all_is_noop():
    assert len(filter_summaries(SKILLS, category="all", status="all", risk="all")) == 3
    assert [s["id"] for s in filter_summaries(SKILLS, category="finance")] == [
        "finance.market-data"
    ]
    assert [s["id"] for s in filter_summaries(SKILLS, status="draft")] == ["system.report"]
    assert [s["id"] for s in filter_summaries(SKILLS, risk="critical")] == [
        "research.deep"
    ]


def test_search_requires_every_term_and_searches_tags():
    assert [s["id"] for s in filter_summaries(SKILLS, q="source cited")] == [
        "system.report"
    ]
    assert [s["id"] for s in filter_summaries(SKILLS, q="ohlcv")] == [
        "finance.market-data"
    ]
    assert filter_summaries(SKILLS, q="no such thing") == []


def test_sort_orders_are_deterministic():
    assert [s["id"] for s in sort_summaries(SKILLS, "name")] == [
        "research.deep",
        "finance.market-data",
        "system.report",
    ]
    assert [s["id"] for s in sort_summaries(SKILLS, "risk")] == [
        "research.deep",
        "system.report",
        "finance.market-data",
    ]
    assert [s["id"] for s in sort_summaries(SKILLS, "updated")] == [
        "system.report",
        "finance.market-data",
        "research.deep",
    ]


def test_unknown_sort_falls_back_to_name():
    assert sort_summaries(SKILLS, "recent") == sort_summaries(SKILLS, "name")


def test_page_reports_exact_envelope_and_clamps_offset():
    page = page_summaries(SKILLS, limit=2, offset=1)
    assert [s["id"] for s in page["skills"]] == ["system.report", "research.deep"]
    assert page["total"] == 3
    assert page["offset"] == 1
    assert page["limit"] == 2
    assert page["hasMore"] is False

    beyond = page_summaries(SKILLS, limit=2, offset=99)
    assert beyond["skills"] == []
    assert beyond["offset"] == 99
    assert beyond["hasMore"] is False


def test_no_limit_returns_everything():
    page = page_summaries(SKILLS, limit=None)
    assert len(page["skills"]) == 3
    assert page["hasMore"] is False


def test_limit_is_bounded():
    page = page_summaries(SKILLS, limit=10_000)
    assert page["limit"] == 1000
