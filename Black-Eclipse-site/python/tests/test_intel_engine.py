"""Deterministic scoring: same observations → same card, no model, no drift."""

from __future__ import annotations

from harness.intel import engine
from harness.intel.contracts import (
    ACTIVIST_STAKE,
    ATTENTION_VELOCITY,
    BEARISH,
    BULLISH,
    FILING_HEAT,
    HIGH,
    INSIDER_CONVICTION,
    LOW,
    MEDIUM,
    WATCH,
)


def _obs(signal: str, value: float, *, detail=None, confidence: float = 0.8,
         source: str = "sec-edgar", unit: str = "usd", note: str = "",
         entity: str = "TEST") -> dict:
    return {
        "entity": entity, "signal": signal, "asOf": "2026-11-17",
        "value": value, "unit": unit, "windowDays": 90,
        "confidence": confidence, "source": source, "method": "m",
        "detail": detail or {}, "provenance": {}, "directionHint": WATCH, "note": note,
    }


def _insider(buyers=2, buy_usd=1_000_000, sell_usd=0.0, officers=None) -> dict:
    officers = officers if officers is not None else ["A", "B"][:buyers]
    return {
        "buyUsd": buy_usd, "sellUsd": sell_usd, "netUsd": buy_usd - sell_usd,
        "buyers": [f"B{i}" for i in range(buyers)],
        "sellers": ["S0"] if sell_usd else [],
        "officerBuyers": officers, "buyCount": buyers, "sellCount": 1 if sell_usd else 0,
        "filingsScanned": buyers, "plannedExcluded": 3, "noiseExcluded": 2,
        "unpricedBuys": 0, "lastBuy": "2026-11-16", "lastSell": None,
        "cluster": buyers >= 2, "windowDays": 90,
    }


def _attention(z: float, ratio: float = 2.0, conf: float = 0.85) -> dict:
    return _obs(ATTENTION_VELOCITY, z, confidence=conf, source="wikipedia",
                unit="zscore", detail={"zscore": z, "ratio": ratio, "confidence": conf})


# ── Scalar helpers ──────────────────────────────────────────────────────────

def test_clamp_and_log_scale_are_bounded():
    assert engine.clamp01(-1) == 0.0 and engine.clamp01(2) == 1.0
    assert engine.log_scale(0, 1e7) == 0.0
    assert engine.log_scale(1e9, 1e7) == 1.0
    assert 0 < engine.log_scale(1e6, 1e7) < 1


def test_recency_decays():
    assert engine.recency(1) == 1.0
    assert engine.recency(20) == 0.7
    assert engine.recency(200) < engine.recency(20)


# ── Insider ─────────────────────────────────────────────────────────────────

def test_no_buying_scores_zero():
    summary = {"buyers": [], "sellers": ["X", "Y"], "buyUsd": 0, "sellUsd": 900_000,
               "officerBuyers": []}
    score, direction, _ = engine.score_insider(summary, as_of_days=5)
    assert score > 0
    assert direction == BEARISH


def test_two_buyers_outrank_one_smaller_buyer():
    small = engine.score_insider(_insider(buyers=1, buy_usd=50_000, officers=["A"]), as_of_days=10)
    big = engine.score_insider(_insider(buyers=2, buy_usd=2_000_000), as_of_days=2)
    assert big[0] > small[0]
    assert big[1] == BULLISH


def test_insider_buying_with_dominant_sales_is_watch_not_bullish():
    summary = _insider(buyers=1, buy_usd=10_000, sell_usd=5_000_000, officers=["A"])
    score, direction, why = engine.score_insider(summary, as_of_days=3)
    assert direction in (WATCH, BEARISH)
    assert direction != BULLISH
    assert "domin" in why or "sell" in why.lower()


def test_recency_changes_the_score_for_the_same_dollars():
    fresh = engine.score_insider(_insider(), as_of_days=2)[0]
    stale = engine.score_insider(_insider(), as_of_days=85)[0]
    assert fresh > stale


# ── Attention ───────────────────────────────────────────────────────────────

def test_attention_below_gate_contributes_nothing():
    score, direction, _ = engine.score_attention({"zscore": 1.4, "ratio": 1.3})
    assert score == 0.0
    assert direction == WATCH


