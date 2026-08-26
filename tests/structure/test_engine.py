from brain.structure import (
    MarketStructureEngine,
)


def candle(
    high,
    low,
    close=None,
):
    if close is None:
        close = (high + low) / 2

    return {
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }


def test_detect_swing_high():

    candles = [
        candle(10, 8),
        candle(11, 9),
        candle(15, 10),
        candle(12, 9),
        candle(11, 8),
    ]

    engine = MarketStructureEngine(
        swing_strength=1
    )

    swings = engine.detect_swings(
        candles
    )

    highs = [
        x for x in swings
        if x.kind == "HIGH"
    ]

    assert len(highs) == 1
    assert highs[0].price == 15


def test_detect_swing_low():

    candles = [
        candle(15, 10),
        candle(13, 8),
        candle(12, 5),
        candle(14, 9),
        candle(16, 10),
    ]

    engine = MarketStructureEngine(
        swing_strength=1
    )

    swings = engine.detect_swings(
        candles
    )

    lows = [
        x for x in swings
        if x.kind == "LOW"
    ]

    assert len(lows) == 1
    assert lows[0].price == 5


def test_bullish_higher_high_higher_low():

    candles = [
        candle(10, 5),
        candle(12, 6),
        candle(9, 4),
        candle(13, 7),
        candle(11, 6),
        candle(15, 8),
        candle(12, 7),
    ]

    engine = MarketStructureEngine(
        swing_strength=1
    )

    result = engine.analyze(
        candles
    )

    assert result.higher_high is True
    assert result.higher_low is True
    assert result.trend == "BULLISH"
    assert result.bias == "LONG"


def test_bearish_lower_high_lower_low():

    candles = [
        candle(15, 10),
        candle(13, 8),
        candle(14, 9),
        candle(11, 6),
        candle(12, 7),
        candle(9, 4),
        candle(10, 5),
    ]

    engine = MarketStructureEngine(
        swing_strength=1
    )

    result = engine.analyze(
        candles
    )

    assert result.lower_high is True
    assert result.lower_low is True
    assert result.trend == "BEARISH"
    assert result.bias == "SHORT"


def test_bullish_bos():

    candles = [
        {"open": 8, "high": 10, "low": 5, "close": 8},
        {"open": 11, "high": 12, "low": 6, "close": 11},
        {"open": 7, "high": 9, "low": 4, "close": 7},
        {"open": 12, "high": 13, "low": 7, "close": 12},
        {"open": 10, "high": 11, "low": 6, "close": 10},
        {"open": 14, "high": 15, "low": 8, "close": 14},
        {"open": 13, "high": 14, "low": 9, "close": 13},
        {"open": 16, "high": 16, "low": 10, "close": 16},
    ]

    engine = MarketStructureEngine(
        swing_strength=1
    )

    result = engine.analyze(candles)

    assert result.bos == "BULLISH"

def test_bearish_bos():

    candles = [
        candle(15, 10),
        candle(13, 8),
        candle(14, 9),
        candle(11, 6),
        candle(12, 7),
        candle(9, 4),
        candle(3, 2),
    ]

    engine = MarketStructureEngine(
        swing_strength=1
    )

    result = engine.analyze(
        candles
    )

    assert result.bos == "BEARISH"
    assert result.bias == "SHORT"


def test_structure_serialization():

    candles = [
        candle(10, 5),
        candle(12, 6),
        candle(9, 4),
        candle(13, 7),
        candle(11, 6),
    ]

    engine = MarketStructureEngine()

    result = engine.analyze(
        candles
    )

    data = result.to_dict()

    assert isinstance(data, dict)
    assert "bias" in data
    assert "swings" in data
    assert "events" in data
