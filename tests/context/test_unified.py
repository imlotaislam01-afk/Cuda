from brain.context import (
    MarketContextBuilder,
    PriceContext,
)

from brain.confluence import (
    ConfluenceEngine,
)

from brain.oi import (
    OIEngine,
    OISnapshot,
)


def make_confluence():

    engine = ConfluenceEngine()

    return engine.analyze([
        engine.structure("BULLISH"),
        engine.liquidity("BULLISH"),
        engine.displacement("BULLISH"),
        engine.fvg("BULLISH"),
        engine.orderflow("BULLISH"),
    ])


def make_oi():

    return OIEngine().analyze(
        OISnapshot(
            price_change_pct=3.0,
            oi_change_pct=5.0,
            volume_ratio=3.0,
        )
    )


def test_price_context():

    price = PriceContext(
        symbol="BTCUSDT",
        price=100000.0,
        timeframe="5m",
        change_pct=1.2,
        volume=5000,
        volume_ratio=2.5,
        atr=500,
    )

    assert price.symbol == "BTCUSDT"
    assert price.price == 100000
    assert price.timeframe == "5m"


def test_builder_requires_confluence():

    builder = MarketContextBuilder(
        symbol="BTCUSDT",
        price=100000,
    )

    builder.set_oi(make_oi())

    try:
        builder.build()
    except ValueError as exc:
        assert "Confluence" in str(exc)
    else:
        raise AssertionError(
            "Expected missing confluence error"
        )


def test_builder_requires_oi():

    builder = MarketContextBuilder(
        symbol="BTCUSDT",
        price=100000,
    )

    builder.set_confluence(
        make_confluence()
    )

    try:
        builder.build()
    except ValueError as exc:
        assert "OI" in str(exc)
    else:
        raise AssertionError(
            "Expected missing OI error"
        )


def test_build_complete_context():

    confluence = make_confluence()
    oi = make_oi()

    context = (
        MarketContextBuilder(
            symbol="BTCUSDT",
            price=100000,
        )
        .set_price(
            price=100500,
            change_pct=2.0,
            volume=10000,
            volume_ratio=3.5,
            atr=600,
        )
        .set_confluence(confluence)
        .set_oi(oi)
        .set_timestamp(1234567890)
        .add_metadata(
            "source",
            "test",
        )
        .build()
    )

    assert context.symbol == "BTCUSDT"
    assert context.current_price == 100500
    assert context.bias == "LONG"
    assert context.score == 100
    assert context.regime == "LONG_BUILDUP"
    assert context.oi_direction == "BULLISH"
    assert context.trade_candidate is True


def test_builder_accepts_optional_engines():

    context = (
        MarketContextBuilder(
            symbol="ETHUSDT",
            price=4000,
        )
        .set_confluence(
            make_confluence()
        )
        .set_oi(
            make_oi()
        )
        .set_orderflow(
            {"delta": 500}
        )
        .set_liquidity(
            {"sweep": "BULLISH"}
        )
        .set_structure(
            {"bos": "BULLISH"}
        )
        .set_fvg(
            {"direction": "BULLISH"}
        )
        .build()
    )

    assert context.orderflow["delta"] == 500
    assert context.liquidity["sweep"] == "BULLISH"
    assert context.structure["bos"] == "BULLISH"
    assert context.fvg["direction"] == "BULLISH"


def test_to_dict():

    context = (
        MarketContextBuilder(
            symbol="BTCUSDT",
            price=100000,
        )
        .set_confluence(
            make_confluence()
        )
        .set_oi(
            make_oi()
        )
        .build()
    )

    data = context.to_dict()

    assert data["symbol"] == "BTCUSDT"
    assert "price" in data
    assert "confluence" in data
    assert "oi" in data
    assert data["confluence"]["bias"] == "LONG"


def test_metadata_is_copied():

    builder = (
        MarketContextBuilder(
            symbol="BTCUSDT",
            price=100000,
        )
        .set_confluence(
            make_confluence()
        )
        .set_oi(
            make_oi()
        )
    )

    builder.add_metadata(
        "exchange",
        "BYBIT",
    )

    context = builder.build()

    assert context.metadata["exchange"] == "BYBIT"


def test_price_update_preserves_existing_values():

    builder = MarketContextBuilder(
        symbol="BTCUSDT",
        price=100000,
    )

    builder.set_price(
        price=101000,
        change_pct=1.0,
        volume_ratio=2.0,
    )

    builder.set_price(
        price=102000,
    )

    context = (
        builder
        .set_confluence(make_confluence())
        .set_oi(make_oi())
        .build()
    )

    assert context.current_price == 102000
    assert context.price.change_pct == 1.0
    assert context.price.volume_ratio == 2.0
