from brain.structure import MarketStructureEngine


def candle(event_time, high, low):
    close = (high + low) / 2
    return {
        "event_time": event_time,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }


def test_future_candles_are_not_used_before_pivot_confirmation():
    candles = [
        candle(1, 10, 8),
        candle(2, 12, 9),
        candle(3, 20, 10),
        candle(4, 13, 9),
        candle(5, 11, 8),
    ]
    engine = MarketStructureEngine(swing_strength=1)

    before_confirmation = engine.analyze(candles, as_of=3)
    after_confirmation = engine.analyze(candles, as_of=4)

    assert before_confirmation.last_high is None
    assert after_confirmation.last_high == 20


def test_forming_candles_cannot_create_structure():
    candles = [
        candle(1, 10, 8),
        candle(2, 20, 10),
        candle(3, 11, 8),
    ]
    candles[1]["confirmed"] = False

    result = MarketStructureEngine(swing_strength=1).analyze(candles, as_of=3)

    assert result.swings == []
    assert result.bos == "NONE"


def test_structure_ignores_explicitly_other_symbols():
    candles = [
        {**candle(index, high, low), "symbol": "ETHUSDT"}
        for index, high, low in ((1, 10, 8), (2, 20, 10), (3, 11, 8))
    ]

    result = MarketStructureEngine(swing_strength=1).analyze(
        candles,
        as_of=3,
        symbol="BTCUSDT",
    )

    assert result.swings == []