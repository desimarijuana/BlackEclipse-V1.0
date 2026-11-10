"""The research sub-kinds extend quant intent without changing existing routing."""

from __future__ import annotations

from harness.quant_intent import classify_quant_intent, quant_intent_block

_TOOLS = {
    "research_search_papers", "research_get_paper", "research_get_citations",
    "research_extract_method", "research_compare_methods", "research_get_evidence",
    "quant_list_methods", "quant_get_method", "quant_specify_method",
    "quant_reproduce_method", "quant_validate_method", "quant_register_method",
    "quant_build_dossier", "model_catalog", "run_backtest",
}


def test_literature_review():
    intent = classify_quant_intent("find papers on GARCH volatility forecasting")
    assert intent.tier == "standard"
    assert intent.kind == "literature_review"
    block = quant_intent_block(intent, available=_TOOLS)
    assert "research_search_papers" in block
    assert "research_extract_method" in block


def test_method_comparison():
    intent = classify_quant_intent("compare GARCH, EGARCH and GJR-GARCH")
    assert intent.kind == "method_comparison"
    block = quant_intent_block(intent, available=_TOOLS)
    assert "research_compare_methods" in block
    assert "profit probability" in block


def test_method_reproduction_is_deep():
    intent = classify_quant_intent("reproduce the GARCH paper for gold")
    assert intent.tier == "deep"
    assert intent.kind == "method_reproduction"
    block = quant_intent_block(intent, available=_TOOLS)
    assert "quant_reproduce_method" in block
    assert "reproduction" in block.lower()


def test_model_development_from_research():
    intent = classify_quant_intent("develop a research-backed volatility model for gold")
    assert intent.tier == "deep"
    assert intent.kind == "quant_model_development"
    block = quant_intent_block(intent, available=_TOOLS)
    assert "quant_build_dossier" in block


def test_independent_research():
    intent = classify_quant_intent("investigate a research gap in liquidity and volatility")
    assert intent.tier == "deep"
    assert intent.kind == "research_extension"
    block = quant_intent_block(intent, available=_TOOLS)
    assert "research gap" in block.lower()


def test_existing_routes_are_unchanged():
    assert classify_quant_intent("what is the price of gold").tier == "none"
    assert classify_quant_intent("build me a quant model for gold").kind == "model"
    assert classify_quant_intent("what methods can I use to trade gold").kind == "discovery"
    assert classify_quant_intent("place a live trade for gold").kind == "trade"
