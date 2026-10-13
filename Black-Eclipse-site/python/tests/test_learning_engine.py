"""Deterministic learning curriculum & skill-graph engine tests."""

from __future__ import annotations

from harness.research.learning import (
    LearningResource,
    SkillNode,
    build_curriculum,
    detect_cycles,
    rank_resources,
    reject_weak,
    resources_from_specs,
    topological_order,
    validate_curriculum,
)
from harness.research.web_sources import classify_source_type
from harness.research.web_contracts import SourceType, ResearchIntent
from harness.research.web_intent import classify_intent


def _res(url, title, st, **kw):
    return {"url": url, "title": title, "sourceType": st, **kw}


def test_learning_source_classification():
    assert classify_source_type("youtube.com") == SourceType.VIDEO
    assert classify_source_type("github.com") == SourceType.REPOSITORY
    assert classify_source_type("coursera.org") == SourceType.COURSE
    assert classify_source_type("https://docs.python.org/3/") == SourceType.DOCUMENTATION
    assert classify_source_type("arxiv.org") == SourceType.ACADEMIC
    assert classify_source_type("ted.com") == SourceType.VIDEO


def test_learning_intent_classification():
    r = classify_intent("I want to learn quantitative trading from scratch")
    assert r.intent == ResearchIntent.LEARNING
    assert SourceType.VIDEO in r.sourceTypes
    assert SourceType.COURSE in r.sourceTypes
    # A research-paper question is still academic, not learning.
    assert classify_intent("find a research paper on machine learning").intent == ResearchIntent.ACADEMIC_RESEARCH


def test_build_curriculum_is_a_valid_dag():
    resources = resources_from_specs([
        _res("https://www.youtube.com/playlist?list=a", "Quant trading full course", "video",
             durationSeconds=7200, description="python backtesting statistics risk"),
        _res("https://docs.python.org/3/", "Python reference", "documentation", description="python language"),
        _res("https://github.com/example/backtrader", "backtrader", "repository", description="backtesting python"),
    ])
    graph = build_curriculum(
        goal="quantitative trading",
        skill_specs=[
            {"id": "python", "name": "Python", "objectives": ["write python"], "milestone": "basics", "assessment": "script"},
            {"id": "stats", "name": "Statistics", "objectives": ["statistics"], "prerequisites": ["python"]},
            {"id": "backtest", "name": "Backtesting", "objectives": ["backtesting python"], "prerequisites": ["stats"]},
        ],
        resources=resources,
        start_level="beginner",
    )
    assert [e.to_dict() for e in graph.edges] == [{"from": "python", "to": "stats"}, {"from": "stats", "to": "backtest"}]
    assert not [i for i in graph.issues if i["severity"] == "error"]
    # Every skill with a relevant resource got one attached.
    assert all(n.resourceIds for n in graph.nodes)
    assert topological_order(graph.nodes) == ["python", "stats", "backtest"]


def test_cycle_detection_and_validation():
    nodes = [
        SkillNode(id="a", name="A", prerequisites=["b"]),
        SkillNode(id="b", name="B", prerequisites=["a"]),
    ]
    assert detect_cycles(nodes)  # non-empty => a cycle exists
    graph = build_curriculum(goal="x", skill_specs=[
        {"id": "a", "name": "A", "prerequisites": ["b"]},
        {"id": "b", "name": "B", "prerequisites": ["a"]},
    ], resources=[])
    assert any(i["code"] == "circular_dependency" for i in graph.issues)


def test_missing_prerequisite_is_an_error():
    graph = build_curriculum(goal="x", skill_specs=[{"id": "a", "name": "A", "prerequisites": ["nope"]}], resources=[])
    assert any(i["code"] == "missing_prerequisite" and i["severity"] == "error" for i in graph.issues)


def test_milestone_without_assessment_warns():
    graph = build_curriculum(goal="x", skill_specs=[{"id": "a", "name": "A", "milestone": "done"}], resources=[])
    assert any(i["code"] == "milestone_without_assessment" for i in graph.issues)


def test_empty_skills_yields_a_foundation_skill():
    graph = build_curriculum(goal="Rust", skill_specs=[], resources=[])
    assert len(graph.nodes) == 1 and graph.nodes[0].id == "foundations"
    # A skill with no resources is an explicit, honest gap.
    assert any(i["code"] == "skill_without_resources" for i in graph.issues)


def test_prerequisite_names_are_resolved_to_ids():
    graph = build_curriculum(
        goal="x",
        skill_specs=[
            {"name": "Python"},
            {"name": "Stats", "prerequisites": ["Python"]},
        ],
        resources=[],
    )
    ids = {n.id for n in graph.nodes}
    assert any(e.target for e in graph.edges)
    assert all(e.source in ids and e.target in ids for e in graph.edges)


def test_ranking_is_explainable_and_prefers_authority():
    resources = [
        LearningResource(resourceId="vid", title="Quant trading", url="https://youtube.com/x",
                         sourceType=SourceType.VIDEO, description="quant trading"),
        LearningResource(resourceId="doc", title="Quant trading", url="https://docs.x/y",
                         sourceType=SourceType.DOCUMENTATION, description="quant trading"),
    ]
    ranked = rank_resources(resources, "quant trading")
    assert ranked[0]["resourceId"] == "doc"  # documentation outranks video in the learning table
    assert set(ranked[0]["components"]) == {"authority", "relevance", "depth", "accessibility", "verification"}
    kept, rejected = reject_weak(ranked, floor=0.99)
    assert kept == [] and len(rejected) == 2


def test_resources_are_deduplicated_by_url():
    specs = [
        _res("https://youtube.com/x", "A", "video"),
        _res("https://youtube.com/x", "A duplicate", "video"),
    ]
    assert len(resources_from_specs(specs)) == 1
