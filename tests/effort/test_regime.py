from brain.intelligence import RegimeEngine


def candle(event_time, price, *, confirmed=True, symbol=None):
    item = {"event_time": event_time, "open": price, "high": price, "low": price, "close": price, "confirmed": confirmed}
    if symbol is not None:
        item["symbol"] = symbol
    return item


def test_regime_fails_closed_without_visible_confirmed_data():
    result = RegimeEngine().analyze([candle(1, 100, confirmed=False)], as_of=1)
    assert result.state == "UNKNOWN"
    assert result.directional is False


def test_regime_excludes_future_and_other_symbol_data():
    candles = [candle(1, 100, symbol="BTCUSDT"), candle(2, 101, symbol="BTCUSDT"), candle(3, 500, symbol="ETHUSDT")]
    first = RegimeEngine().analyze(candles, as_of=2, symbol="BTCUSDT")
    second = RegimeEngine().analyze(candles, as_of=2, symbol="BTCUSDT")
    assert first.to_dict() == second.to_dict()
    assert first.event_time == 2