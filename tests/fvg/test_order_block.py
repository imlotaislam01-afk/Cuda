from brain.fvg import OrderBlockEngine


def candles(*items):
    return [{"event_time": time, "open": opening, "high": high, "low": low, "close": close, "confirmed": confirmed}
            for time, opening, high, low, close, confirmed in items]


def test_order_block_creation_cutoff_and_direction():
    result = OrderBlockEngine().analyze(candles(
        (1, 100, 102, 98, 99, True),
        (2, 99, 106, 98, 105, True),
        (3, 105, 106, 103, 104, True),
    ), as_of=2, symbol="BTCUSDT")
    assert len(result.bullish_blocks) == 1
    block = result.bullish_blocks[0]
    assert block.origin_time == 1
    assert block.creation_time == 2
    assert block.event_time == 2
    assert block.mitigation_state == "ACTIVE"


def test_order_block_mitigation_invalidation_forming_and_symbol_isolation():
    engine = OrderBlockEngine()
    base = candles((1, 100, 102, 98, 99, True), (2, 99, 106, 98, 105, True))
    partial = engine.analyze(base + candles((3, 105, 106, 100, 103, True)), symbol="BTCUSDT")
    assert partial.latest.mitigation_state == "PARTIALLY_MITIGATED"
    invalid = engine.analyze(base + candles((3, 105, 106, 97, 103, True)), symbol="BTCUSDT")
    assert invalid.latest.invalidation_state == "INVALIDATED"
    future = engine.analyze(base + candles((4, 105, 110, 104, 109, True)), as_of=2, symbol="BTCUSDT")
    assert len(future.blocks) == 1
    forming = engine.analyze(base + candles((4, 105, 110, 104, 109, False)), symbol="BTCUSDT")
    assert len(forming.blocks) == 1
    mismatch = engine.analyze([dict(item, symbol="ETHUSDT") for item in base], symbol="BTCUSDT")
    assert mismatch.blocks == []