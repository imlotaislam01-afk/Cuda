from brain.intelligence import (
    MicrostructureEngine,
    ConfluenceEngine,
)


def test_bullish_microstructure():

    engine = MicrostructureEngine()

    result = engine.analyze({

        "order_flow": {
            "delta": 100,
            "cumulative_delta": 500,
            "absorption": False,
        },

        "orderbook": {
            "imbalance": 0.40,
        },

        "liquidity": {
            "sweep": "sell_side",
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
            "absorption": False,
        },

        "orderbook": {
            "imbalance": -0.40,
        },

        "liquidity": {
            "sweep": "buy_side",
        },

    })

    assert result.bias == "SHORT"
    assert result.score >= 50


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
