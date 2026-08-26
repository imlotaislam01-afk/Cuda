from brain.context import MarketContextBuilder
from brain.confluence import ConfluenceEngine
from brain.oi import OIEngine, OISnapshot
from brain.pipeline import ApexBrainPipeline
from market.indicators import ATRCalculator, VWAPCalculator


def candles():
    return [
        {"event_time": 1, "open": 10, "high": 13, "low": 9, "close": 12, "volume": 2},
        {"event_time": 2, "open": 12, "high": 14, "low": 11, "close": 13, "volume": 3},
        {"event_time": 3, "open": 13, "high": 15, "low": 12, "close": 14, "volume": 5},
    ]


def test_vwap_is_volume_weighted_and_cutoff_aware():
    assert VWAPCalculator.calculate(candles()) == 12.9
    assert round(VWAPCalculator.calculate(candles(), as_of=2), 6) == 12.133333
    assert VWAPCalculator.calculate([{**candles()[0], "volume": 0}]) is None
    assert VWAPCalculator.calculate([]) is None


def test_atr_is_deterministic_and_requires_history():
    assert ATRCalculator(period=2).calculate(candles()) == 3.0
    assert ATRCalculator(period=3).calculate(candles()) is None
    assert ATRCalculator(period=2).calculate(candles(), as_of=2) is None


def test_pipeline_feeds_successive_oi_into_canonical_engine():
    context = (
        MarketContextBuilder("BTCUSDT", 100)
        .set_price(100, change_pct=1, volume_ratio=2)
        .set_confluence(ConfluenceEngine().analyze([]))
        .set_oi(OIEngine().analyze(OISnapshot(1, 5)))
        .set_market_data(open_interest=105, oi_change=5)
        .build()
    )
    assert ApexBrainPipeline().run(context).context.oi.oi_change_pct == 5