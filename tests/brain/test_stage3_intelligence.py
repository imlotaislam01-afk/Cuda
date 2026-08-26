from brain.intelligence import (
    MicrostructureEngine,
    ConfluenceEngine,
)

from market.liquidity import (
    LiquiditySweepDetector,
)


def test_sell_side_sweep():

    detector = LiquiditySweepDetector()

    result = detector.detect(
        price=99_900,
        previous_low=100_000,
        delta=500,
    )

    assert result.detected is True
    assert result.direction == "sell_side"


def test_buy_side_sweep():

    detector = LiquiditySweepDetector()

    result = detector.detect(
        price=100_100,
        previous_high=100_000,
        delta=-500,
    )

    assert result.detected is True
    assert result.direction == "buy_side"


def test_no_sweep():

    detector = LiquiditySweepDetector()

    result = detector.detect(
        price=100_000,
        previous_low=99_500,
        previous_high=100_500,
    )

    assert result.detected is False
    assert result.direction == "none"


def test_bullish_microstructure():

    engine = MicrostructureEngine()

    result = engine.analyze({

        "order_flow": {
            "delta": 100,
            "cumulative_delta": 500,
            "aggression": "strong",
            "absorption": False,
        },

        "orderbook": {
            "imbalance": 0.40,
        },

        "liquidity": {
            "sweep": "sell_side",
            "sweep_strength": 0.8,
        },

    })

    assert result.bias == "LONG"
    assert result.score >= 50


def test_bearish_microstructure():

    engine = MicrostructureEngine()

    result = engine.analyze({

        "order_flow": {
            "delta": -100,
            "cumulative_delta": -500,
            "aggression": "strong",
            "absorption": False,
        },

        "orderbook": {
            "imbalance": -0.40,
        },

        "liquidity": {
            "sweep": "buy_side",
            "sweep_strength": 0.8,
        },

    })

    assert result.bias == "SHORT"
    assert result.score >= 50


def test_microstructure_conflict_is_not_automatic_entry():

    engine = MicrostructureEngine()

    result = engine.analyze({

        "order_flow": {
            "delta": 100,
            "cumulative_delta": 500,
            "aggression": "strong",
            "absorption": False,
        },

        "orderbook": {
            "imbalance": -0.80,
        },

        "liquidity": {
            "sweep": "none",
        },

    })

    assert result.divergence is True
    assert result.bias in {"LONG", "SHORT", "WAIT"}


def test_confluence_wait():

    engine = ConfluenceEngine()

    result = engine.evaluate(
        market={},
        microstructure={
            "bias": "WAIT",
            "score": 0,
        },
    )

    assert result.bias == "WAIT"
    assert result.approved is False


def test_strong_long_confluence():

    engine = ConfluenceEngine()

    result = engine.evaluate(

        market={
            "structure": {
                "bias": "BULLISH",
            },

            "open_interest": {
                "change_pct": 5.0,
            },

            "volume": {
                "rvol": 3.5,
            },

            "fvg": {
                "active": True,
                "bias": "BULLISH",
            },

        },

        microstructure={
            "bias": "LONG",
            "score": 100,
        },
    )

    assert result.bias == "LONG"
    assert result.approved is True
    assert result.score >= 75
