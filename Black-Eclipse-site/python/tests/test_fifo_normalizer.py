"""FIFO round-trip normalizer: deterministic synthetic deals from executions."""

from __future__ import annotations

from harness.trade.adapters.fifo import Execution, normalize_fifo


def _exec(id_, side, qty, price, t, fee=0.0, symbol="AAPL"):
    return Execution(id=id_, symbol=symbol, side=side, qty=qty, price=price, time_ms=t, fee=fee)


def _round_trips(deals):
    keys = sorted({d["positionTicket"] for d in deals})
    return {
        key: sorted(
            [d for d in deals if d["positionTicket"] == key],
            key=lambda d: d["dealtAt"],
        )
        for key in keys
    }


def test_single_long_round_trip():
    deals = normalize_fifo([
        _exec("o1", "buy", 10, 100, 1_000),
        _exec("c1", "sell", 10, 110, 2_000, fee=2.0),
    ])
    trips = _round_trips(deals)
    assert len(trips) == 1
    legs = list(trips.values())[0]
    assert [leg["entry"] for leg in legs] == ["in", "out"]
    assert legs[0]["volume"] == 10
    assert legs[0]["price"] == 100
    assert legs[1]["price"] == 110
    assert legs[1]["profit"] == 100
    assert legs[1]["commission"] == -2.0


def test_scale_in_is_closed_fifo_and_aggregated_into_one_exit():
    deals = normalize_fifo([
        _exec("o1", "buy", 5, 100, 1_000),
        _exec("o2", "buy", 5, 102, 1_500),
        _exec("c1", "sell", 10, 110, 2_000),
    ])
    trips = _round_trips(deals)
    assert len(trips) == 1
    legs = list(trips.values())[0]
    assert legs[0]["volume"] == 10
    assert legs[0]["price"] == 101  # weighted FIFO entry
    assert legs[1]["profit"] == 90  # 5×10 + 5×8


def test_partial_close_leaves_the_remainder_open():
    deals = normalize_fifo([
        _exec("o1", "buy", 4, 100, 1_000),
        _exec("c1", "sell", 1, 110, 2_000),
    ])
    trips = _round_trips(deals)
    assert len(trips) == 2  # one closed + one open remainder
    closed = [legs for legs in trips.values() if len(legs) == 2][0]
    still_open = [legs for legs in trips.values() if len(legs) == 1][0]
    assert closed[1]["profit"] == 10
    assert still_open[0]["volume"] == 3
    assert still_open[0]["entry"] == "in"


def test_short_round_trip():
    deals = normalize_fifo([
        _exec("o1", "sell", 2, 100, 1_000),
        _exec("c1", "buy", 2, 95, 2_000),
    ])
    legs = list(_round_trips(deals).values())[0]
    assert legs[0]["side"] == "sell"
    assert legs[1]["side"] == "buy"
    assert legs[1]["profit"] == 10


def test_fees_are_split_across_the_round_trip():
    deals = normalize_fifo([
        _exec("o1", "buy", 2, 100, 1_000, fee=1.0),
        _exec("c1", "sell", 2, 110, 2_000, fee=3.0),
    ])
    legs = list(_round_trips(deals).values())[0]
    assert legs[0]["commission"] == -1.0
    assert legs[1]["commission"] == -3.0


def test_position_flip_closes_then_opens_the_other_way():
    deals = normalize_fifo([
        _exec("o1", "buy", 1, 100, 1_000),
        _exec("x1", "sell", 3, 110, 2_000),
    ])
    trips = _round_trips(deals)
    assert len(trips) == 2  # the long close + the new short remainder
    closed = [legs for legs in trips.values() if len(legs) == 2][0]
    opened = [legs for legs in trips.values() if len(legs) == 1][0]
    assert closed[1]["profit"] == 10
    assert opened[0]["side"] == "sell"
    assert opened[0]["volume"] == 2