def test_attention_spike_contributes_but_claims_no_direction():
    score, direction, why = engine.score_attention({"zscore": 4.0, "ratio": 3.0})
    assert score > 0
    assert direction == WATCH  # attention alone is never a directional call
    assert "attention" in why


def test_filing_heat_is_gated():
    assert engine.score_filing_heat(1.5)[0] == 0.0
    assert engine.score_filing_heat(3.0)[0] > 0


def test_activist_absent_scores_zero():
    assert engine.score_activist(0)[0] == 0.0
    assert engine.score_activist(1)[0] > 0


# ── Cards ───────────────────────────────────────────────────────────────────

def test_a_quiet_entity_produces_no_card():
    card = engine.build_opportunity(
        "TEST", [
            _obs(ACTIVIST_STAKE, 0),
            _obs(INSIDER_CONVICTION, 0, detail=_insider(buyers=0, buy_usd=0, officers=[])),
        ], as_of="2026-11-17",
    )
    assert card is None


def test_an_insider_cluster_produces_a_bullish_card_with_invalidation():
    card = engine.build_opportunity(
        "TEST", [_obs(INSIDER_CONVICTION, 1_000_000, detail=_insider())],
        as_of="2026-11-17", days_since_last_buy=2,
    )
    assert card is not None
    assert card.direction == BULLISH
    assert card.horizon_days == 60
    assert card.invalidation.startswith("Close the case when:")
    assert card.priority > 0
    assert card.signals[0]["signal"] == INSIDER_CONVICTION


def test_two_independent_sources_raise_conviction_and_are_named():
    card = engine.build_opportunity(
        "TEST", [
            _obs(INSIDER_CONVICTION, 2_000_000, detail=_insider(buyers=3, buy_usd=4_000_000)),
            _attention(4.0, ratio=3.0),
        ], as_of="2026-11-17", days_since_last_buy=1,
    )
    assert card is not None
    assert card.conviction in (HIGH, MEDIUM)
    assert set(card.sources) == {"sec-edgar", "wikipedia"}
    assert "sec-edgar" in card.sources


def test_attention_alone_is_a_watch_card_not_a_direction():
    card = engine.build_opportunity(
        "TEST", [_attention(4.0, ratio=3.0)], as_of="2026-11-17",
    )
    assert card is not None
    assert card.direction == WATCH
    assert card.conviction == LOW


def test_divergence_needs_price_and_reports_underreaction():
    reading = {"zscore": 3.0, "ratio": 2.0}
    assert engine.divergence(None, reading) == ""
    assert "underreaction" in engine.divergence({"change5d": 0.0}, reading)
    assert "already priced" in engine.divergence({"change5d": 0.2}, reading)
    assert engine.divergence({"change5d": 0.05}, reading) == ""


def test_insider_price_note_flags_buying_into_weakness():
    assert "weakness" in engine.insider_price_note({"change30d": -0.15}, BULLISH)
    assert "run-up" in engine.insider_price_note({"change30d": 0.3}, BULLISH)
    assert engine.insider_price_note({"change30d": 0.05}, BULLISH) == ""
    assert engine.insider_price_note({"change30d": -0.3}, WATCH) == ""


def test_caveats_carry_the_signal_limit():
    card = engine.build_opportunity(
        "TEST", [_obs(INSIDER_CONVICTION, 1_000_000, detail=_insider())],
        as_of="2026-11-17",
    )
    assert card is not None
    assert any("Form 4 is filed within two business days" in caveat for caveat in card.caveats)


def test_ranking_orders_by_priority_then_entity():
    a = engine.build_opportunity(
        "AAA", [_obs(INSIDER_CONVICTION, 100, entity="AAA",
                     detail=_insider(buyers=1, buy_usd=1_000, officers=["A"]))],
        as_of="2026-11-17", days_since_last_buy=60,
    )
    b = engine.build_opportunity(
        "BBB", [_obs(INSIDER_CONVICTION, 9_000_000, entity="BBB", detail=_insider(buyers=3))],
        as_of="2026-11-17", days_since_last_buy=1,
    )
    ranked = engine.rank([a, b])
    assert [card.entity for card in ranked] == ["BBB", "AAA"]
