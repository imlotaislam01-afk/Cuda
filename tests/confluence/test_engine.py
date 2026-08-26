from brain.confluence import (
    ConfluenceEngine,
    Signal,
)


def test_strong_bullish_confluence():

    engine = ConfluenceEngine()

    signals = [
        engine.structure(
            "BULLISH",
            reason="Bullish BOS",
        ),
        engine.liquidity(
            "BULLISH",
            reason="Sell-side sweep",
        ),
        engine.displacement(
            "BULLISH",
            reason="Strong bullish displacement",
        ),
        engine.fvg(
            "BULLISH",
            reason="Bullish FVG",
        ),
        engine.orderflow(
            "BULLISH",
            reason="Aggressive buying",
        ),
    ]

    result = engine.analyze(signals)

    assert result.bias == "LONG"
    assert result.score == 100.0
    assert result.quality == "A+"
    assert result.status == "TRADE_CANDIDATE"


def test_strong_bearish_confluence():

    engine = ConfluenceEngine()

    signals = [
        engine.structure("BEARISH"),
        engine.liquidity("BEARISH"),
        engine.displacement("BEARISH"),
        engine.fvg("BEARISH"),
        engine.orderflow("BEARISH"),
    ]

    result = engine.analyze(signals)

    assert result.bias == "SHORT"
    assert result.score == 100.0
    assert result.quality == "A+"
    assert result.status == "TRADE_CANDIDATE"


def test_insufficient_score_is_filtered():

    engine = ConfluenceEngine(
        minimum_score=60,
    )

    signals = [
        engine.structure("BULLISH"),
        engine.fvg("BULLISH"),
    ]

    result = engine.analyze(signals)

    assert result.bias == "LONG"
    assert result.score == 35.0
    assert result.status == "FILTERED"


def test_bullish_score_wins():

    engine = ConfluenceEngine()

    signals = [
        engine.structure("BULLISH"),
        engine.liquidity("BULLISH"),
        engine.fvg("BULLISH"),
        engine.orderflow("BEARISH"),
    ]

    result = engine.analyze(signals)

    assert result.bias == "LONG"
    assert result.bullish_score == 60.0
    assert result.bearish_score == 20.0


def test_bearish_score_wins():

    engine = ConfluenceEngine()

    signals = [
        engine.structure("BEARISH"),
        engine.liquidity("BEARISH"),
        engine.fvg("BEARISH"),
        engine.orderflow("BULLISH"),
    ]

    result = engine.analyze(signals)

    assert result.bias == "SHORT"
    assert result.bearish_score == 60.0
    assert result.bullish_score == 20.0


def test_conflict_is_detected():

    engine = ConfluenceEngine()

    signals = [
        engine.structure("BULLISH"),
        engine.liquidity("BEARISH"),
    ]

    result = engine.analyze(signals)

    assert result.bias == "WAIT"
    assert result.status == "CONFLICT"
    assert len(result.conflicts) == 1


def test_inactive_signal_is_ignored():

    engine = ConfluenceEngine()

    signals = [
        engine.structure("BULLISH"),
        engine.liquidity(
            "BEARISH",
            active=False,
        ),
    ]

    result = engine.analyze(signals)

    assert result.bias == "LONG"
    assert result.bullish_score == 20.0
    assert result.bearish_score == 0.0


def test_neutral_signal_is_ignored_for_direction():

    engine = ConfluenceEngine()

    signals = [
        engine.structure("BULLISH"),
        Signal(
            name="Neutral Filter",
            direction="NEUTRAL",
            score=50,
        ),
    ]

    result = engine.analyze(signals)

    assert result.bias == "LONG"
    assert result.bullish_score == 20.0


def test_empty_signals():

    engine = ConfluenceEngine()

    result = engine.analyze([])

    assert result.bias == "WAIT"
    assert result.score == 0
    assert result.status == "NO_SIGNAL"


def test_value_migration_is_bounded_contextual_evidence():
    signal = ConfluenceEngine().value("BULLISH", "Value migrating higher")

    assert signal.name == "Value Migration"
    assert signal.score == 5.0


def test_custom_weights():

    engine = ConfluenceEngine(
        weights={
            "structure": 30,
            "liquidity": 30,
            "displacement": 20,
            "fvg": 10,
            "orderflow": 10,
        }
    )

    signals = [
        engine.structure("BULLISH"),
        engine.liquidity("BULLISH"),
    ]

    result = engine.analyze(signals)

    assert result.score == 60
    assert result.bias == "LONG"
    assert result.status == "TRADE_CANDIDATE"


def test_to_dict():

    engine = ConfluenceEngine()

    result = engine.analyze([
        engine.structure(
            "BULLISH",
            reason="BOS confirmed",
        )
    ])

    data = result.to_dict()

    assert data["bias"] == "LONG"
    assert data["score"] == 20.0
    assert len(data["signals"]) == 1
    assert data["signals"][0]["name"] == "Market Structure"
