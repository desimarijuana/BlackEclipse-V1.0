"""A market refusal must name the WHOLE trail of providers it tried.

The observed failure: a daily history came back as "AUTHENTICATION_FAILED, no
POLYGON_API_KEY" - the LAST provider's error - while the more useful one (a
keyless route that had no data) was swallowed. The agent then went on to scrape
a page, because the refusal never said which routes had already been tried.
"""

from __future__ import annotations

from harness.market.errors import (
    AUTHENTICATION_FAILED,
    DATA_NOT_AVAILABLE,
    MarketError,
)
from harness.market.gateway import MarketDataGateway
from harness.market.tools import _finish


class _Ctx:
    """The smallest context the refusal path needs."""

    def __init__(self) -> None:
        self.collected: list = []
        self.persisted: list = []


def _finish_with(error: MarketError) -> str:
    text, _data = _finish(_Ctx(), error, "historical")
    return text


def test_the_refusal_names_every_provider_it_tried():
    error = MarketError(
        AUTHENTICATION_FAILED,
        "no POLYGON_API_KEY",
        provider="polygon",
        detail={
            "providers": [
                {"provider": "yahoo", "code": "DATA_NOT_AVAILABLE", "message": "no history for AAPL"},
                {"provider": "stooq", "code": "DATA_NOT_AVAILABLE", "message": "no history for AAPL"},
                {"provider": "polygon", "code": "AUTHENTICATION_FAILED", "message": "no POLYGON_API_KEY"},
            ]
        },
    )
    text = _finish_with(error)
    assert "Providers tried:" in text
    assert "yahoo" in text
    assert "stooq" in text
    assert "polygon" in text


def test_a_provider_that_needs_a_missing_credential_is_never_offered_again():
    error = MarketError(
        AUTHENTICATION_FAILED,
        "no POLYGON_API_KEY",
        provider="polygon",
        detail={"providers": [{"provider": "polygon", "code": "AUTHENTICATION_FAILED", "message": "no key"}]},
    )
    text = _finish_with(error)
    assert "do not try it again" in text
    # The correction is still named: the refusal teaches the next route.
    assert "scraper_run" in text


def test_a_refusal_without_a_trail_still_teaches_the_correction():
    text = _finish_with(MarketError(DATA_NOT_AVAILABLE, "no provider returned data"))
    assert "scraper_run" in text
    assert "Providers tried:" not in text
