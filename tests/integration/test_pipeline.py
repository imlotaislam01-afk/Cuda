from brain.context import Candle, MarketContextBuilder, Trade
from brain.confluence import ConfluenceEngine
from brain.oi import OIEngine, OISnapshot
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate


def make_context(direction="LONG", quality="OK"):
    if direction == "LONG":
        values = [(100, 95, 98), (105, 99, 103), (101, 90, 95), (103, 94, 100), (110, 99, 108)]
        side = "BUY"
    else:
        values = [(105, 100, 103), (101, 96, 98), (110, 99, 104), (103, 94, 97), (90, 80, 82)]
        side = "SELL"
    candles = tuple(
        Candle(float(index + 1), float(close), float(high), float(low), float(close), 100)
        for index, (high, low, close) in enumerate(values)
    )
    trades = tuple(
        Trade(str(index), float(index + 1), float(close), 10, side)
        for index, (_, _, close) in enumerate(values)
    )
    return (
        MarketContextBuilder("BTCUSDT", values[-1][2], "5m")
        .set_exchange("BYBIT")
        .set_market_data(candles=candles, trades=trades, volatility=1)
        .set_event_times(event_time=5, received_time=5, calculation_time=5)
        .set_data_quality(quality)
        .build(allow_incomplete=True)
    )


def test_pipeline_returns_actionable_long():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20
    result = pipeline.run(make_context("LONG"))
    assert result.decision.action == "LONG"
    assert result.decision.levels.stop_loss < result.decision.levels.entry
    assert result.intent is not None


def test_pipeline_returns_actionable_short():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20
    result = pipeline.run(make_context("SHORT"))
    assert result.decision.action == "SHORT"
    assert result.decision.levels.stop_loss > result.decision.levels.entry
    assert result.intent is not None


def test_pipeline_blocks_bad_data():
    result = ApexBrainPipeline().run(make_context("LONG", "DATA_STALE"))
    assert result.decision.action == "WAIT"
    assert result.intent is None


def test_pipeline_conflict_produces_no_trade():
    pipeline = ApexBrainPipeline(RiskGate(RiskConfig(minimum_confidence=20)))
    pipeline.decision.minimum_confidence = 20

    bullish = [
        {"event_time": index + 1, "open": close, "high": high, "low": low, "close": close}
        for index, (high, low, close) in enumerate([(10, 5, 8), (12, 6, 11), (9, 4, 7), (13, 7, 12), (11, 6, 10), (15, 8, 14), (14, 9, 13), (16, 10, 16)])
    ]
    bearish = [
        {"event_time": index + 1, "open": high, "high": high, "low": low - 1, "close": low}
        for index, (high, low) in enumerate([(15, 10), (13, 8), (14, 9), (11, 6), (12, 7), (9, 4), (3, 2)])
    ]
    conflicting = make_context("LONG")
    conflicting.event_time = 8
    conflicting.calculation_time = 8
    conflicting.metadata["candles_by_timeframe"] = {"5m": bullish, "1h": bearish}
    result = pipeline.run(conflicting)
    assert result.context.mtf.conflict is True
    assert result.decision.action == "WAIT"