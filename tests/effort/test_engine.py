import pytest

from brain.intelligence import AbsorptionEngine, AggressionEngine, EffortModel


def candle(event_time, close, volume=10, *, confirmed=True, symbol=None):
    item = {
        "event_time": event_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
        "confirmed": confirmed,
    }
    if symbol is not None:
        item["symbol"] = symbol
    return item


def test_aggression_uses_authoritative_delta_and_is_deterministic():
    candles = [candle(1, 100), candle(2, 101)]
    flow = {"buy_volume": 30, "sell_volume": 10, "delta": 20, "trade_count": 4}

    first = AggressionEngine().analyze(candles, flow, as_of=2, symbol="BTCUSDT")
    second = AggressionEngine().analyze(candles, flow, as_of=2, symbol="BTCUSDT")

    assert first.to_dict() == second.to_dict()
    assert first.direction == "BULLISH"
    assert first.aggressive_volume == 40
    assert first.intensity == 0.5


def test_absorption_requires_multiple_visible_observations():
    candles = [
        candle(1, 100, volume=10),
        candle(2, 100.05, volume=10),
        candle(3, 100.10, volume=10),
        candle(4, 100.15, volume=100),
        candle(5, 200, volume=100),
    ]
    flow = {"buy_volume": 80, "sell_volume": 10, "delta": 70, "trade_count": 10}

    result = AbsorptionEngine(max_response_pct=0.001).analyze(candles, flow, as_of=4)

    assert result.detected is True
    assert result.side == "BUY"
    assert result.price_response == pytest.approx(0.0004995005)
    assert result.event_time == 4


def test_future_forming_and_other_symbol_data_cannot_change_result():
    base = [
        candle(1, 100, volume=10, symbol="BTCUSDT"),
        candle(2, 100, volume=10, symbol="BTCUSDT"),
        candle(3, 100.05, volume=100, symbol="BTCUSDT"),
    ]
    extra = [
        candle(4, 200, volume=1000, symbol="ETHUSDT"),
        candle(5, 300, volume=1000, confirmed=False, symbol="BTCUSDT"),
    ]
    flow = {"buy_volume": 80, "sell_volume": 10, "delta": 70, "trade_count": 10}
    engine = AbsorptionEngine()

    first = engine.analyze(base, flow, as_of=3, symbol="BTCUSDT")
    second = engine.analyze(base + extra, flow, as_of=3, symbol="BTCUSDT")

    assert second.to_dict() == first.to_dict()


def test_empty_effort_input_fails_closed():
    result = AbsorptionEngine().analyze([], {}, as_of=10, symbol="BTCUSDT")

    assert result.detected is False
    assert result.side == "NONE"
    assert result.data_quality == "DATA_INCOMPLETE"


def test_effort_model_reports_absorbed_buying_without_trade_decision():
    result = EffortModel().analyze(
        [candle(1, 100), candle(2, 100.01, volume=100)],
        {"buy_volume": 80, "sell_volume": 10, "delta": 70, "aggression": "strong"},
        as_of=2,
        symbol="BTCUSDT",
    )

    assert result.effort_state == "ABSORBED_BUYING"
    assert result.path_of_least_resistance == "BULLISH"
    assert not hasattr(result, "decision")


def test_effort_model_excludes_future_and_forming_observations():
    candles = [
        candle(1, 100, symbol="BTCUSDT"),
        candle(2, 100.01, symbol="BTCUSDT"),
        candle(3, 200, confirmed=False, symbol="BTCUSDT"),
        candle(4, 300, symbol="ETHUSDT"),
    ]
    flow = {"buy_volume": 80, "sell_volume": 10, "delta": 70}

    first = EffortModel().analyze(candles, flow, as_of=2, symbol="BTCUSDT")
    second = EffortModel().analyze(candles, flow, as_of=2, symbol="BTCUSDT")

    assert second.to_dict() == first.to_dict()
    assert first.event_time == 2
