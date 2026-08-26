from market.indicators import RVOLCalculator, VolumeProfileCalculator


def candle(event_time, volume, *, confirmed=True, price=100):
    return {
        "event_time": event_time,
        "open": price,
        "high": price + 1,
        "low": price - 1,
        "close": price,
        "volume": volume,
        "confirmed": confirmed,
    }


def test_rvol_normal_high_low_and_insufficient_history():
    candles = [candle(1, 10), candle(2, 10), candle(3, 10), candle(4, 20)]
    calculator = RVOLCalculator(lookback=3)
    assert calculator.calculate(candles).rvol == 2.0
    assert calculator.calculate([*candles[:-1], candle(4, 5)]).rvol == 0.5
    assert calculator.calculate(candles[:2]).rvol is None
    assert calculator.calculate(candles).data_quality == "DATA_VALID"
    result = calculator.calculate(candles, as_of=4)
    assert result.sample_count == 3
    assert result.as_of == 4


def test_rvol_excludes_zero_baseline_future_forming_and_duplicate_timestamp():
    calculator = RVOLCalculator(lookback=2)
    zero = [candle(1, 0), candle(2, 0), candle(3, 10)]
    assert calculator.calculate(zero).rvol is None
    data = [candle(1, 10), candle(2, 10), candle(3, 10), candle(4, 100), candle(5, 1000, confirmed=False)]
    assert calculator.calculate(data, as_of=4).rvol == 10.0
    duplicate = [candle(1, 10), candle(2, 10), candle(2, 100), candle(3, 20)]
    assert calculator.calculate(duplicate).rvol == 20 / 55


def test_volume_profile_poc_value_area_and_location():
    candles = [
        candle(1, 10, price=100),
        candle(2, 30, price=101),
        candle(3, 20, price=102),
    ]
    result = VolumeProfileCalculator(lookback=3, bin_size=1).calculate(candles)
    assert result.poc == 101
    assert result.val <= result.poc <= result.vah
    assert result.data_quality == "DATA_VALID"
    assert result.approximation.startswith("OHLCV typical-price")
    assert result.sample_count == 3
    assert result.bin_count == 3
    assert result.as_of is None


def test_volume_indicators_reject_malformed_input_without_partial_values():
    malformed = [candle(1, 10), {"event_time": 2, "high": 101, "low": 99, "close": 100}]
    assert RVOLCalculator(lookback=1).calculate(malformed).data_quality == "DATA_INVALID"
    assert VolumeProfileCalculator(lookback=2).calculate(malformed).data_quality == "DATA_INVALID"


def test_volume_profile_is_bounded_confirmed_and_deterministic():
    calculator = VolumeProfileCalculator(lookback=3, bin_size=1)
    candles = [candle(1, 10, price=100), candle(2, 20, price=101), candle(3, 30, price=102), candle(4, 100, price=200)]
    first = calculator.calculate(candles, as_of=3)
    second = calculator.calculate(candles, as_of=3)
    assert first.to_dict() == second.to_dict()
    assert first.poc < 200
    assert calculator.calculate(candles[:2]).poc is not None
    assert calculator.calculate([candle(1, 10, confirmed=False)]).poc is None
