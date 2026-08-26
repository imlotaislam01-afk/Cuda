import math

import pytest

from brain.context import DataQuality, MarketContextBuilder, OrderBook
from brain.confluence import ConfluenceEngine
from brain.oi import OIEngine, OISnapshot


def complete_builder():
    confluence = ConfluenceEngine().analyze([])
    oi = OIEngine().analyze(OISnapshot(0, 0))
    return MarketContextBuilder("BTCUSDT", 100).set_confluence(confluence).set_oi(oi)


def test_context_rejects_invalid_price_and_crossed_book():
    with pytest.raises(ValueError):
        MarketContextBuilder("BTCUSDT", math.nan)
    with pytest.raises(ValueError):
        OrderBook(bids=((101, 1),), asks=((100, 1),))


def test_context_preserves_explicit_times_and_quality():
    context = (
        complete_builder()
        .set_event_times(event_time=10, received_time=11, calculation_time=12)
        .build()
    )
    assert context.event_time == 10
    assert context.received_time == 11
    assert context.calculation_time == 12
    assert context.data_quality.status == "OK"
    assert DataQuality("DATA_STALE").status == "DATA_STALE"