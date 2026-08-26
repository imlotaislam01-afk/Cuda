
from brain.liquidity import LiquidityEngine

def candle(
    high: float,
    low: float,
    close: float,
    open_: float | None = None,
    event_time: float | None = None,
    confirmed: bool = True,
    symbol: str | None = None,
):
    if open_ is None:
        open_ = close
    result = {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "confirmed": confirmed,
    }
    if event_time is not None:
        result["event_time"] = event_time
    if symbol is not None:
        result["symbol"] = symbol
    return result

def test_equal_high_creates_buy_side_pool():

    candles = [

        candle(100, 95, 98),

        candle(105, 97, 103),

        candle(100, 94, 97),

        candle(105, 96, 102),

    ]

    engine = LiquidityEngine(

        tolerance_pct=0.001,

        min_touches=2,

    )

    result = engine.analyze(candles)

    assert len(result.buy_side_pools) >= 1

    pool = result.buy_side_pools[0]

    assert pool.kind == "BUY_SIDE"

    assert pool.touches >= 2

def test_equal_low_creates_sell_side_pool():

    candles = [

        candle(105, 100, 103),

        candle(104, 95, 98),

        candle(103, 100, 102),

        candle(106, 95, 101),

    ]

    engine = LiquidityEngine(

        tolerance_pct=0.001,

        min_touches=2,

    )

    result = engine.analyze(candles)

    assert len(result.sell_side_pools) >= 1

    pool = result.sell_side_pools[0]

    assert pool.kind == "SELL_SIDE"

    assert pool.touches >= 2

def test_bullish_sell_side_sweep():

    candles = [

        candle(105, 100, 103),

        candle(104, 95, 98),

        candle(103, 100, 102),

        candle(106, 95, 101),

        candle(108, 94, 103),

        candle(110, 99, 109),

    ]

    engine = LiquidityEngine(

        tolerance_pct=0.001,

        min_touches=2,

        displacement_pct=0.001,

    )

    result = engine.analyze(candles)

    assert result.latest_sweep is not None

    assert result.latest_sweep.direction == "BULLISH"

    assert result.latest_sweep.pool_kind == "SELL_SIDE"

    assert result.bias == "LONG"

def test_bearish_buy_side_sweep():

    candles = [

        candle(100, 95, 98),

        candle(105, 97, 103),

        candle(100, 94, 97),

        candle(105, 96, 102),

        candle(107, 98, 103),

        candle(106, 100, 101),

    ]

    engine = LiquidityEngine(

        tolerance_pct=0.001,

        min_touches=2,

        displacement_pct=0.001,

    )

    result = engine.analyze(candles)

    assert result.latest_sweep is not None

    assert result.latest_sweep.direction == "BEARISH"

    assert result.latest_sweep.pool_kind == "BUY_SIDE"

    assert result.bias == "SHORT"

def test_no_liquidity_means_wait():

    candles = [

        candle(100, 95, 98),

        candle(103, 97, 101),

        candle(106, 99, 104),

    ]

    engine = LiquidityEngine()

    result = engine.analyze(candles)

    assert result.latest_sweep is None

    assert result.bias == "WAIT"

    assert result.confidence == 0.0

def test_bullish_displacement():

    candles = [
        # Equal lows = SELL-SIDE liquidity at 100
        candle(105, 100, 103),
        candle(104, 95, 98),
        candle(103, 100, 102),
        candle(106, 101, 104),

        # Sweep below 100 and reclaim
        candle(105, 99, 102),

        # Strong bullish displacement AFTER sweep
        candle(112, 101, 110),
    ]

    engine = LiquidityEngine(
        tolerance_pct=0.001,
        min_touches=2,
        displacement_pct=0.001,
    )

    result = engine.analyze(candles)

    assert result.latest_sweep is not None
    assert result.latest_sweep.direction == "BULLISH"
    assert result.latest_sweep.displacement is True
    assert result.confidence == 90.0


def test_failed_sweep_is_reported_without_actionable_bias():
    candles = [
        candle(105, 100, 103),
        candle(104, 95, 98),
        candle(103, 100, 102),
        candle(106, 101, 104),
        candle(105, 99, 98),
    ]

    result = LiquidityEngine(min_touches=2).analyze(candles)

    assert result.latest_sweep is not None
    assert result.latest_sweep.rejection is False
    assert result.latest_sweep.confirmed is False
    assert result.bias == "WAIT"


def test_cutoff_excludes_future_pool_and_forming_candle():
    candles = [
        candle(100, 95, 98, event_time=1),
        candle(105, 97, 103, event_time=2),
        candle(101, 94, 97, event_time=3),
        candle(100, 96, 99, event_time=4, confirmed=False),
        candle(100, 96, 99, event_time=5),
    ]

    result = LiquidityEngine(min_touches=2).analyze(candles, as_of=4)

    assert result.buy_side_pools == []
    assert result.as_of == 4
    assert result.latest_sweep is None


def test_liquidity_outputs_are_deterministic_and_symbol_stamped():
    candles = [
        candle(100, 95, 98, event_time=1),
        candle(105, 97, 103, event_time=2),
        candle(100, 94, 97, event_time=3),
        candle(105, 96, 102, event_time=4),
    ]

    btc = LiquidityEngine().analyze(candles, as_of=4, symbol="BTCUSDT")
    eth = LiquidityEngine().analyze(candles, as_of=4, symbol="ETHUSDT")

    assert btc.to_dict() == LiquidityEngine().analyze(candles, as_of=4, symbol="BTCUSDT").to_dict()
    assert btc.symbol == "BTCUSDT"
    assert eth.symbol == "ETHUSDT"
    assert all(pool.symbol == "BTCUSDT" for pool in btc.buy_side_pools + btc.sell_side_pools)


def test_liquidity_ignores_explicitly_other_symbol_candles():
    candles = [
        candle(100, 95, 98, event_time=1, symbol="BTCUSDT"),
        candle(105, 97, 103, event_time=2, symbol="BTCUSDT"),
        candle(100, 94, 97, event_time=3, symbol="ETHUSDT"),
    ]

    result = LiquidityEngine().analyze(candles, symbol="BTCUSDT")

    assert result.buy_side_pools == []
