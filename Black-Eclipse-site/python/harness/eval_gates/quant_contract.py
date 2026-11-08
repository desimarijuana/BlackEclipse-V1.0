"""Offline deterministic gate for the chat-only quant contract.

This does not call a model. It asserts that the runtime's per-turn protocol still
REQUIRES the behaviour the product depends on: catalog-first reuse, the artifact
line, the gold basis, clarification and validation. A prompt edit that drops one
of these fails the gate before it can reach a live run.
"""

from __future__ import annotations

from ..quant_intent import classify_quant_intent, quant_intent_block

_TOOLS = {
    "analysis_run", "model_catalog", "create_research_plan", "run_backtest",
    "run_walk_forward", "run_robustness_analysis", "python_chart",
    "eclipse_report", "clarify",
}

# (query, expected tier, substrings the protocol must still contain)
CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("forecast gold for tomorrow", "standard", (
        "Artifacts: <comma-separated ids>",
        "Artifacts: none —",
        "spot XAUUSD",
        "GC=F futures",
    )),
    ("build me a quant model for gold", "deep", (
        "call `model_catalog` FIRST",
        "reuse it",
        "ask ONE clarify question",
        "Artifacts:",
    )),
    ("reuse the model from last week", "standard", (
        "model_catalog",
        "reuse a fitting artifact",
    )),
    ("calculate gold's 20-day volatility", "light", (
        "Compute with the tool",
        "show formula",
    )),
    ("what is the price of gold", "none", ()),
)


def run_gate() -> None:
    for query, tier, required in CASES:
        intent = classify_quant_intent(query)
        assert intent.tier == tier, f"{query!r}: expected {tier}, got {intent.tier}"
        block = quant_intent_block(intent, available=_TOOLS)
        if tier == "none":
            assert block == "", f"{query!r}: a lookup got a quant block"
            continue
        for needle in required:
            assert needle in block, f"{query!r}: block lost {needle!r}"
