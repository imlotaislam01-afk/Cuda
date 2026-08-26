from brain.structure import MultiTimeframeStructure


def bullish():
    return [
        {"open": 8, "high": 10, "low": 5, "close": 8},
        {"open": 11, "high": 12, "low": 6, "close": 11},
        {"open": 7, "high": 9, "low": 4, "close": 7},
        {"open": 12, "high": 13, "low": 7, "close": 12},
        {"open": 10, "high": 11, "low": 6, "close": 10},
        {"open": 14, "high": 15, "low": 8, "close": 14},
        {"open": 13, "high": 14, "low": 9, "close": 13},
        {"open": 16, "high": 16, "low": 10, "close": 16},
    ]


def bearish():
    return [
        {"open": 15, "high": 15, "low": 10, "close": 15},
        {"open": 13, "high": 13, "low": 8, "close": 13},
        {"open": 14, "high": 14, "low": 9, "close": 14},
        {"open": 11, "high": 11, "low": 6, "close": 11},
        {"open": 12, "high": 12, "low": 7, "close": 12},
        {"open": 9, "high": 9, "low": 4, "close": 9},
        {"open": 3, "high": 3, "low": 2, "close": 3},
    ]


def test_bullish_hierarchy_alignment():
    result = MultiTimeframeStructure(swing_strength=1).analyze({
        "4H": bullish(), "15m": bullish(), "1m": bullish(),
    })
    assert result.htf_bias == "LONG"
    assert result.mtf_bias == "LONG"
    assert result.ltf_bias == "LONG"
    assert result.aligned is True
    assert result.alignment_score == 100


def test_htf_and_ltf_conflict_is_explicit():
    result = MultiTimeframeStructure(swing_strength=1).analyze({
        "1H": bullish(), "1m": bearish(),
    })
    assert result.htf_bias == "LONG"
    assert result.ltf_bias == "SHORT"
    assert result.conflict is True
    assert result.bias == "LONG"


def test_missing_timeframe_does_not_invent_alignment():
    result = MultiTimeframeStructure(swing_strength=1).analyze({"1H": bullish()})
    assert result.htf_bias == "LONG"
    assert result.mtf_bias == "WAIT"
    assert result.ltf_bias == "WAIT"
    assert result.aligned is True