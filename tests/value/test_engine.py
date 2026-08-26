from brain.value import ValueMigrationEngine


def candle(event_time, price, volume=10, *, confirmed=True, symbol=None):
    result = {
        "event_time": event_time,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
        "confirmed": confirmed,
    }
    if symbol is not None:
        result["symbol"] = symbol
    return result


def test_value_profile_is_event_time_bounded_and_deterministic():
    engine = ValueMigrationEngine(lookback=4, bin_size=1)
    candles = [
        candle(1, 100),
        candle(2, 101),
        candle(3, 102),
        candle(4, 103, volume=30),
        candle(5, 200, volume=100),
    ]

    first = engine.analyze(candles, as_of=4, symbol="BTCUSDT")
    second = engine.analyze(candles, as_of=4, symbol="BTCUSDT")

    assert first.to_dict() == second.to_dict()
    assert first.event_time == 4
    assert first.poc < 200
    assert first.as_of == 4


def test_value_excludes_forming_and_other_symbol_candles():
    engine = ValueMigrationEngine(lookback=4)
    candles = [
        candle(1, 100, symbol="BTCUSDT"),
        candle(2, 101, symbol="BTCUSDT"),
        candle(3, 102, confirmed=False, symbol="BTCUSDT"),
        candle(4, 200, volume=100, symbol="ETHUSDT"),
    ]

    result = engine.analyze(candles, as_of=4, symbol="BTCUSDT")

    assert result.event_time == 2
    assert result.poc == 100


def test_value_reports_balance_for_inside_value_price():
    result = ValueMigrationEngine(lookback=4).analyze([
        candle(1, 100),
        candle(2, 100),
        candle(3, 101),
        candle(4, 101),
    ], as_of=4)

    assert result.state == "BALANCE"
    assert result.auction == "BALANCED_AUCTION"
    assert result.acceptance == "INSIDE_VALUE"


def test_value_is_unavailable_without_two_visible_candles():
    result = ValueMigrationEngine().analyze([candle(10, 100)], as_of=10)

    assert result.state == "UNAVAILABLE"
    assert result.data_quality == "DATA_INCOMPLETE"
    assert result.poc is None
