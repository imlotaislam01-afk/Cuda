
from brain.fvg import FVGEngine

def candle(

    high: float,

    low: float,

    close: float,

    open_: float | None = None,

):

    if open_ is None:

        open_ = close

    return {

        "open": open_,

        "high": high,

        "low": low,

        "close": close,

    }

def test_bullish_fvg():

    candles = [

        candle(100, 95, 98),

        candle(105, 99, 104),

        candle(110, 102, 108),

    ]

    engine = FVGEngine()

    result = engine.analyze(candles)

    assert len(result.bullish_gaps) >= 1

    gap = result.bullish_gaps[0]

    assert gap.direction == "BULLISH"

    assert gap.lower == 100

    assert gap.upper == 102

    assert gap.size == 2

def test_bearish_fvg():

    candles = [

        candle(110, 105, 108),

        candle(106, 100, 102),

        candle(103, 95, 98),

    ]

    engine = FVGEngine()

    result = engine.analyze(candles)

    assert len(result.bearish_gaps) >= 1

    gap = result.bearish_gaps[0]

    assert gap.direction == "BEARISH"

    assert gap.lower == 103

    assert gap.upper == 105

    assert gap.size == 2

def test_bullish_displacement():

    candles = [
        candle(101, 99, 100, 99.5),

        # Large bullish body.
        candle(106, 99, 105, 100),
    ]

    engine = FVGEngine(
        min_body_ratio=0.60,
        displacement_pct=0.001,
    )

    result = engine.analyze(candles)

    displacement = result.latest_displacement

    assert displacement is not None
    assert displacement.direction == "BULLISH"
    assert displacement.strong is True


def test_bearish_displacement():

    candles = [
        candle(101, 99, 100, 100.5),

        # Large bearish body.
        candle(101, 94, 95, 100),
    ]

    engine = FVGEngine(
        min_body_ratio=0.60,
        displacement_pct=0.001,
    )

    result = engine.analyze(candles)

    displacement = result.latest_displacement

    assert displacement is not None
    assert displacement.direction == "BEARISH"
    assert displacement.strong is True



def test_weak_candle_is_not_displacement():

    candles = [

        candle(101, 99, 100),

        candle(102, 98, 100.5),

    ]

    engine = FVGEngine(

        min_body_ratio=0.60,

        displacement_pct=0.001,

    )

    result = engine.analyze(candles)

    strong = [

        x

        for x in result.displacements

        if x.strong

    ]

    assert len(strong) == 0

def test_fvg_fill():

    candles = [

        candle(100, 95, 98),

        candle(105, 99, 104),

        candle(110, 102, 108),

        # Price trades back into the FVG.

        candle(106, 101, 103),

        # Fully fills bullish FVG.

        candle(103, 99, 100),

    ]

    engine = FVGEngine()

    result = engine.analyze(candles)

    bullish = [

        x for x in result.gaps

        if x.direction == "BULLISH"

    ]

    assert bullish

    assert bullish[0].filled is True

    assert bullish[0].fill_pct == 1.0

def test_empty_market():

    engine = FVGEngine()

    result = engine.analyze([])

    assert result.bias == "WAIT"

    assert result.confidence == 0

    assert result.gaps == []

    assert result.displacements == []

def test_bullish_fvg_plus_displacement():

    candles = [

        candle(100, 95, 98),

        candle(

            106,

            99,

            105,

            100,

        ),

        candle(

            112,

            103,

            111,

            104,

        ),

    ]

    engine = FVGEngine(

        min_body_ratio=0.60,

        displacement_pct=0.001,

    )

    result = engine.analyze(candles)

    assert result.bullish_gaps

    assert result.latest_displacement is not None

    assert result.latest_displacement.direction == "BULLISH"

def test_bearish_fvg_plus_displacement():

    candles = [

        candle(110, 105, 108),

        candle(

            106,

            99,

            100,

            105,

        ),

        candle(

            103,

            94,

            95,

            102,

        ),

    ]

    engine = FVGEngine(

        min_body_ratio=0.60,

        displacement_pct=0.001,

    )

    result = engine.analyze(candles)

    assert result.bearish_gaps

    assert result.latest_displacement is not None

    assert result.latest_displacement.direction == "BEARISH"

