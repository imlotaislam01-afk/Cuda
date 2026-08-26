from brain.confluence import ConfluenceEngine
from brain.context import Candle, MarketContextBuilder, OrderBook, Trade
from brain.pipeline import ApexBrainPipeline
from brain.risk import RiskConfig, RiskGate
from brain.structure.mtf import MTFStructureResult
from market.indicators import ATRCalculator


def context(price=105.0, funding=None, candles=None):
    candles = candles or (
        Candle(1, 100, 103, 99, 101, 10),
        Candle(2, 101, 106, 100, 105, 20),
        Candle(3, 105, 108, 104, 105, 30),
    )
    builder = (MarketContextBuilder("BTCUSDT", price, "5m")
               .set_exchange("BYBIT")
               .set_market_data(
                   candles=candles,
                   order_book=OrderBook(bids=((104, 2),), asks=((106, 2),)),
                   trades=(Trade("t1", 3, price, 1, "BUY"),),
                   open_interest=100,
                   oi_change=5,
                   funding=funding,
               )
               .set_event_times(event_time=3, received_time=3, calculation_time=3)
               .set_data_quality("OK"))
    return builder.build(allow_incomplete=True)


def signals(result, name):
    return [signal for signal in result.context.confluence.signals if signal.name == name]


def test_mtf_alignment_is_bounded_and_conflict_still_waits(monkeypatch):
    pipeline = ApexBrainPipeline()
    aligned = MTFStructureResult("LONG", True, {}, [], mtf_bias="LONG", alignment_score=100)
    monkeypatch.setattr(pipeline.mtf, "analyze", lambda *args, **kwargs: aligned)
    result = pipeline.run(context())
    assert signals(result, "MTF Alignment")[0].score == 10

    conflict = MTFStructureResult("WAIT", False, {}, [], conflict=True)
    monkeypatch.setattr(pipeline.mtf, "analyze", lambda *args, **kwargs: conflict)
    assert pipeline.run(context()).decision.action == "WAIT"


def test_microstructure_uses_bounded_residual_credit():
    engine = ConfluenceEngine()
    signal = engine.microstructure("BULLISH", 100, components={"book_bias": "bullish"})
    result = engine.analyze([engine.orderflow("BULLISH"), signal])
    assert signal.score == 10
    assert result.score <= 30


def test_vwap_above_below_and_near_are_explicit_context():
    above = ApexBrainPipeline().run(context(price=106))
    below = ApexBrainPipeline().run(context(price=100))
    near = ApexBrainPipeline().run(context(price=104.2222222222))
    assert signals(above, "VWAP Context")[0].direction == "BULLISH"
    assert signals(below, "VWAP Context")[0].direction == "BEARISH"
    assert not signals(near, "VWAP Context")


def test_funding_policy_is_contrarian_and_missing_is_unavailable():
    positive = ApexBrainPipeline().run(context(funding=0.02))
    negative = ApexBrainPipeline().run(context(funding=-0.02))
    normal = ApexBrainPipeline().run(context(funding=0.001))
    missing = ApexBrainPipeline().run(context())
    assert signals(positive, "Funding")[0].direction == "BEARISH"
    assert signals(negative, "Funding")[0].direction == "BULLISH"
    assert not signals(normal, "Funding")
    assert not signals(missing, "Funding")


def test_atr_price_regimes_are_low_normal_high():
    assert ATRCalculator.classify_regime(1, 1000, low=0.0025, high=0.01) == "LOW"
    assert ATRCalculator.classify_regime(5, 1000, low=0.0025, high=0.01) == "NORMAL"
    assert ATRCalculator.classify_regime(20, 1000, low=0.0025, high=0.01) == "HIGH"
    assert ATRCalculator.classify_regime(None, 1000, low=0.0025, high=0.01) == "UNKNOWN"


def test_high_volatility_is_rejected_by_risk_gate():
    result = RiskGate(RiskConfig(minimum_confidence=20)).evaluate(
        action="LONG", confidence=80, entry=100, stop_loss=99, leverage=1,
        volatility_regime="HIGH",
    )
    assert result.approved is False
    assert any("Volatility regime" in reason for reason in result.rejection_reasons)
