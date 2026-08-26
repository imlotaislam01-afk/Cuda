from brain.oi import (
    OIEngine,
    OISnapshot,
)


def test_long_buildup():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=3.0,
            oi_change_pct=5.0,
        )
    )

    assert result.regime == "LONG_BUILDUP"
    assert result.direction == "BULLISH"
    assert result.strength == "STRONG"


def test_short_buildup():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=-3.0,
            oi_change_pct=5.0,
        )
    )

    assert result.regime == "SHORT_BUILDUP"
    assert result.direction == "BEARISH"
    assert result.strength == "STRONG"


def test_short_covering():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=3.0,
            oi_change_pct=-3.0,
        )
    )

    assert result.regime == "SHORT_COVERING"
    assert result.direction == "BULLISH"


def test_long_liquidation():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=-3.0,
            oi_change_pct=-3.0,
        )
    )

    assert result.regime == "LONG_LIQUIDATION"
    assert result.direction == "BEARISH"


def test_position_buildup():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=0.05,
            oi_change_pct=3.0,
        )
    )

    assert result.regime == "POSITION_BUILDUP"
    assert result.direction == "NEUTRAL"


def test_position_reduction():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=-0.05,
            oi_change_pct=-3.0,
        )
    )

    assert result.regime == "POSITION_REDUCTION"
    assert result.direction == "NEUTRAL"


def test_neutral():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=0.05,
            oi_change_pct=0.05,
        )
    )

    assert result.regime == "NEUTRAL"
    assert result.direction == "NEUTRAL"


def test_volume_confirmation():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=3.0,
            oi_change_pct=5.0,
            volume_ratio=3.5,
        )
    )

    assert any(
        "relative volume" in reason
        for reason in result.reasons
    )


def test_funding_context():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=3.0,
            oi_change_pct=5.0,
            funding_rate=0.02,
        )
    )

    assert any(
        "positive funding" in reason
        for reason in result.reasons
    )


def test_confidence_is_bounded():

    engine = OIEngine()

    result = engine.analyze(
        OISnapshot(
            price_change_pct=10.0,
            oi_change_pct=20.0,
            volume_ratio=10.0,
        )
    )

    assert 0 <= result.confidence <= 100


def test_to_dict():

    snapshot = OISnapshot(
        price_change_pct=2.0,
        oi_change_pct=3.0,
    )

    result = OIEngine().analyze(snapshot)

    data = result.to_dict()

    assert data["regime"] == "LONG_BUILDUP"
    assert "confidence" in data
    assert "reasons" in data
